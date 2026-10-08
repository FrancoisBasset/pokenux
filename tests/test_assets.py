"""Offline regression tests for catalogue publication and transactional installs."""

import copy
from contextlib import nullcontext
from dataclasses import replace
import hashlib
import importlib.util
import io
from email.message import Message
import json
from pathlib import Path
import tempfile
import unittest
from typing import Any
from unittest.mock import patch
from urllib.error import HTTPError
from zipfile import ZipFile, ZipInfo

from pokenux.services.assets import (
    AssetError,
    AssetManager,
    AssetManifest,
    MANIFEST_NAME,
    MANIFEST_URL,
    LEGACY_URL,
    REQUIRED_FILES,
    validate_catalogues,
)

spec = importlib.util.spec_from_file_location(
    "prepare_assets", Path(__file__).parents[1] / "scripts" / "prepare_assets.py"
)
assert spec is not None and spec.loader is not None
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def pokemon() -> dict[str, Any]:
    return {
        "pokedex_id": 1,
        "generation": 1,
        "name": {"fr": "Bulbizarre", "en": "Bulbasaur"},
        "category": "Pokémon Graine",
        "sprites": {"regular": "https://example.com/1.png", "shiny": "", "gmax": None},
        "types": [{"name": "Plante", "image": ""}],
        "talents": [{"name": "Engrais", "hidden": False}],
        "stats": {
            "hp": 45,
            "attack": 49,
            "defense": 49,
            "special_attack": 65,
            "special_defense": 65,
            "speed": 45,
        },
        "resistances": [],
        "evolution": {"pre": None, "next": [], "mega": None},
        "height": "0,7 m",
        "weight": "6,9 kg",
        "egg_groups": ["Monstrueux"],
        "sex": None,
        "catch_rate": 45,
    }


def catalogues(root):
    data = root / "data"
    data.mkdir(parents=True)
    values: dict[str, Any] = {
        "pokemon.json": [pokemon()],
        "generations.json": ["1"],
        "types.json": [{"fr": "Plante", "en": "Grass"}],
    }
    for lang in ("fr", "en"):
        values[f"tcg_{lang}.json"] = [
            {
                "id": "base",
                "name": "Base",
                "sets": [
                    {
                        "id": "base1",
                        "name": "Base",
                        "cards": [
                            {
                                "id": "base1-1",
                                "name": "Bulbizarre" if lang == "fr" else "Bulbasaur",
                            }
                        ],
                    }
                ],
            }
        ]
    for name, value in values.items():
        (data / name).write_text(json.dumps(value), encoding="utf-8")


class Response(io.BytesIO):
    def __init__(self, body):
        super().__init__(body)
        self.headers = {"Content-Length": str(len(body))}


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        catalogues(self.source)
        self.output = self.root / "output"
        self.manifest = prepare.package_catalogues(self.source, self.output, "1.0.0")
        self.network = {
            MANIFEST_URL: (self.output / MANIFEST_NAME).read_bytes(),
            self.manifest.archive.url: (
                self.output / self.manifest.archive.name
            ).read_bytes(),
        }
        self.calls = []

        def opener(request, timeout):
            self.calls.append(request.full_url)
            self.assertEqual(timeout, 20)
            result = self.network[request.full_url]
            if isinstance(result, Exception):
                raise result
            return Response(result)

        self.manager = AssetManager(self.root / "user", opener=opener)

    def test_packager_is_deterministic_and_only_contains_catalogues(self):
        second = self.root / "second"
        manifest = prepare.package_catalogues(self.source, second, "1.0.0")
        self.assertEqual(manifest, self.manifest)
        with ZipFile(second / manifest.archive.name) as archive:
            self.assertEqual(set(archive.namelist()), set(REQUIRED_FILES))
        self.assertEqual(manifest.languages, ("fr", "en"))

    def test_install_checks_files_and_keeps_legacy_for_rollback(self):
        catalogues(self.manager.active_path)
        (self.manager.active_path / "data/tcg_en.json").unlink()
        self.assertTrue(self.manager.status().legacy)
        self.assertEqual(self.manager.status().languages, ("fr",))
        stages = []
        self.assertTrue(
            self.manager.install(
                self.manifest, progress=lambda event: stages.append(event.stage)
            )
        )
        self.assertEqual(self.manager.status().version, "1.0.0")
        self.assertEqual(self.manager.status().languages, ("fr", "en"))
        self.assertIsNone(self.manager.check_update())
        self.assertTrue(self.manager.rollback())
        self.assertTrue(self.manager.status().legacy)
        self.assertEqual(self.manager.status().languages, ("fr",))
        self.assertIn("verifying", stages)

    def test_archive_corruption_preserves_installed_data(self):
        catalogues(self.manager.active_path)
        original = (self.manager.active_path / "data/pokemon.json").read_bytes()
        body = self.network[self.manifest.archive.url]
        self.network[self.manifest.archive.url] = body[:-1] + bytes([body[-1] ^ 1])
        with self.assertRaisesRegex(AssetError, "SHA-256"):
            self.manager.install(self.manifest)
        self.assertEqual(
            (self.manager.active_path / "data/pokemon.json").read_bytes(), original
        )
        self.assertTrue(self.manager.status().legacy)
        self.assertEqual(list(self.manager.data_root.glob(".assets-staging-*")), [])

    def test_per_file_corruption_is_rejected_even_with_correct_archive_digest(self):
        entries = dict(self.manifest.files)
        entries["data/pokemon.json"] = replace(
            entries["data/pokemon.json"], sha256="0" * 64
        )
        with self.assertRaisesRegex(AssetError, "checksum mismatch"):
            self.manager.install(replace(self.manifest, files=entries))
        self.assertFalse(self.manager.active_path.exists())

    def malicious_archive(self, name, *, symlink=False):
        stream = io.BytesIO()
        with ZipFile(stream, "w") as archive:
            item = ZipInfo(name)
            item.external_attr = (0o120777 if symlink else 0o100644) << 16
            archive.writestr(item, "bad")
        body = stream.getvalue()
        self.network[self.manifest.archive.url] = body
        return replace(
            self.manifest,
            archive=replace(
                self.manifest.archive,
                size=len(body),
                sha256=hashlib.sha256(body).hexdigest(),
            ),
        )

    def test_traversal_and_symlinks_are_rejected(self):
        for name, symlink in (
            ("../escape", False),
            ("/absolute", False),
            ("data/pokemon.json", True),
            ("data\\escape", False),
        ):
            with self.subTest(name=name):
                with self.assertRaises(AssetError):
                    self.manager.install(self.malicious_archive(name, symlink=symlink))
                self.assertFalse(self.manager.active_path.exists())
        self.assertFalse((self.root / "escape").exists())

    def test_cancelled_download_preserves_old_data_and_cleans_staging(self):
        catalogues(self.manager.active_path)
        cancelled = False

        def progress(event):
            nonlocal cancelled
            if event.stage == "downloading":
                cancelled = True

        self.assertFalse(
            self.manager.install(
                self.manifest, cancelled=lambda: cancelled, progress=progress
            )
        )
        self.assertTrue(self.manager.status().legacy)
        self.assertEqual(list(self.manager.data_root.glob(".assets-staging-*")), [])

    def test_cancelled_extraction_never_activates(self):
        cancelled = False

        def progress(event):
            nonlocal cancelled
            if event.stage == "extracting":
                cancelled = True

        self.assertFalse(
            self.manager.install(
                self.manifest, cancelled=lambda: cancelled, progress=progress
            )
        )
        self.assertFalse(self.manager.active_path.exists())

    def test_failed_activation_restores_previous_data(self):
        catalogues(self.manager.active_path)
        rename = Path.rename

        def failure(path, target):
            if path.name == "assets" and path.parent.name.startswith(
                ".assets-staging-"
            ):
                raise OSError("simulated failure")
            return rename(path, target)

        with patch.object(Path, "rename", failure), self.assertRaises(AssetError):
            self.manager.install(self.manifest)
        self.assertTrue(self.manager.status().legacy)

    def test_manifest_requires_supported_schema_both_languages_and_safe_paths(self):
        for change in (
            {"schema_version": 2},
            {"languages": ["fr"]},
            {"version": "garbage"},
        ):
            with self.subTest(change=change), self.assertRaises(AssetError):
                AssetManifest.from_dict({**self.manifest.to_dict(), **change})
        data = self.manifest.to_dict()
        data["files"]["../escape"] = next(iter(data["files"].values()))
        with self.assertRaises(AssetError):
            AssetManifest.from_dict(data)

    def test_legacy_fallback_only_when_channel_not_published(self):
        self.network[MANIFEST_URL] = HTTPError(
            MANIFEST_URL, 404, "unpublished", Message(), None
        )
        for prefix in ("", "assets/"):
            for directory_entries in (False, True):
                with self.subTest(prefix=prefix, directory_entries=directory_entries):
                    stream = io.BytesIO()
                    with ZipFile(stream, "w") as archive:
                        if directory_entries:
                            if prefix:
                                archive.mkdir(prefix)
                            archive.mkdir(prefix + "data/")
                        for relative in REQUIRED_FILES[:-1]:
                            archive.write(self.source / relative, prefix + relative)
                    self.network[LEGACY_URL] = stream.getvalue()
                    manager = AssetManager(
                        self.root / f"user-{bool(prefix)}-{directory_entries}",
                        opener=self.manager._opener,
                    )
                    self.assertTrue(manager.bootstrap())
                    self.assertTrue(manager.status().legacy)
                    self.assertEqual(manager.status().languages, ("fr",))
                    self.assertEqual(
                        (manager.active_path / "data/pokemon.json").read_bytes(),
                        (self.source / "data/pokemon.json").read_bytes(),
                    )
                    self.assertEqual(
                        list(manager.data_root.glob(".assets-staging-*")), []
                    )
        self.network[MANIFEST_URL] = HTTPError(
            MANIFEST_URL, 503, "unavailable", Message(), None
        )
        self.calls.clear()
        empty = AssetManager(self.root / "other-user", opener=self.manager._opener)
        with self.assertRaises(AssetError):
            empty.bootstrap()
        self.assertNotIn(LEGACY_URL, self.calls)

    def test_unwrapped_legacy_catalogue_can_upgrade_and_roll_back(self):
        self.network[MANIFEST_URL] = HTTPError(
            MANIFEST_URL, 404, "unpublished", Message(), None
        )
        self.network[LEGACY_URL] = self.network[self.manifest.archive.url]
        self.manager.data_root.mkdir()
        config = self.manager.data_root / "config.toml"
        config.write_text('app_lang = "fr"\n')
        self.assertTrue(self.manager.bootstrap())
        self.assertTrue(self.manager.status().legacy)
        self.assertEqual(self.manager.status().languages, ("fr", "en"))
        self.assertTrue(self.manager.install(self.manifest))
        self.assertEqual(self.manager.status().version, "1.0.0")
        self.assertTrue(self.manager.rollback())
        self.assertTrue(self.manager.status().legacy)
        self.assertEqual(validate_catalogues(self.manager.active_path), ("fr", "en"))
        self.assertEqual(config.read_text(), 'app_lang = "fr"\n')

    def test_legacy_layout_validation_still_rejects_unsafe_archives(self):
        self.network[MANIFEST_URL] = HTTPError(
            MANIFEST_URL, 404, "unpublished", Message(), None
        )
        for prefix in ("", "assets/"):
            for name, symlink in (
                (prefix + "../escape", False),
                (prefix + "data/../../escape", False),
                (prefix + "data\\escape", False),
                (prefix + "data/link", True),
                (prefix + "data/pokemon.json", False),
                (prefix + "../config.toml", False),
                (
                    "assets/data/unexpected.json"
                    if not prefix
                    else "data/unexpected.json",
                    False,
                ),
            ):
                with self.subTest(prefix=prefix, name=name, symlink=symlink):
                    stream = io.BytesIO()
                    with ZipFile(stream, "w") as archive:
                        for relative in REQUIRED_FILES:
                            archive.write(self.source / relative, prefix + relative)
                        item = ZipInfo(name)
                        item.external_attr = (0o120777 if symlink else 0o100644) << 16
                        warning = (
                            self.assertWarns(UserWarning)
                            if name == prefix + "data/pokemon.json"
                            else nullcontext()
                        )
                        with warning:
                            archive.writestr(item, "bad")
                    self.network[LEGACY_URL] = stream.getvalue()
                    with self.assertRaises(AssetError):
                        self.manager.bootstrap()
                    self.assertFalse(self.manager.active_path.exists())
                    self.assertEqual(
                        list(self.manager.data_root.glob(".assets-staging-*")), []
                    )
                    self.assertFalse((self.manager.data_root / "escape").exists())
                    self.assertFalse((self.manager.data_root / "config.toml").exists())

    def test_invalid_model_and_missing_english_rejected(self):
        item = pokemon()
        item["types"] = {"fr": ["Plante"], "en": ["Grass"]}
        (self.source / "data/pokemon.json").write_text(json.dumps([item]))
        with self.assertRaises(AssetError):
            validate_catalogues(self.source)
        (self.source / "data/pokemon.json").write_text(json.dumps([pokemon()]))
        (self.source / "data/tcg_en.json").unlink()
        with self.assertRaises(AssetError):
            prepare.package_catalogues(self.source, self.output, "1.0.1")

    def test_newer_version_detected_and_older_version_ignored(self):
        self.manager.install(self.manifest)
        for version, expected in (("1.1.0", True), ("1.0.0", False), ("0.9.0", False)):
            candidate = replace(self.manifest, version=version)
            self.network[MANIFEST_URL] = json.dumps(candidate.to_dict()).encode()
            self.assertEqual(self.manager.check_update() is not None, expected)

    def test_bootstrap_recovers_interrupted_promotion_without_network(self):
        catalogues(self.manager.data_root / ".assets-previous")
        self.assertTrue(self.manager.bootstrap())
        self.assertTrue(self.manager.status().installed)
        self.assertEqual(self.calls, [])

    def test_cancellation_before_activation_preserves_existing_data(self):
        catalogues(self.manager.active_path)
        cancelled = False

        def progress(event):
            nonlocal cancelled
            if event.stage == "activating":
                cancelled = True

        self.assertFalse(
            self.manager.install(
                self.manifest, cancelled=lambda: cancelled, progress=progress
            )
        )
        self.assertTrue(self.manager.status().legacy)

    def test_bulk_english_enrichment_uses_ids_and_keeps_unknown_conditions_explicit(
        self,
    ):
        first = pokemon()
        first["talents"][0]["name"] = "Provider spelling mismatch"
        first["evolution"]["next"] = [
            {"pokedex_id": 2, "name": "Herbizarre", "condition": "Niveau 16"}
        ]
        second = pokemon()
        second["pokedex_id"] = 2
        second["name"]["en"] = "Ivysaur"
        second["evolution"]["next"] = [
            {"pokedex_id": 1, "condition": "Une condition complexe indisponible"}
        ]
        csv_files = {
            "pokemon_species_names": "pokemon_species_id,local_language_id,name,genus\n1,9,Bulbasaur,Seed Pokémon\n2,9,Ivysaur,Seed Pokémon\n",
            "ability_names": "ability_id,local_language_id,name\n65,5,Engrais\n65,9,Overgrow\n",
            "pokemon_abilities": "pokemon_id,ability_id,is_hidden,slot\n1,65,0,1\n2,65,0,1\n",
            "egg_group_prose": "egg_group_id,local_language_id,name\n1,5,Monstrueux\n1,9,Monster\n",
        }
        with patch.object(
            prepare, "fetch_text", side_effect=lambda url: csv_files[Path(url).stem]
        ) as fetch:
            prepare.english_metadata([first, second])
        self.assertEqual(fetch.call_count, 4)
        self.assertEqual(first["category_en"], "Seed Pokémon")
        self.assertEqual(first["egg_groups_en"], ["Monster"])
        self.assertEqual(first["talents"][0]["name_en"], "Overgrow")
        evolution = first["evolution"]["next"][0]
        self.assertEqual(evolution["name_en"], "Ivysaur")
        self.assertEqual(evolution["condition_en"], "Level 16")
        self.assertEqual(evolution["condition"], "Niveau 16")
        self.assertEqual(second["evolution"]["next"][0]["condition_en"], "")

    def test_tyradex_normalization_keeps_type_list_and_does_not_mutate_input(self):
        raw = pokemon()
        raw["name"]["jp"] = "フシギダネ"
        raw["stats"]["atk"] = raw["stats"].pop("attack")
        raw["talents"][0]["tc"] = raw["talents"][0].pop("hidden")
        raw["sexe"] = raw.pop("sex")
        original = copy.deepcopy(raw)
        result = prepare.normalize_pokemon(raw)
        self.assertEqual(raw, original)
        self.assertIsInstance(result["types"], list)
        self.assertEqual(result["name"], {"fr": "Bulbizarre", "en": "Bulbasaur"})
        self.assertEqual(result["stats"]["attack"], 49)
        self.assertFalse(result["talents"][0]["hidden"])


if __name__ == "__main__":
    unittest.main()

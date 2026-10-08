"""Prepare and package independently versioned French/English catalogues.

No artwork is downloaded: the application caches images on demand. Use
--from-directory for a completely offline, reproducible package operation.
"""

import argparse
import copy
import csv
import io
import json
import re
from pathlib import Path
import tempfile
from typing import Any
import unicodedata
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from pokenux.services.api import tcgdex
from pokenux.services.assets import (
    AssetArchive,
    AssetFile,
    AssetManifest,
    REQUIRED_FILES,
    SCHEMA_VERSION,
    file_sha256,
    validate_catalogues,
    version_tuple,
)

POKEAPI_COMMIT = "2fe95532d27a9bf340575253aff50868319d8182"
POKEAPI_CSV = (
    f"https://raw.githubusercontent.com/PokeAPI/pokeapi/{POKEAPI_COMMIT}/data/v2/csv"
)


def fetch_text(url: str) -> str:
    """Bounded retries and timeouts for maintainer-only catalogue generation."""
    with requests.Session() as session:
        session.headers["User-Agent"] = (
            "Pokenux-assets/1 (+https://github.com/FrancoisBasset/pokenux)"
        )
        session.mount(
            "https://",
            HTTPAdapter(
                max_retries=Retry(
                    total=3, backoff_factor=1, status_forcelist=(429, 502, 503, 504)
                )
            ),
        )
        response = session.get(url, timeout=(5, 30))
        response.raise_for_status()
        return response.text


def normalized(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize(
            "NFKD", value.replace("œ", "oe").replace("Œ", "OE")
        ).casefold()
        if character.isalnum()
    )


def english_metadata(pokemon: list[dict[str, Any]]) -> None:
    """Use four upstream CSVs, avoiding a request for every Pokémon or ability."""

    def rows(name):
        return list(
            csv.DictReader(io.StringIO(fetch_text(f"{POKEAPI_CSV}/{name}.csv")))
        )

    species = {
        int(row["pokemon_species_id"]): row
        for row in rows("pokemon_species_names")
        if row["local_language_id"] == "9"
    }

    def translations(name, key):
        records = rows(name)
        english = {
            row[key]: row["name"] for row in records if row["local_language_id"] == "9"
        }
        return {
            normalized(row["name"]): english[row[key]]
            for row in records
            if row["local_language_id"] == "5" and row[key] in english
        }

    ability_rows = rows("ability_names")
    ability_english = {
        row["ability_id"]: row["name"]
        for row in ability_rows
        if row["local_language_id"] == "9"
    }
    abilities = {
        normalized(row["name"]): ability_english[row["ability_id"]]
        for row in ability_rows
        if row["local_language_id"] == "5" and row["ability_id"] in ability_english
    }
    ability_ids = {}
    for row in rows("pokemon_abilities"):
        ability_ids.setdefault(int(row["pokemon_id"]), []).append(
            (ability_english.get(row["ability_id"], ""), row["is_hidden"] == "1")
        )

    def ability_name(value):
        # Tyradex sometimes combines abilities or distinguishes gender forms.
        suffix = re.search(r"\s*\((Femelle|M[aâ]le)\)$", value, re.IGNORECASE)
        base = value[: suffix.start()] if suffix else value
        translated = [abilities.get(normalized(part), "") for part in base.split("/")]
        if not all(translated):
            return ""
        result = "/".join(translated)
        if suffix:
            result += (
                " (Female)" if suffix.group(1).casefold() == "femelle" else " (Male)"
            )
        return result

    eggs = translations("egg_group_prose", "egg_group_id")
    names = {item["pokedex_id"]: item["name"]["en"] for item in pokemon}
    for item in pokemon:
        item["category_en"] = species.get(item["pokedex_id"], {}).get("genus", "")
        item["egg_groups_en"] = [
            eggs.get(normalized(group), "") for group in item.get("egg_groups") or []
        ]
        for talent in item.get("talents", []):
            talent["name_en"] = ability_name(talent["name"])
        known = {
            talent["name_en"] for talent in item.get("talents", []) if talent["name_en"]
        }
        for talent in item.get("talents", []):
            if not talent["name_en"]:
                candidates = {
                    name
                    for name, hidden in ability_ids.get(item["pokedex_id"], [])
                    if hidden == talent.get("hidden", False)
                    and name not in known
                    and name
                }
                if len(candidates) == 1:
                    talent["name_en"] = candidates.pop()
                    known.add(talent["name_en"])
        for direction in ("pre", "next"):
            for evolution in (item.get("evolution") or {}).get(direction) or []:
                evolution["name_en"] = names.get(evolution["pokedex_id"], "")
                # Unknown conditions stay visibly unavailable rather than being
                # falsely labelled as an English translation.
                if not evolution.get("condition_en"):
                    condition = str(evolution.get("condition") or "")
                    level = re.fullmatch(r"Niveau (\d+)", condition)
                    evolution["condition_en"] = (
                        f"Level {level.group(1)}"
                        if level
                        else {
                            "Echange": "Trade",
                            "Échange": "Trade",
                            "Bonheur": "Friendship",
                        }.get(condition, "")
                    )


def normalize_pokemon(raw: dict[str, Any]) -> dict[str, Any]:
    """Keep the model's list of types; normalize only Tyradex field aliases."""
    pokemon = copy.deepcopy(raw)
    pokemon["name"] = {lang: pokemon["name"][lang] for lang in ("fr", "en")}
    for talent in pokemon["talents"]:
        if "tc" in talent:
            talent["hidden"] = talent.pop("tc")
    for old, new in {
        "atk": "attack",
        "def": "defense",
        "spe_atk": "special_attack",
        "spe_def": "special_defense",
        "vit": "speed",
    }.items():
        if old in pokemon["stats"]:
            pokemon["stats"][new] = pokemon["stats"].pop(old)
    pokemon["evolution"] = pokemon.get("evolution") or {
        "pre": None,
        "next": [],
        "mega": None,
    }
    if "sexe" in pokemon:
        pokemon["sex"] = pokemon.pop("sexe")
    for unused in ("level_100", "formes", "next"):
        pokemon.pop(unused, None)
    return pokemon


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )


def prepare_pokemon(output_dir: Path) -> None:
    pokemon = [
        normalize_pokemon(item)
        for item in json.loads(fetch_text("https://tyradex.app/api/v1/pokemon"))
        if item["pokedex_id"] != 0
    ]
    english_metadata(pokemon)
    write_json(output_dir / "pokemon.json", pokemon)
    types = [
        {lang: item["name"][lang] for lang in ("fr", "en")}
        for item in json.loads(fetch_text("https://tyradex.app/api/v1/types"))
    ]
    write_json(output_dir / "types.json", types)
    generations = [
        str(item["generation"])
        for item in json.loads(fetch_text("https://tyradex.app/api/v1/gen"))
    ]
    write_json(output_dir / "generations.json", generations)


def prepare_tcg_json(
    languages: tuple[str, ...] = ("fr", "en"),
    *,
    include_card_details: bool = False,
    output_dir: Path = Path("src/pokenux/assets/data"),
):
    """Build TCG catalogues, optionally fetching every card's search metadata.

    Set responses only contain card summaries. A complete offline index needs
    one extra API request per card, enabled explicitly with --tcg-card-details.
    Existing metadata in summaries is retained without these extra requests.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    for language in languages:
        series = []

        for serie_resume in tcgdex.fetch_all_series(language):
            serie_details = tcgdex.fetch_serie_by_id(language, serie_resume["id"])

            serie: dict[str, Any] = {
                "id": serie_details["id"],
                "name": serie_details["name"],
                "logo": serie_details.get("logo"),
                "release_date": serie_details.get("releaseDate", ""),
                "sets": [],
            }

            for set_resume in serie_details.get("sets", []):
                set_details = tcgdex.fetch_set_by_id(language, set_resume["id"])

                card_set: dict[str, Any] = {
                    "id": set_details["id"],
                    "name": set_details["name"],
                    "logo": None,
                    "release_date": set_details.get("releaseDate", ""),
                    "abbreviation": None,
                    "symbol": None,
                    "legal": {
                        "standard": False,
                        "expanded": False,
                        **(set_details.get("legal") or {}),
                    },
                    "cards": [],
                    "serie_id": serie["id"],
                }

                if set_details.get("logo"):
                    card_set["logo"] = set_details["logo"] + ".png"
                if set_details.get("symbol"):
                    card_set["symbol"] = set_details["symbol"] + ".png"
                abbreviation = set_details.get("abbreviation") or {}
                card_set["abbreviation"] = abbreviation.get("official")

                for card_resume in set_details.get("cards", []):
                    card_details = dict(card_resume)
                    if include_card_details:
                        card_details.update(
                            tcgdex.fetch_card_by_id(language, card_resume["id"])
                        )
                    card_set["cards"].append(
                        {
                            "id": card_details["id"],
                            "name": card_details["name"],
                            "image": card_details.get("image"),
                            "set_id": card_set["id"],
                            "hp": card_details.get("hp"),
                            "types": card_details.get("types") or [],
                            "illustrator": card_details.get("illustrator") or "",
                            "rarity": card_details.get("rarity") or "",
                            "category": card_details.get("category") or "",
                            "variants": card_details.get("variants") or {},
                            "local_id": card_details.get("local_id")
                            or card_details.get("localId")
                            or "",
                            "details_loaded": include_card_details
                            or bool(card_details.get("details_loaded"))
                            or all(
                                field in card_details
                                for field in ("hp", "types", "illustrator")
                            ),
                        }
                    )

                serie["sets"].append(card_set)

            series.append(serie)

        with (output_dir / f"tcg_{language}.json").open("w", encoding="utf-8") as f:
            json.dump(series, f, ensure_ascii=False)


def package_catalogues(
    source: Path, output: Path, version: str, *, archive_url: str | None = None
) -> AssetManifest:
    version_tuple(version)
    source = (
        source.parent
        if source.name == "data" and (source / "pokemon.json").is_file()
        else source
    )
    validate_catalogues(source)
    output.mkdir(parents=True, exist_ok=True)
    name = f"pokenux-assets-{version}.zip"
    archive = output / name
    files = {
        name: AssetFile(file_sha256(source / name), (source / name).stat().st_size)
        for name in REQUIRED_FILES
    }
    # Fixed timestamps and member order make packaging identical source bytes
    # deterministic. Provider data changes still require a new content version.
    with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=9) as bundle:
        for relative in sorted(files):
            item = ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            item.compress_type = ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            bundle.writestr(item, (source / relative).read_bytes())
    url = (
        archive_url
        or f"https://github.com/FrancoisBasset/pokenux/releases/download/assets-v{version}/{name}"
    )
    manifest = AssetManifest(
        version,
        SCHEMA_VERSION,
        ("fr", "en"),
        AssetArchive(name, url, file_sha256(archive), archive.stat().st_size),
        files,
    )
    manifest = AssetManifest.from_dict(manifest.to_dict())
    write_json(output / "assets-manifest.json", manifest.to_dict())
    (output / "SHA256SUMS").write_text(
        "".join(
            f"{file_sha256(output / filename)}  {filename}\n"
            for filename in (name, "assets-manifest.json")
        ),
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        required=True,
        help="Independent asset content version, e.g. 1.0.0.",
    )
    parser.add_argument("--output", type=Path, default=Path("dist/assets"))
    parser.add_argument(
        "--from-directory",
        type=Path,
        help="Package existing assets/ or data/ without API calls.",
    )
    parser.add_argument(
        "--archive-url", help="HTTPS location of the immutable archive."
    )
    parser.add_argument(
        "--enrich-english",
        action="store_true",
        help="Enrich --from-directory with four PokeAPI CSV downloads; leave source files unchanged.",
    )
    parser.add_argument(
        "--tcg-card-details",
        action="store_true",
        help="Fresh preparation only: fetch full metadata per card (tens of thousands of extra requests).",
    )
    args = parser.parse_args()
    version_tuple(args.version)
    with tempfile.TemporaryDirectory(prefix="pokenux-assets-prepare-") as temporary:
        staged = Path(temporary)
        data = staged / "data"
        data.mkdir()
        if args.from_directory:
            source = args.from_directory
            if source.name == "data" and (source / "pokemon.json").is_file():
                source = source.parent
            for relative in REQUIRED_FILES:
                (staged / relative).write_bytes((source / relative).read_bytes())
            if args.enrich_english:
                pokemon = json.loads(
                    (data / "pokemon.json").read_text(encoding="utf-8")
                )
                english_metadata(pokemon)
                write_json(data / "pokemon.json", pokemon)
        else:
            print("Preparing Pokémon metadata (Tyradex + PokeAPI)…", flush=True)
            prepare_pokemon(data)
            print("Preparing French and English TCG catalogues (TCGdex)…", flush=True)
            prepare_tcg_json(
                output_dir=data, include_card_details=args.tcg_card_details
            )
        manifest = package_catalogues(
            staged, args.output, args.version, archive_url=args.archive_url
        )
        print(
            f"Assets {manifest.version}: {manifest.archive.size:,} bytes; FR + EN; {args.output.resolve()}"
        )


if __name__ == "__main__":
    main()

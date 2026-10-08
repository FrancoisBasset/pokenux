"""Offline command-line checks also exercised against the installed wheel in CI."""

from contextlib import redirect_stdout
from importlib import import_module, metadata, resources
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pokenux import __version__
from pokenux.main import check_installation
from pokenux.paths import assets_are_missing, data_directory


class CommandLineTests(unittest.TestCase):
    def run_cli(self, argument: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = dict(os.environ)
            environment.update(
                HOME=str(root / "home"),
                XDG_DATA_HOME=str(root / "data"),
                TERM="dumb",
            )
            for name in ("DISPLAY", "WAYLAND_DISPLAY"):
                environment.pop(name, None)
            # Fail on network access or imports that would initialize user data.
            script = """
import runpy
import sys

def reject_network(event, arguments):
    if event in {'socket.connect', 'socket.getaddrinfo'}:
        raise RuntimeError('Network is forbidden in inspection commands')

sys.addaudithook(reject_network)
sys.argv = ['pokenux', sys.argv[1]]
try:
    runpy.run_module('pokenux', run_name='__main__')
finally:
    assert 'pokenux.services.user_data' not in sys.modules
    assert 'pokenux.textual.pokenux' not in sys.modules
    assert 'textual_image.widget' not in sys.modules
"""
            result = subprocess.run(
                [sys.executable, "-c", script, argument],
                env=environment,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            self.assertEqual(list(root.iterdir()), [], "Inspection modified user data")
            return result

    def test_help_is_available_before_first_launch(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--check", result.stdout)
        self.assertIn("--version", result.stdout)

    def test_version_matches_installed_metadata(self):
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip(), f"Pokénux {metadata.version('pokenux')}"
        )
        self.assertEqual(__version__, metadata.version("pokenux"))

    def test_check_is_offline_and_catalogue_is_optional(self):
        result = self.run_cli("--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Packaged stylesheets and translations", result.stdout)
        self.assertIn("Local catalogue absent", result.stdout)
        self.assertIn("Installation ready.", result.stdout)

    def test_unknown_argument_does_not_launch_ui(self):
        result = self.run_cli("--unknown-option")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments", result.stderr)

    def test_missing_dependency_fails_check(self):
        def import_without_requests(name: str):
            if name == "requests":
                raise ModuleNotFoundError("requests missing")
            return import_module(name)

        output = io.StringIO()
        with (
            patch("pokenux.main.import_module", side_effect=import_without_requests),
            redirect_stdout(output),
        ):
            self.assertEqual(check_installation(), 1)
        self.assertIn("FAIL requests", output.getvalue())

    def test_missing_package_resources_fail_check(self):
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with (
                patch("pokenux.main.resources.files", return_value=Path(directory)),
                redirect_stdout(output),
            ):
                self.assertEqual(check_installation(), 1)
            self.assertIn("FAIL CSS quiz_view.css", output.getvalue())
            self.assertIn("FAIL Translation fr", output.getvalue())

    def test_invalid_translation_fails_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = resources.files("pokenux")
            shutil.copytree(
                str(package.joinpath("textual", "css")), root / "textual" / "css"
            )
            shutil.copytree(str(package.joinpath("locales")), root / "locales")
            (root / "locales" / "fr" / "LC_MESSAGES" / "pokenux.mo").write_bytes(
                b"not a translation"
            )
            output = io.StringIO()
            with (
                patch("pokenux.main.resources.files", return_value=root),
                redirect_stdout(output),
            ):
                self.assertEqual(check_installation(), 1)
            self.assertIn("FAIL Translation fr", output.getvalue())


class DataPathTests(unittest.TestCase):
    def test_xdg_absolute_path_is_used_without_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {"XDG_DATA_HOME": str(root / "custom")}):
                self.assertEqual(data_directory(), root / "custom" / "pokenux")
            self.assertEqual(list(root.iterdir()), [])

    def test_unset_or_relative_xdg_preserves_default(self):
        home = Path("/example/home")
        for configured in ("", "relative/path"):
            with (
                self.subTest(configured=configured),
                patch.dict(os.environ, {"XDG_DATA_HOME": configured}),
                patch("pokenux.paths.Path.home", return_value=home),
            ):
                self.assertEqual(
                    data_directory(), home / ".local" / "share" / "pokenux"
                )

    def test_catalogue_requires_pokemon_files_and_any_tcg_language(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = Path(directory) / "assets"
            self.assertTrue(assets_are_missing(assets))
            data = assets / "data"
            data.mkdir(parents=True)
            for name in ("pokemon.json", "generations.json", "types.json"):
                (data / name).write_text("[]", encoding="utf-8")
            self.assertTrue(assets_are_missing(assets))
            (data / "tcg_fr.json").write_text("[]", encoding="utf-8")
            self.assertFalse(assets_are_missing(assets))
            (data / "types.json").unlink()
            self.assertTrue(assets_are_missing(assets))


if __name__ == "__main__":
    unittest.main()

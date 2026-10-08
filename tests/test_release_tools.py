"""Regression checks for metadata, release checksums and package contents."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.check_dist import REQUIRED, check
from scripts.release import checksums, release_info, verify_checksums


class ReleaseMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "pyproject.toml").write_text('[project]\nversion = "1.1.0"\n')
        (self.root / "uv.lock").write_text(
            '[[package]]\nname = "pokenux"\nversion = "1.1.0"\n'
        )
        self.changelog = self.root / "CHANGELOG.md"
        self.changelog.write_text(
            "# Changelog\n\n## [1.1.0] - 2026-10-08\n\n### Added\n- Packages.\n\n## [1.0.0] - 2026-08-11\n- Old content.\n"
        )

    def test_notes_match_tag_and_exclude_previous_release(self):
        version, notes = release_info(self.root, "v1.1.0")
        self.assertEqual(version, "1.1.0")
        self.assertIn("Packages.", notes)
        self.assertNotIn("Old content", notes)

    def test_tag_must_match_version(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            release_info(self.root, "v9.0.0")

    def test_undated_changelog_only_allowed_during_development(self):
        self.changelog.write_text("## [1.1.0] - Unreleased\n\n- Packages.\n")
        with self.assertRaisesRegex(ValueError, "Date the changelog"):
            release_info(self.root, "v1.1.0")
        self.assertEqual(release_info(self.root, allow_unreleased=True)[0], "1.1.0")

    def test_lockfile_version_cannot_lag_behind(self):
        (self.root / "uv.lock").write_text(
            '[[package]]\nname = "pokenux"\nversion = "1.0.0"\n'
        )
        with self.assertRaisesRegex(ValueError, "Refresh uv.lock"):
            release_info(self.root)

    def test_empty_notes_are_rejected(self):
        self.changelog.write_text(
            "## [1.1.0] - 2026-10-08\n\n## [1.0.0] - 2026-08-11\nOlder\n"
        )
        with self.assertRaisesRegex(ValueError, "describe the changes"):
            release_info(self.root)


class ReleaseChecksumTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.asset = self.root / "pokenux_1.1.0-1_amd64.deb"
        self.asset.write_bytes(b"release artifact fixture")

    def test_manifest_is_deterministic_and_ignores_intermediate_files(self):
        (self.root / "notes.md").write_text("not an asset")
        manifest = checksums(self.root)
        previous = manifest.read_bytes()
        self.assertEqual(checksums(self.root).read_bytes(), previous)
        self.assertNotIn(b"notes.md", previous)
        verify_checksums(self.root)

    def test_modified_asset_is_rejected(self):
        checksums(self.root)
        self.asset.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
            verify_checksums(self.root)

    def test_checksum_manifest_cannot_read_outside_release_directory(self):
        (self.root / "SHA256SUMS").write_text("0" * 64 + "  ../outside.deb\n")
        with self.assertRaisesRegex(ValueError, "unsafe filename"):
            verify_checksums(self.root)

    def test_duplicate_manifest_entries_are_rejected(self):
        manifest = checksums(self.root)
        manifest.write_text(manifest.read_text() * 2)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            verify_checksums(self.root)


class DistributionContentsTests(unittest.TestCase):
    def test_wheel_requires_stylesheets_and_translations(self):
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "pokenux-1.1.0-py3-none-any.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                for name in REQUIRED:
                    archive.writestr(name, b"fixture")
            with redirect_stdout(StringIO()):
                check(wheel)
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("pokenux/__main__.py", b"fixture")
            with self.assertRaisesRegex(ValueError, "missing runtime resources"):
                check(wheel)

    def test_wheel_excludes_downloaded_game_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "pokenux-1.1.0-py3-none-any.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                for name in REQUIRED:
                    archive.writestr(name, b"fixture")
                archive.writestr("pokenux/assets/data/pokemon.json", b"[]")
            with self.assertRaisesRegex(ValueError, "game data"):
                check(wheel)


if __name__ == "__main__":
    unittest.main()

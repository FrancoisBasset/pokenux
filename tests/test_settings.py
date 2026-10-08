"""Independent locale preferences, atomic persistence and live settings controls."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from textual.app import App, ComposeResult
from textual.widgets import Button, Label, Select, Static
import tomlkit

from pokenux.services import user_data
from pokenux.services.assets import AssetStatus
from pokenux.textual.utils import i18n
from pokenux.textual.views.parameters_view import ParametersView


class SettingsFixture:
    def setUp(self):
        super().setUp()
        temporary = self.enterContext(TemporaryDirectory())
        self.root = Path(temporary)
        self.enterContext(
            patch.multiple(
                user_data,
                path=self.root,
                config_path=self.root / "config.toml",
                assets_path=self.root / "assets",
                config_file=tomlkit.document(),
                config_load_error=None,
            )
        )
        self.enterContext(
            patch.object(user_data, "data_directory", return_value=self.root)
        )
        self.addCleanup(i18n.set_language, i18n.get_language())
        user_data.init()
        i18n.set_language("en")


class PreferenceTests(SettingsFixture, unittest.TestCase):
    def test_independent_languages_survive_restart(self):
        user_data.save_preferences(app_lang="fr", pokemon_lang="en", tcg_lang="fr")
        user_data.init()
        self.assertEqual(
            (
                user_data.get_app_lang(),
                user_data.get_pokemon_lang(),
                user_data.get_tcg_lang(),
            ),
            ("fr", "en", "fr"),
        )

    def test_invalid_values_are_normalized_and_unknown_settings_preserved(self):
        user_data.config_path.write_text(
            'app_lang = "de"\npokemon_lang = "fr"\ntcg_lang = 42\ncustom = "kept"\n'
        )
        user_data.init()
        self.assertEqual(user_data.get_app_lang(), "en")
        self.assertEqual(user_data.get_pokemon_lang(), "fr")
        self.assertEqual(user_data.get_tcg_lang(), "en")
        user_data.save_config()
        self.assertEqual(
            tomlkit.parse(user_data.config_path.read_text())["custom"], "kept"
        )
        with self.assertRaises(ValueError):
            user_data.set_app_lang("")

    def test_corrupt_file_is_not_overwritten_during_load(self):
        damaged = "app_lang = [broken"
        user_data.config_path.write_text(damaged)
        user_data.init()
        self.assertIsNotNone(user_data.config_load_error)
        self.assertEqual(user_data.get_app_lang(), "en")
        self.assertEqual(user_data.config_path.read_text(), damaged)

    def test_failed_atomic_save_keeps_disk_and_memory_preferences(self):
        user_data.save_preferences(app_lang="en", pokemon_lang="fr", tcg_lang="en")
        before = user_data.config_path.read_bytes()
        with patch.object(
            user_data.os, "replace", side_effect=PermissionError("read only")
        ):
            with self.assertRaises(PermissionError):
                user_data.save_preferences(
                    app_lang="fr", pokemon_lang="en", tcg_lang="fr"
                )
        self.assertEqual(user_data.config_path.read_bytes(), before)
        self.assertEqual(user_data.get_app_lang(), "en")
        self.assertEqual(list(self.root.glob(".config-*")), [])

    def test_text_and_legacy_gettext_follow_same_locale(self):
        for language, expected in (("fr", "Bonjour Ada"), ("en", "Hello Ada")):
            i18n.set_language(language)
            self.assertEqual(
                i18n.text("Bonjour {name}", "Hello {name}", name="Ada"), expected
            )
            self.assertEqual(
                i18n.trans("quit"), "Quitter" if language == "fr" else "Quit"
            )


class PreservedActivity(Static):
    def __init__(self):
        super().__init__("", id="activity")
        self.score = 1200
        self.refreshes = 0

    async def refresh_language(self):
        self.refreshes += 1
        self.update(i18n.text("Partie en cours", "Game in progress"))


class SettingsApp(App):
    def compose(self) -> ComposeResult:
        yield ParametersView()
        yield PreservedActivity()


class SettingsViewTests(SettingsFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.manager_type = self.enterContext(
            patch("pokenux.textual.views.parameters_view.AssetManager")
        )
        self.manager = self.manager_type.return_value
        self.manager.status.return_value = AssetStatus(
            languages=("fr",), legacy=True, installed=True
        )

    async def test_save_refreshes_open_activity_without_reset_and_shows_fallback(self):
        app = SettingsApp()
        async with app.run_test(size=(110, 44)) as pilot:
            await pilot.pause()
            self.assertIn(
                "EN catalogue is missing",
                str(app.query_one("#catalogue_warning", Label).render()),
            )
            app.query_one("#app_lang", Select).value = "fr"
            app.query_one("#pokemon_lang", Select).value = "en"
            app.query_one("#tcg_lang", Select).value = "fr"
            await pilot.pause()
            await app.query_one(ParametersView).action_save()
            await pilot.pause()
            self.assertEqual(user_data.get_app_lang(), "fr")
            self.assertEqual(user_data.get_pokemon_lang(), "en")
            self.assertEqual(user_data.get_tcg_lang(), "fr")
            self.assertIn(
                "enregistrées", str(app.query_one("#settings_status", Label).render())
            )
            activity = app.query_one(PreservedActivity)
            self.assertEqual(activity.score, 1200)
            self.assertEqual(activity.refreshes, 1)
            self.assertEqual(str(activity.render()), "Partie en cours")
            self.assertTrue(app.query_one("#save_button", Button).disabled)

    async def test_narrow_layout_and_reset_keep_valid_choices(self):
        app = SettingsApp()
        async with app.run_test(size=(48, 30)) as pilot:
            await pilot.pause()
            view = app.query_one(ParametersView)
            self.assertTrue(view.has_class("narrow"))
            app.query_one("#pokemon_lang", Select).value = "fr"
            await pilot.pause()
            view.reset_changes()
            await pilot.pause()
            for key in ("app_lang", "pokemon_lang", "tcg_lang"):
                select = app.query_one(f"#{key}", Select)
                self.assertEqual(select.value, "en")
                self.assertLessEqual(select.region.right, 48)
            self.assertEqual(view.max_scroll_x, 0)

    async def test_update_error_is_recoverable_and_check_remains_enabled(self):
        self.manager.check_update.side_effect = OSError("offline")
        app = SettingsApp()
        async with app.run_test(size=(110, 44)) as pilot:
            view = app.query_one(ParametersView)
            view.check_assets()
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertFalse(app.query_one("#check_assets", Button).disabled)
            self.assertFalse(app.query_one("#cancel_assets", Button).display)
            self.assertIn(
                "offline", str(app.query_one("#assets_status", Label).render())
            )


if __name__ == "__main__":
    unittest.main()

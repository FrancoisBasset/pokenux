"""Independent UI/data languages, stable filters and asynchronous TCG isolation."""

from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from textual.app import App, ComposeResult
from textual.widgets import Input, Label, Select, TabbedContent, TabPane

from pokenux.services import localization, tcg_library, user_data
from pokenux.services.assets import AssetStatus
from pokenux.textual.views.tcg_view import CatalogueScope, TcgView
from pokenux.textual.widgets.remote_image import RemoteImage
from pokenux.textual.views.parameters_view import ParametersView
from pokenux.textual.pokenux import Pokenux


def catalogue(language: str, *, detailed: bool = True) -> list[dict]:
    return [
        {
            "id": "base",
            "name": "Base",
            "sets": [
                {
                    "id": "base1",
                    "name": "Set de Base" if language == "fr" else "Base Set",
                    "serie_id": "base",
                    "release_date": "1999-01-09",
                    "cards": [
                        {
                            "id": "base1-1",
                            "name": "Florizarre" if language == "fr" else "Venusaur",
                            "set_id": "base1",
                            "hp": 100,
                            "types": ["Plante" if language == "fr" else "Grass"],
                            "details_loaded": detailed,
                        }
                    ],
                }
            ],
        }
    ]


class CatalogueFixture:
    def setUp(self):
        super().setUp()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.assets = self.root / "assets"
        (self.assets / "data").mkdir(parents=True)
        for lang in ("fr", "en"):
            self.write_catalogue(lang)
        self.addCleanup(patch.stopall)
        patch.object(user_data, "path", self.root).start()
        patch.object(user_data, "assets_path", self.assets).start()
        patch.object(user_data, "get_tcg_lang", return_value="en").start()
        self.old_language = localization.language()
        self.addCleanup(localization.set_language, self.old_language)
        # Restore the catalogue snapshot too: other tests may use the installed data.
        old_series, old_status = tcg_library.series, tcg_library.get_language_status()
        old_catalogues, old_details = (
            tcg_library._catalogues.copy(),
            tcg_library._details.copy(),
        )

        def restore():
            tcg_library.series = old_series
            tcg_library._language_status = old_status
            tcg_library._catalogues = old_catalogues
            tcg_library._details = old_details

        self.addCleanup(restore)
        tcg_library._catalogues.clear()
        tcg_library._details.clear()
        localization.set_language("en")
        tcg_library.set_language("en")

    def write_catalogue(self, language: str, detailed: bool = True):
        (self.assets / "data" / f"tcg_{language}.json").write_text(
            json.dumps(catalogue(language, detailed=detailed)), encoding="utf-8"
        )


class TcgLanguageTests(CatalogueFixture, unittest.TestCase):
    def test_catalogue_language_is_independent_of_interface(self):
        localization.set_language("en")
        tcg_library.set_language("fr")
        self.assertEqual(tcg_library.search_cards()[0].name, "Florizarre")
        localization.set_language("fr")
        tcg_library.set_language("en")
        self.assertEqual(tcg_library.search_cards()[0].name, "Venusaur")
        self.assertEqual(tcg_library.translate_type("Plante", "fr", "en"), "Grass")

    def test_missing_catalogue_reports_actual_language(self):
        (self.assets / "data" / "tcg_en.json").unlink()
        status = tcg_library.set_language("en")
        self.assertEqual(status.active, "fr")
        self.assertIn("FR", tcg_library.get_language_status().warning)
        self.assertIn("unavailable", tcg_library.get_language_status().warning)
        localization.set_language("fr")
        self.assertIn("indisponible", tcg_library.get_language_status().warning)
        with self.assertRaises(ValueError):
            tcg_library.set_language("../en")

    def test_inflight_details_stay_in_the_requested_language(self):
        for lang in ("fr", "en"):
            self.write_catalogue(lang, detailed=False)
        tcg_library.reload_catalogues()
        tcg_library.set_language("fr")

        def fetch(language, card_id):
            tcg_library.set_language("en")
            return {
                "id": card_id,
                "name": "Florizarre" if language == "fr" else "Venusaur",
                "set": {"id": "base1"},
            }

        with patch.object(
            tcg_library.tcgdex, "fetch_card_by_id", side_effect=fetch
        ) as remote:
            french = tcg_library.fetch_card_details("base1-1", language="fr")
            english = tcg_library.fetch_card_details("base1-1", language="en")
        self.assertEqual(french.name, "Florizarre")
        self.assertEqual(english.name, "Venusaur")
        self.assertEqual([call.args[0] for call in remote.call_args_list], ["fr", "en"])
        self.assertEqual(
            tcg_library.get_card_by_id("base1-1", language="fr").name, "Florizarre"
        )

    def test_explicit_search_does_not_use_another_tabs_language(self):
        tcg_library.set_language("fr")
        tcg_library.set_language("en")
        result = tcg_library.search_cards_online(name="florizarre", language="fr")
        self.assertEqual([card.name for card in result.cards], ["Florizarre"])
        self.assertEqual(tcg_library.get_language_status().active, "en")

    def test_asset_versions_have_distinct_persistent_cache_namespaces(self):
        from pokenux.services.assets import AssetManager

        legacy = tcg_library._cache_path("fr", "card", "base1-1")
        with patch.object(
            AssetManager, "status", return_value=AssetStatus(version="1.0.0")
        ):
            first = tcg_library._cache_path("fr", "card", "base1-1")
        with patch.object(
            AssetManager, "status", return_value=AssetStatus(version="1.1.0")
        ):
            second = tcg_library._cache_path("fr", "card", "base1-1")
        self.assertEqual(len({legacy, first, second}), 3)


class TcgApp(App):
    CSS_PATH = "../src/pokenux/textual/css/tcg_view.css"

    def compose(self) -> ComposeResult:
        yield TcgView()


class TcgSettingsApp(App):
    CSS_PATH = "../src/pokenux/textual/css/tcg_view.css"
    action_show_parameters = Pokenux.action_show_parameters

    def compose(self) -> ComposeResult:
        with TabbedContent(id="tabbed_content"):
            yield TabPane("TCG", TcgView(), id="tcg")
            yield TabPane("Home", id="new_tab_tab")

    def on_mount(self):
        self.tabbed_content = self.query_one(TabbedContent)

    def action_close_tab(self, tab_id):
        pass


class TcgLiveLanguageTests(CatalogueFixture, unittest.IsolatedAsyncioTestCase):
    async def test_opening_settings_and_background_refresh_keep_settings_active(self):
        with patch.object(RemoteImage, "_download"):
            app = TcgSettingsApp()
            async with app.run_test(size=(110, 40)) as pilot:
                await pilot.pause()
                view = app.query_one(TcgView)
                view.query_one("#tcg_name", Input).focus()
                # Leave focus notifications queued when the new pane is opened.
                await app.action_show_parameters()
                await pilot.pause()
                self.assertEqual(app.tabbed_content.active, "parameters")
                self.assertIsNotNone(app.query_one(ParametersView))
                localization.set_language("fr")
                view.refresh_language()
                view._focus_on_show()
                await pilot.pause()
                self.assertEqual(app.tabbed_content.active, "parameters")

    async def test_live_switch_keeps_scope_search_and_type_filter(self):
        with patch.object(RemoteImage, "_download"):
            app = TcgApp()
            async with app.run_test(size=(140, 44)) as pilot:
                await pilot.pause()
                view = app.query_one(TcgView)
                view._scope = CatalogueScope("base", "base1")
                view.query_one("#tcg_type", Select).value = "Grass"
                view.query_one("#tcg_name", Input).value = "base"
                localization.set_language("fr")
                with patch.object(user_data, "get_tcg_lang", return_value="fr"):
                    view.refresh_language()
                    await pilot.pause()
                self.assertEqual(view._scope, CatalogueScope("base", "base1"))
                self.assertEqual(view.query_one("#tcg_name", Input).value, "base")
                self.assertEqual(view.query_one("#tcg_type", Select).value, "Plante")
                self.assertEqual(
                    str(view.query_one("#tcg_title", Label).content), "▤  CARTES TCG"
                )
                localization.set_language("en")
                with patch.object(user_data, "get_tcg_lang", return_value="fr"):
                    view.refresh_language()
                    await pilot.pause()
                self.assertEqual(
                    str(view.query_one("#tcg_title", Label).content), "▤  TCG CARDS"
                )
                self.assertEqual(view._sets["base1"].name, "Set de Base")
                self.assertEqual(view.query_one("#tcg_type", Select).value, "Plante")


if __name__ == "__main__":
    unittest.main()

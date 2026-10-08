"""First launch remains interactive after failed catalogue downloads."""

import unittest
from unittest.mock import patch

from textual.app import App
from textual.widgets import Button, Label

from pokenux.services import localization
from pokenux.services.assets import AssetError, AssetProgress, AssetStatus
from pokenux.textual.screens.fetching_screen import FetchingScreen


class SetupApp(App):
    result = None

    def on_mount(self):
        self.push_screen(FetchingScreen(), self.completed)

    def completed(self, result):
        self.result = result


class FirstRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_download_can_retry_and_successfully_finish(self):
        self.addCleanup(localization.set_language, localization.language())
        localization.set_language("fr")
        calls = []

        def download(*, cancelled, progress):
            calls.append(True)
            progress(AssetProgress("downloading", 5, 10))
            if len(calls) == 1:
                raise AssetError("HTTP 503")
            progress(AssetProgress("verifying", 5, 5))
            return True

        with (
            patch("pokenux.services.user_data.download_assets", side_effect=download),
            patch("pokenux.textual.screens.fetching_screen.AssetManager") as manager,
        ):
            manager.return_value.status.return_value = AssetStatus(
                version="1.0.0", installed=True, languages=("fr", "en")
            )
            app = SetupApp()
            async with app.run_test(size=(80, 26)) as pilot:
                await pilot.pause()
                screen = app.screen
                self.assertIsInstance(screen, FetchingScreen)
                self.assertTrue(screen.query_one("#fetch_retry", Button).display)
                self.assertIn(
                    "réessaie", str(screen.query_one("#fetch_error", Label).content)
                )
                self.assertIsNone(app.result)
                await pilot.click("#fetch_retry")
                await pilot.pause()
                self.assertIs(app.result, True)
                self.assertEqual(len(calls), 2)

    async def test_quit_during_failed_setup_is_available(self):
        with patch(
            "pokenux.services.user_data.download_assets",
            side_effect=AssetError("offline"),
        ):
            app = SetupApp()
            async with app.run_test(size=(64, 24)) as pilot:
                await pilot.pause()
                await pilot.click("#fetch_cancel")
                await pilot.pause()
                self.assertIs(app.result, False)


if __name__ == "__main__":
    unittest.main()

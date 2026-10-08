"""Language changes preserve bought cards, game currency and partial openings."""

from pathlib import Path
import random
import unittest

from textual.app import App, ComposeResult
from textual.widgets import Button, Label, TabbedContent, TabPane

from pokenux.services.games.booster_simulator import (
    SimulatorService,
    finish_label,
    format_euros,
)
from pokenux.textual.utils import i18n
from pokenux.textual.views.simulator_view import SimulatorView
from test_simulator import catalogue


def translated_catalogue(prefix):
    series = catalogue()
    for serie in series:
        serie.name = prefix + " series"
        for card_set in serie.sets:
            card_set.name = prefix + " set"
            for card in card_set.cards:
                card.name = prefix + " " + card.id
    return series


class CatalogueLanguageTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(i18n.set_language, i18n.get_language())

    def test_catalogue_switch_changes_display_without_rewriting_saved_cards(self):
        service = SimulatorService(
            translated_catalogue("French"), ":memory:", rng=random.Random(7)
        )
        self.addCleanup(service.close)
        with service._transaction() as connection:
            connection.execute("UPDATE simulator_account SET balance=10000 WHERE id=1")
        opening = service.buy_and_open("sv01")
        before = service.snapshot()
        saved = list(
            service._connection.execute(
                "SELECT card_id, payload, value, quantity FROM simulator_inventory"
            )
        )
        rng_state = service._rng.getstate()
        service.set_catalogue(translated_catalogue("English"))
        self.assertEqual(service.snapshot(), before)
        self.assertEqual(service._rng.getstate(), rng_state)
        self.assertEqual(
            list(
                service._connection.execute(
                    "SELECT card_id, payload, value, quantity FROM simulator_inventory"
                )
            ),
            saved,
        )
        self.assertTrue(
            all(card.name.startswith("English") for card in service.collection())
        )
        self.assertTrue(all(card.name.startswith("French") for card in opening.cards))
        displayed = service.display_card(opening.cards[0])
        self.assertEqual(
            (displayed.card_id, displayed.value, displayed.finish),
            (opening.cards[0].card_id, opening.cards[0].value, opening.cards[0].finish),
        )

    def test_display_translates_money_and_finish_without_changing_finish_keys(self):
        i18n.set_language("fr")
        self.assertEqual(format_euros(599), "5,99 €")
        self.assertEqual(finish_label("Holographique"), "Holographique")
        i18n.set_language("en")
        self.assertEqual(format_euros(599), "€5.99")
        self.assertEqual(finish_label("Holographique"), "Holographic")


class SimulatorLanguageApp(App):
    CSS_PATH = [
        Path(__file__).parents[1] / "src/pokenux/textual/css/simulator_view.css"
    ]

    def __init__(self, service):
        super().__init__()
        self.service = service

    def compose(self) -> ComposeResult:
        with TabbedContent(id="activities"):
            with TabPane("Boosters", id="boosters"):
                yield SimulatorView(self.service)
            with TabPane("Settings", id="settings"):
                yield Button("Settings focus", id="settings_focus")


class SimulatorLanguageViewTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_translation_keeps_partial_booster_and_inactive_tab(self):
        self.addCleanup(i18n.set_language, i18n.get_language())
        i18n.set_language("fr")
        service = SimulatorService(catalogue(), ":memory:", rng=random.Random(7))
        self.addCleanup(service.close)
        with service._transaction() as connection:
            connection.execute("UPDATE simulator_account SET balance=10000 WHERE id=1")
        app = SimulatorLanguageApp(service)
        async with app.run_test(size=(105, 40)) as pilot:
            await pilot.pause()
            view = app.query_one(SimulatorView)
            view.buy_booster()
            view.reveal_next()
            view.reveal_next()
            await pilot.pause()
            opening, before = view._opening, service.snapshot()
            activities = app.query_one("#activities", TabbedContent)
            activities.active = "settings"
            app.query_one("#settings_focus", Button).focus()
            await pilot.pause()
            i18n.set_language("en")
            view.refresh_language()
            await pilot.pause()
            self.assertIs(view._opening, opening)
            self.assertEqual(view._revealed, 2)
            self.assertEqual(service.snapshot(), before)
            self.assertEqual(activities.active, "settings")
            self.assertEqual(app.focused.id, "settings_focus")
            self.assertIn("Balance:", str(app.query_one("#sim_wallet", Label).render()))
            self.assertIn(
                "cards revealed",
                str(app.query_one("#sim_opening_status", Label).render()),
            )
            self.assertEqual(
                view.query_one("#sim_sections", TabbedContent)
                .get_tab("sim_shop_tab")
                .label_text,
                "Shop",
            )


if __name__ == "__main__":
    unittest.main()

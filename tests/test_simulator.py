"""Offline checks for card metadata and transactional game currency."""

from pathlib import Path
import random
import tempfile
import unittest

from pokenux.models.tcg.card import Card
from pokenux.models.tcg.serie import Serie
from pokenux.services.games.booster_simulator import SimulatorError, SimulatorService


def catalogue() -> list[Serie]:
    cards = [
        {
            "id": f"sv01-{index}",
            "name": f"Test {index}",
            "rarity": rarity,
            "variants": {
                "normal": rarity != "Rare",
                "holo": rarity == "Rare",
                "reverse": True,
            },
        }
        for index, rarity in enumerate(["Common"] * 8 + ["Uncommon"] * 5 + ["Rare"] * 3)
    ]
    return [
        Serie.from_dict(
            {
                "id": "sv",
                "name": "Test series",
                "sets": [
                    {
                        "id": "sv01",
                        "name": "Test set",
                        "releaseDate": "2023-03-31",
                        "cards": cards,
                    }
                ],
            }
        )
    ]


class CardMetadataTests(unittest.TestCase):
    def test_legacy_card_infers_set_without_fabricating_rarity(self):
        card = Card.from_dict({"id": "sv01-1", "name": "Test"})
        self.assertEqual(card.set_id, "sv01")
        self.assertEqual(card.rarity, "")
        self.assertEqual(card.variants, {})
        self.assertFalse(card.details_loaded)

    def test_invalid_variant_flags_are_not_treated_as_true(self):
        card = Card.from_dict(
            {
                "id": "sv01-1",
                "name": "Test",
                "hp": "invalid",
                "variants": {
                    "normal": True,
                    "holo": False,
                    "reverse": "false",
                    "firstEdition": 1,
                },
            }
        )
        self.assertEqual(card.variants, {"normal": True, "holo": False})
        self.assertIsNone(card.hp)

    def test_full_card_keeps_nested_set_and_official_rarity(self):
        card = Card.from_dict(
            {
                "id": "sv01-1",
                "name": "Test",
                "set": {"id": "sv01"},
                "hp": "120",
                "category": "Pokemon",
                "rarity": "Rare",
            }
        )
        self.assertEqual(card.hp, 120)
        self.assertEqual(card.rarity, "Rare")
        self.assertTrue(card.details_loaded)


class EconomyTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.service = SimulatorService(
            catalogue(), ":memory:", rng=random.Random(7), clock=lambda: self.now
        )
        self.addCleanup(self.service.close)

    def fund_booster(self):
        price = self.service.extensions[0].price
        while self.service.snapshot().balance < price:
            self.service.work()
            self.now += 3.0

    def test_work_cooldown_preserves_balance_on_rejection(self):
        before = self.service.snapshot()
        worked = self.service.work()
        self.assertEqual(worked.state.balance, before.balance + worked.earned)
        with self.assertRaises(SimulatorError):
            self.service.work()
        self.assertEqual(self.service.snapshot().balance, worked.state.balance)
        self.now += 2.0
        self.assertEqual(self.service.work().state.clicks, 2)

    def test_unaffordable_upgrade_rolls_back(self):
        before = self.service.snapshot()
        with self.assertRaises(SimulatorError):
            self.service.upgrade_work()
        self.assertEqual(self.service.snapshot(), before)

    def test_pack_purchase_and_sale_balance_inventory(self):
        self.fund_booster()
        before = self.service.snapshot()
        opened = self.service.buy_and_open("sv01")
        self.assertEqual(len(opened.cards), 10)
        self.assertEqual(opened.state.balance, before.balance - opened.offer.price)
        self.assertEqual(opened.state.boosters_opened, 1)
        self.assertEqual(opened.state.cards_owned, 10)
        self.assertEqual(sum(card.quantity for card in self.service.collection()), 10)
        self.assertEqual(sum(card.finish == "Reverse" for card in opened.cards), 2)
        card = opened.cards[0]
        earned = self.service.sell(card.card_id)
        self.assertEqual(earned, card.value)
        self.assertEqual(self.service.snapshot().balance, opened.state.balance + earned)
        self.assertEqual(self.service.snapshot().cards_owned, 9)

    def test_invalid_purchase_and_sale_are_atomic(self):
        before = self.service.snapshot()
        with self.assertRaises(SimulatorError):
            self.service.buy_and_open("unknown")
        for amount in (0, -1, True):
            with self.subTest(amount=amount), self.assertRaises(SimulatorError):
                self.service.sell("unknown", amount)
        self.assertEqual(self.service.snapshot(), before)

    def test_incomplete_metadata_cannot_be_purchased(self):
        self.service.set_cards("sv01", [Card("sv01-1", "Test", "", "sv01")])
        before = self.service.snapshot()
        self.assertFalse(self.service.metadata_ready("sv01"))
        with self.assertRaises(SimulatorError):
            self.service.buy_and_open("sv01")
        self.assertEqual(self.service.snapshot(), before)

    def test_saved_currency_survives_reopening(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "save.sqlite3"
            first = SimulatorService([], database, clock=lambda: self.now)
            try:
                expected = first.work().state
            finally:
                first.close()
            second = SimulatorService([], database, clock=lambda: self.now)
            try:
                self.assertEqual(second.snapshot(), expected)
            finally:
                second.close()


if __name__ == "__main__":
    unittest.main()

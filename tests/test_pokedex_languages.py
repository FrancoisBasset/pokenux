"""Independent interface/data languages and stable Pokédex state."""

from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from textual.app import App, ComposeResult
from textual.widgets import Checkbox, Input, Label, Select, TabbedContent

from pokenux.models.pokemon.pokemon import Pokemon
from pokenux.models.tcg.serie import Serie
import pokenux.services
from pokenux.services import user_data

# Importing the catalogue in a fresh CI home must not depend on real assets.
with (
    patch.object(user_data, "get_all_pokemon", return_value=[]),
    patch.object(user_data, "get_all_types", return_value=[]),
):
    from pokenux.services import pokedex
    from pokenux.textual.utils import i18n
    from pokenux.textual.widgets.pokemon_details import PokemonDetails
    from pokenux.textual.widgets.pokemon_list import PokemonList
    from pokenux.textual.views.pokedex_view import PokedexView


TYPES = [{"fr": "Électrik", "en": "Electric"}, {"fr": "Normal", "en": "Normal"}]


def pokemon(number=25, fr="Pikachu", en="Pikachu"):
    return Pokemon.from_dict(
        {
            "pokedex_id": number,
            "generation": 1 if number == 25 else 2,
            "name": {"fr": fr, "en": en},
            "category": "Pokémon Souris",
            "category_en": "Mouse Pokémon",
            "sprites": {"regular": "", "shiny": "", "gmax": None},
            "types": [{"name": "Électrik", "image": ""}],
            "talents": [{"name": "Statik", "name_en": "Static", "hidden": False}],
            "stats": dict.fromkeys(
                (
                    "hp",
                    "attack",
                    "defense",
                    "special_attack",
                    "special_defense",
                    "speed",
                ),
                50,
            ),
            "resistances": [],
            "evolution": {"pre": [], "next": [], "mega": []},
            "height": "0,4 m",
            "weight": "6,0 kg",
            "egg_groups": ["Terrestre", "Féerique"],
            "egg_groups_en": ["Field", "Fairy"],
            "sex": None,
            "catch_rate": 190,
        }
    )


class CatalogueLanguageTests(unittest.TestCase):
    def setUp(self):
        self.pikachu = pokemon()
        self.mareep = pokemon(179, "Wattouat", "Mareep")
        self.catalogue = [self.pikachu, self.mareep]
        for target, value in (
            ("all_pokemon", self.catalogue),
            ("_type_catalogue", TYPES),
        ):
            context = patch.object(pokedex, target, value)
            context.start()
            self.addCleanup(context.stop)

    def test_english_and_french_type_filters_use_same_ids(self):
        for value in ("Électrik", "electrik", "Electric", "electric"):
            with self.subTest(value=value):
                self.assertEqual(
                    pokedex.filter_pokemon([], [value], []), self.catalogue
                )
        self.assertEqual(pokedex.pokemon_types(self.pikachu, "en"), ["Electric"])

    def test_names_sort_in_selected_data_language(self):
        self.assertEqual(
            pokedex.filter_pokemon([], [], [], sort_by="by_name", language="fr"),
            self.catalogue,
        )
        self.assertEqual(
            pokedex.filter_pokemon([], [], [], sort_by="by_name", language="en"),
            self.catalogue[::-1],
        )

    def test_search_crosses_names_and_ignores_accents(self):
        self.assertEqual(
            pokedex.filter_pokemon([], [], [], search="wattóuat", language="en"),
            [self.mareep],
        )
        self.assertEqual(
            pokedex.filter_pokemon([], [], [], search="MAREEP", language="fr"),
            [self.mareep],
        )

    def test_localized_metadata_and_legacy_defaults(self):
        self.assertEqual(self.pikachu.localized_category("en"), "Mouse Pokémon")
        self.assertEqual(self.pikachu.talents[0].name_en, "Static")
        self.assertEqual(self.pikachu.egg_groups_en, ["Field", "Fairy"])
        self.pikachu.category_en = ""
        self.assertEqual(self.pikachu.localized_category("en"), "")

    def test_related_cards_follow_tcg_language_independently(self):
        english = [
            Serie.from_dict(
                {
                    "id": "sv",
                    "name": "Series",
                    "sets": [
                        {
                            "id": "sv01",
                            "name": "Set",
                            "cards": [{"id": "sv01-1", "name": "Mareep"}],
                        }
                    ],
                }
            )
        ]
        requested = ["fr"]
        library = SimpleNamespace(series=[])
        library.get_language_status = lambda: SimpleNamespace(requested=requested[0])

        def select_language(language):
            requested[0] = language
            library.series = english

        library.set_language = select_language
        with (
            patch.object(pokenux.services, "tcg_library", library, create=True),
            patch.object(user_data, "get_tcg_lang", return_value="en"),
            patch.object(user_data, "get_pokemon_lang", return_value="fr"),
        ):
            cards = PokemonDetails()._cards(self.mareep)
        self.assertEqual(requested, ["en"])
        self.assertEqual([card.name for card in cards], ["Mareep"])

    def test_evolution_name_resolves_through_current_catalogue(self):
        previous = i18n.get_language()
        self.addCleanup(i18n.set_language, previous)
        i18n.set_language("en")
        with patch.object(user_data, "get_pokemon_lang", return_value="en"):
            self.assertEqual(
                PokemonDetails._evolution_name({"pokedex_id": 179, "name": "Wattouat"}),
                "Mareep",
            )
            self.assertIn(
                "English",
                PokemonDetails._evolution_condition({"condition": "Niveau 30"}),
            )


class PokedexHarness(App):
    CSS_PATH = [
        str(
            Path(__file__).resolve().parents[1]
            / "src/pokenux/textual/css/pokedex_view.css"
        )
    ]

    def compose(self) -> ComposeResult:
        yield PokedexView()


class LiveLanguageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.languages = {"app": "fr", "pokemon": "fr", "tcg": "fr"}
        self.catalogue = [pokemon(), pokemon(179, "Wattouat", "Mareep")]
        self.old_language = i18n.get_language()
        self.addCleanup(i18n.set_language, self.old_language)
        for context in (
            patch.object(
                user_data,
                "get_pokemon_lang",
                side_effect=lambda: self.languages["pokemon"],
            ),
            patch.object(
                user_data, "get_tcg_lang", side_effect=lambda: self.languages["tcg"]
            ),
            patch.object(user_data, "get_all_types", return_value=TYPES),
            patch.object(user_data, "get_all_generations", return_value=["1", "2"]),
            patch.object(pokedex, "all_pokemon", self.catalogue),
            patch.object(pokedex, "_type_catalogue", TYPES),
            patch.object(PokemonDetails, "_cards", return_value=[]),
        ):
            context.start()
            self.addCleanup(context.stop)
        i18n.set_language("fr")

    async def test_refresh_preserves_search_filters_selection_and_detail_tab(self):
        app = PokedexHarness()
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause()
            view = app.query_one(PokedexView)
            view.query_one("#type_Electric", Checkbox).value = True
            view.query_one("#pokemon_sort", Select).value = "by_name"
            await pilot.pause()
            listing = view.query_one(PokemonList)
            await listing.select_index(1)
            details = view.query_one(PokemonDetails)
            await pilot.pause()
            details.query_one(TabbedContent).active = "pokemon_stats"
            await pilot.pause()
            self.languages["pokemon"] = "en"
            i18n.set_language("en")
            await view.refresh_language()
            await pilot.pause()
            self.assertEqual(view.active_types, ["Electric"])
            self.assertTrue(view.query_one("#type_Electric", Checkbox).value)
            self.assertEqual(listing.selected_pokemon.pokedex_id, 179)
            self.assertEqual(listing.selected_index, 0)
            self.assertEqual(view.query_one("#pokemon_sort", Select).value, "by_name")
            self.assertEqual(details.query_one(TabbedContent).active, "pokemon_stats")
            self.assertEqual(
                str(details.query_one("#details_title", Label).render()), "Mareep"
            )
            self.assertIn(
                "NATIONAL", str(view.query_one("#pokedex_title", Label).render())
            )
            view.query_one("#pokemon_input", Input).value = "wattouat"
            await pilot.pause()
            i18n.set_language("fr")
            await view.refresh_language()
            await pilot.pause()
            self.assertEqual(view.query_one("#pokemon_input", Input).value, "wattouat")
            self.assertEqual(
                str(details.query_one("#details_title", Label).render()), "Mareep"
            )
            self.assertIn(
                "GÉNÉRATION",
                str(details.query_one("#details_generation", Label).render()),
            )

    async def test_english_interface_keeps_french_pokemon_metadata(self):
        i18n.set_language("en")
        app = PokedexHarness()
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause()
            details = app.query_one(PokemonDetails)
            self.assertEqual(
                str(details.query_one("#details_category", Label).render()),
                "Pokémon Souris",
            )
            self.assertIn(
                "Électrik", str(details.query_one("#details_types", Label).render())
            )
            self.assertIn(
                "Abilities",
                " ".join(str(label.render()) for label in details.query(Label)),
            )


if __name__ == "__main__":
    unittest.main()

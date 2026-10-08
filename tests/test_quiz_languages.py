"""Quiz localization keeps answers, scores and the in-progress question intact."""

from pathlib import Path
import random
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from textual.app import App, ComposeResult
from textual.widgets import Button, Input, Label

from pokenux.models.pokemon.pokemon_name import PokemonName
from pokenux.models.tcg.serie import Serie
from pokenux.services import localization, user_data
from pokenux.services.games import pokemon_quiz, tcg_quiz
from pokenux.services.games.quiz import QuestionState
from pokenux.textual.utils import i18n
from pokenux.textual.views.quiz_view import QuizView


def catalogue():
    return [
        SimpleNamespace(
            pokedex_id=133,
            name=PokemonName(en="Eevee", fr="Évoli"),
            generation=1,
            height="0,3 m",
            weight="6,5 kg",
            types=[{"name": "Normal"}],
            sprites=SimpleNamespace(regular=""),
            evolution=SimpleNamespace(pre=[], next=[]),
        )
    ]


class QuizLanguageRulesTests(unittest.TestCase):
    def setUp(self):
        previous = localization.language()
        self.addCleanup(localization.set_language, previous)

    def test_mode_titles_follow_language_after_import(self):
        localization.set_language("fr")
        self.assertEqual(pokemon_quiz.get_modes()[1].title, "Anagramme")
        localization.set_language("en")
        self.assertEqual(pokemon_quiz.get_modes()[1].title, "Anagram")
        self.assertEqual(tcg_quiz.get_modes()[0].title, "Name the card")

    def test_interface_prompt_and_pokemon_names_are_independent(self):
        localization.set_language("en")
        question = pokemon_quiz.generate_question(
            "number_to_name", catalogue(), language="fr"
        )
        self.assertIn("Which Pokémon", question.prompt)
        self.assertEqual(question.targets[0].label, "Évoli")
        state = QuestionState(question)
        self.assertEqual(state.submit("Eevee").message, "Correct!")

    def test_translation_does_not_change_rng_or_answers(self):
        localization.set_language("fr")
        french = pokemon_quiz.generate_question(
            "anagram", catalogue(), language="en", rng=random.Random(5)
        )
        localization.set_language("en")
        english = pokemon_quiz.generate_question(
            "anagram", catalogue(), language="en", rng=random.Random(5)
        )
        self.assertEqual(french.targets, english.targets)
        self.assertEqual(
            french.prompt.rpartition(" : ")[2], english.prompt.rpartition(" : ")[2]
        )
        self.assertIn("The name", english.hint)

    def test_tcg_hp_accepts_both_suffixes_in_english_interface(self):
        localization.set_language("en")
        series = [
            Serie.from_dict(
                {
                    "id": "sv",
                    "name": "Test",
                    "sets": [
                        {
                            "id": "sv01",
                            "name": "Set",
                            "cards": [{"id": "sv01-1", "name": "Eevee", "hp": 70}],
                        }
                    ],
                }
            )
        ]
        question = tcg_quiz.generate_question("tcg_hp", series)
        self.assertIn("How many HP", question.prompt)
        self.assertTrue(QuestionState(question).submit("70 PV").correct)
        self.assertTrue(QuestionState(question).submit("70 HP").correct)


class QuizHarness(App):
    CSS_PATH = [
        str(
            Path(__file__).resolve().parents[1]
            / "src/pokenux/textual/css/quiz_view.css"
        )
    ]

    def compose(self) -> ComposeResult:
        yield QuizView(pokemon=catalogue(), series=[])


class QuizLiveLanguageTests(unittest.IsolatedAsyncioTestCase):
    async def test_switch_keeps_completed_round_and_score_then_generates_english(self):
        previous = i18n.get_language()
        self.addCleanup(i18n.set_language, previous)
        i18n.set_language("fr")
        language = ["fr"]
        with patch.object(
            user_data, "get_pokemon_lang", side_effect=lambda: language[0]
        ):
            app = QuizHarness()
            async with app.run_test(size=(120, 45)) as pilot:
                view = app.query_one(QuizView)
                view.start_mode("anagram")
                for _ in range(20):
                    await pilot.pause()
                    if view._state is not None:
                        break
                self.assertIsNotNone(view._state)
                original = view._state
                view.query_one("#quiz_answer", Input).value = "Évoli"
                view.submit_answer()
                self.assertEqual(view._session.points, 100)
                self.assertTrue(original.complete)
                language[0] = "en"
                i18n.set_language("en")
                view.refresh_language()
                await pilot.pause()
                self.assertIs(view._state, original)
                self.assertEqual(view._session.completed, 1)
                self.assertEqual(view._session.points, 100)
                self.assertIn(
                    "Anagram", str(view.query_one("#quiz_mode_anagram", Button).label)
                )
                self.assertIn(
                    "Streak", str(view.query_one("#quiz_streak", Label).render())
                )
                self.assertEqual(
                    str(view.query_one("#quiz_submit", Button).label), "Submit ↵"
                )
                view.action_next_question()
                for _ in range(20):
                    await pilot.pause()
                    if view._state is not None and view._state is not original:
                        break
                self.assertIn("Unscramble", view._state.question.prompt)
                self.assertEqual(view._state.question.targets[0].label, "Eevee")
                self.assertEqual(view._session.points, 100)


if __name__ == "__main__":
    unittest.main()

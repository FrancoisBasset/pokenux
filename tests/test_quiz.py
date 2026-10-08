"""User-visible quiz rules, independent of a downloaded Pokémon catalogue."""

import unittest

from pokenux.services.games.quiz import (
    QuestionState,
    QuizQuestion,
    QuizTarget,
    normalize_answer,
)
from pokenux.services.games.quiz_session import QuizSession


def question(*names: str, kind: str = "single") -> QuestionState:
    return QuestionState(
        QuizQuestion(
            "test",
            "Qui est ce Pokémon ?",
            tuple(QuizTarget(str(index), name, ()) for index, name in enumerate(names)),
            answer_kind=kind,
        )
    )


def answered() -> QuestionState:
    state = question("Évoli")
    state.submit("evoli")
    return state


class AnswerTests(unittest.TestCase):
    def test_names_ignore_accents_case_and_punctuation(self):
        state = question("M. Mime")
        self.assertTrue(state.submit("m mime").correct)
        self.assertEqual(normalize_answer("ÉVOLI"), "evoli")
        self.assertEqual(normalize_answer("00025"), "25")

    def test_nidoran_sexes_remain_distinct(self):
        state = question("Nidoran♀")
        self.assertFalse(state.submit("Nidoran♂").correct)
        self.assertTrue(state.submit("Nidoran F").correct)

    def test_blank_answer_does_not_cost_a_mistake(self):
        state = question("Évoli")
        self.assertEqual(state.submit("   ").status, "empty")
        self.assertEqual(state.mistakes, 0)

    def test_collection_duplicate_does_not_advance_or_penalize(self):
        state = question("Évoli", "Pikachu", kind="collection")
        self.assertEqual(state.submit("evoli").status, "progress")
        self.assertEqual(state.submit("ÉVOLI").status, "duplicate")
        self.assertEqual(len(state.found), 1)
        self.assertEqual(state.mistakes, 0)
        self.assertTrue(state.submit("Pikachu").complete)

    def test_collection_unknown_answer_counts_once(self):
        state = question("Évoli", "Pikachu", kind="collection")
        result = state.submit("evoli, inconnu, pikachu")
        self.assertTrue(result.complete)
        self.assertEqual(state.mistakes, 1)

    def test_ordering_requires_every_name_once(self):
        state = question("Pichu", "Pikachu", "Raichu", kind="order")
        self.assertFalse(state.submit("Pichu, Pikachu, Pikachu").correct)
        self.assertFalse(state.submit("Raichu, Pikachu, Pichu").correct)
        self.assertTrue(state.submit("Pichu → Pikachu → Raichu").correct)

    def test_reveal_does_not_award_a_correct_answer(self):
        state = question("Évoli")
        state.reveal()
        self.assertTrue(state.complete)
        self.assertFalse(state.succeeded)
        self.assertEqual(state.submit("evoli").status, "finished")


class ScoringTests(unittest.TestCase):
    def test_clean_streak_bonus_is_capped(self):
        session = QuizSession(length=8)
        awarded = [session.record(answered()).points for _ in range(8)]
        self.assertEqual(awarded, [100, 120, 140, 160, 180, 200, 200, 200])
        self.assertEqual(session.points, sum(awarded))
        self.assertEqual(session.best_streak, 8)
        self.assertTrue(session.finished)

    def test_hint_breaks_streak_and_halves_points(self):
        session = QuizSession()
        session.record(answered())
        self.assertEqual(session.record(answered(), used_hint=True).points, 50)
        self.assertEqual(session.streak, 0)
        self.assertEqual(session.record(answered()).points, 100)

    def test_mistake_penalty_has_a_floor(self):
        state = question("Évoli")
        for _ in range(6):
            state.submit("wrong")
        state.submit("evoli")
        self.assertEqual(QuizSession().record(state).points, 25)

    def test_record_is_idempotent_and_snapshot_is_immutable(self):
        session = QuizSession(length=1)
        state = answered()
        original = session.record(state)
        state.mistakes = 10
        self.assertIs(session.record(state, skipped=True), original)
        self.assertEqual(session.completed, 1)
        self.assertEqual(session.points, 100)
        self.assertEqual(original.mistakes, 0)

    def test_incomplete_and_extra_questions_are_rejected(self):
        session = QuizSession(length=1)
        with self.assertRaises(ValueError):
            session.record(question("Évoli"))
        session.record(answered())
        with self.assertRaises(ValueError):
            session.record(answered())

    def test_skipped_answer_scores_zero_and_reset_clears_history(self):
        session = QuizSession()
        session.record(answered(), skipped=True)
        self.assertEqual(session.points, 0)
        self.assertEqual(session.correct, 0)
        session.reset()
        self.assertEqual(session.completed, 0)
        self.assertEqual(session.best_streak, 0)
        self.assertFalse(session.finished)


if __name__ == "__main__":
    unittest.main()

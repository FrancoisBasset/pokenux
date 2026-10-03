"""Free-text Pokémon and TCG quizzes with a menu and reusable sessions."""

from dataclasses import replace
import random

from textual import events, on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Button, Input, Label, Select, TabbedContent, TabPane
from textual.worker import get_current_worker

from pokenux.models.pokemon.pokemon import Pokemon
from pokenux.models.tcg.serie import Serie
from pokenux.services import user_data
from pokenux.services.api.tcgdex import TCGdexError
from pokenux.services.games import pokemon_quiz, tcg_quiz
from pokenux.services.games.quiz import (
    AnswerResult,
    QuestionState,
    QuizMode,
    QuizQuestion,
    QuizUnavailableError,
)
from pokenux.textual.widgets.quiz_image import QuizImage


class QuizView(Vertical):
    BINDINGS = [
        Binding("escape", "quiz_menu", "Menu Quiz"),
        Binding("ctrl+n", "next_question", "Suivante"),
    ]

    class QuestionReady(Message):
        def __init__(self, revision: int, question: QuizQuestion) -> None:
            super().__init__()
            self.revision, self.question = revision, question

    class QuestionFailed(Message):
        def __init__(self, revision: int, message: str) -> None:
            super().__init__()
            self.revision, self.message = revision, message

    def __init__(
        self,
        pokemon: list[Pokemon] | None = None,
        series: list[Serie] | None = None,
    ) -> None:
        super().__init__()
        if pokemon is None:
            from pokenux.services import pokedex

            pokemon = pokedex.all_pokemon
        if series is None:
            from pokenux.services import tcg_library

            if tcg_library.get_language_status().requested != user_data.get_tcg_lang():
                tcg_library.set_language(user_data.get_tcg_lang())
            series = tcg_library.series
        self._pokemon = list(pokemon)
        self._series = list(series)
        self._cached_tcg_series: list[Serie] | None = None
        self._modes = {mode.id: mode for mode in [*pokemon_quiz.MODES, *tcg_quiz.MODES]}
        self._mode: QuizMode | None = None
        self._state: QuestionState | None = None
        self._length = 10
        self._missing_letters: int | None = None
        self._completed = self._correct = self._mistakes = self._hints = 0
        self._recorded = False
        self._revision = 0
        self._question_image: QuizImage | None = None
        self._image_ready = True
        self._image_failed = False
        self._ready = False
        self._seen_questions: set[tuple[str, str | None, tuple[str, ...]]] = set()

    def compose(self) -> ComposeResult:
        with Vertical(id="quiz_menu"):
            yield Label("◈  QUIZ POKÉDEX & TCG", id="quiz_heading")
            yield Label(
                "Choisis un jeu. Toutes les réponses se font au clavier, sans QCM.",
                classes="quiz-note",
            )
            with Horizontal(id="quiz_settings"):
                with Vertical(classes="quiz-setting"):
                    yield Label("Durée de la partie")
                    yield Select(
                        [
                            ("5 questions", 5),
                            ("10 questions", 10),
                            ("20 questions", 20),
                            ("Entraînement sans fin", 0),
                        ],
                        value=10,
                        allow_blank=False,
                        id="quiz_length",
                    )
                with Vertical(classes="quiz-setting"):
                    yield Label("Lettres manquantes")
                    yield Select(
                        [("Nombre variable", 0)] + [(str(n), n) for n in range(1, 9)],
                        value=0,
                        allow_blank=False,
                        id="quiz_missing_letters",
                        tooltip="Utilisé uniquement pour le jeu « Compléter le nom ».",
                    )
            with TabbedContent(id="quiz_categories"):
                with TabPane("Pokédex", id="quiz_pokedex_modes"):
                    with VerticalScroll(classes="quiz-mode-scroll"):
                        with Grid(classes="quiz-mode-grid"):
                            for mode in pokemon_quiz.MODES:
                                yield self._mode_button(mode)
                with TabPane("TCG", id="quiz_tcg_modes"):
                    with VerticalScroll(classes="quiz-mode-scroll"):
                        with Grid(classes="quiz-mode-grid"):
                            for mode in tcg_quiz.MODES:
                                yield self._mode_button(mode)
            yield Label(
                "Casse, accents, espaces, tirets et ponctuation ignorés. Entrée pour valider.",
                id="quiz_normalization_note",
            )

        with Vertical(id="quiz_game"):
            with Horizontal(id="quiz_game_heading"):
                yield Label("", id="quiz_game_title", markup=False)
                yield Button("← Menu", id="quiz_back")
            yield Label("", id="quiz_score", markup=False)
            with VerticalScroll(id="quiz_question_panel"):
                yield Label("", id="quiz_prompt", markup=False)
                yield Vertical(id="quiz_art_slot")
                yield Label("", id="quiz_hint", markup=False)
                yield Label("", id="quiz_found", markup=False)
                yield Label("", id="quiz_solution", markup=False)
            yield Label("", id="quiz_answer_help", markup=False)
            yield Input(placeholder="Ta réponse…", id="quiz_answer", disabled=True)
            with Horizontal(id="quiz_actions"):
                yield Button("Valider", id="quiz_submit", variant="primary")
                yield Button("Indice", id="quiz_show_hint")
                yield Button("Solution", id="quiz_reveal")
                yield Button("Passer", id="quiz_skip")
                yield Button("Suivante →", id="quiz_next", disabled=True)
            with Horizontal(id="quiz_feedback_bar"):
                yield Label("", id="quiz_feedback", markup=False)
                yield Button("Réessayer", id="quiz_retry", disabled=True)

        with VerticalScroll(id="quiz_summary"):
            yield Label("PARTIE TERMINÉE", id="quiz_summary_title")
            yield Label("", id="quiz_summary_score", markup=False)
            yield Label("", id="quiz_summary_details", markup=False)
            yield Button("Rejouer ce quiz", id="quiz_replay", variant="primary")
            yield Button("Choisir un autre quiz", id="quiz_choose")

    @staticmethod
    def _mode_button(mode: QuizMode) -> Button:
        button = Button(
            f"{mode.title}\n{mode.description}",
            id=f"quiz_mode_{mode.id}",
            classes="quiz-mode-button",
        )
        button.tooltip = mode.description
        return button

    def on_mount(self) -> None:
        self._ready = True
        self._show_panel("quiz_menu")
        self.call_after_refresh(self._focus_visible)

    def on_show(self) -> None:
        if self._ready:
            self.call_after_refresh(self._focus_visible)

    def _focus_visible(self) -> None:
        if not self.is_mounted or self.region.height <= 0:
            return
        if self.query_one("#quiz_menu").display:
            self.query_one("#quiz_length", Select).focus()
        elif self.query_one("#quiz_summary").display:
            self.query_one("#quiz_replay", Button).focus()
        elif self._state and self._state.complete:
            self.query_one("#quiz_next", Button).focus()
        elif self._state and self._image_ready:
            self.query_one("#quiz_answer", Input).focus()
        else:
            self.query_one("#quiz_back", Button).focus()

    def on_resize(self, event: events.Resize) -> None:
        self.set_class(event.size.width < 90, "narrow")
        self.set_class(event.size.height < 25, "short")
        if self._ready:
            self.query_one("#quiz_art_slot").styles.height = max(
                6, min(24, event.size.height - 13)
            )

    def _show_panel(self, identifier: str) -> None:
        for panel in ("quiz_menu", "quiz_game", "quiz_summary"):
            self.query_one(f"#{panel}").display = panel == identifier

    @on(Button.Pressed, ".quiz-mode-button")
    def choose_mode(self, event: Button.Pressed) -> None:
        if event.button.id:
            self.start_mode(event.button.id.removeprefix("quiz_mode_"))

    def start_mode(self, mode_id: str) -> None:
        self._mode = self._modes[mode_id]
        self._length = int(str(self.query_one("#quiz_length", Select).value))
        missing = int(str(self.query_one("#quiz_missing_letters", Select).value))
        self._missing_letters = missing or None
        self._completed = self._correct = self._mistakes = self._hints = 0
        self._seen_questions.clear()
        self._cached_tcg_series = None
        self.query_one("#quiz_game_title", Label).update(self._mode.title)
        self._show_panel("quiz_game")
        self._next_question()

    def _next_question(self) -> None:
        if self._length and self._completed >= self._length:
            self._show_summary()
            return
        if self._mode is None:
            return
        self._revision += 1
        self.workers.cancel_group(self, "quiz-question")
        self._state = None
        self._recorded = False
        self._image_ready = False
        self._image_failed = False
        self._question_image = None
        self.query_one("#quiz_prompt", Label).update("Préparation de la question…")
        self.query_one("#quiz_art_slot").display = False
        for identifier in ("quiz_hint", "quiz_found", "quiz_solution"):
            self.query_one(f"#{identifier}").display = False
        answer = self.query_one("#quiz_answer", Input)
        answer.value = ""
        self._set_answer_enabled(False)
        for identifier in ("quiz_show_hint", "quiz_reveal", "quiz_skip", "quiz_next"):
            self.query_one(f"#{identifier}", Button).disabled = True
        self.query_one("#quiz_next", Button).label = "Suivante →"
        self.query_one("#quiz_retry", Button).display = False
        self._feedback("Chargement…")
        self._update_score()
        self._generate_question(self._revision, self._mode.id, self._missing_letters)

    @work(thread=True, exclusive=True, group="quiz-question", exit_on_error=False)
    def _generate_question(
        self, revision: int, mode_id: str, missing: int | None
    ) -> None:
        worker = get_current_worker()
        try:
            mode = self._modes[mode_id]
            question: QuizQuestion | None = None
            for attempt in range(12):
                if worker.is_cancelled:
                    return
                if mode.category == "pokedex":
                    language = user_data.get_pokemon_lang()
                    question = pokemon_quiz.generate_question(
                        mode_id,
                        self._pokemon,
                        language=language if language in ("fr", "en") else "fr",
                        missing_letters=missing,
                    )
                else:
                    question = self._generate_tcg_question(mode_id)
                if (
                    self._question_key(question) not in self._seen_questions
                    or attempt == 11
                ):
                    break
            if question is not None and not worker.is_cancelled:
                self.post_message(self.QuestionReady(revision, question))
        except (QuizUnavailableError, TCGdexError, OSError, ValueError) as error:
            if not worker.is_cancelled:
                self.post_message(self.QuestionFailed(revision, str(error)))

    @staticmethod
    def _question_key(
        question: QuizQuestion,
    ) -> tuple[str, str | None, tuple[str, ...]]:
        return (
            question.prompt,
            question.image_url,
            tuple(t.key for t in question.targets),
        )

    def _generate_tcg_question(self, mode_id: str) -> QuizQuestion:
        if self._cached_tcg_series is not None and mode_id in (
            "tcg_hp",
            "tcg_type",
            "tcg_illustrator",
            "tcg_rarity",
        ):
            return tcg_quiz.generate_question(mode_id, self._cached_tcg_series)
        try:
            return tcg_quiz.generate_question(mode_id, self._series)
        except QuizUnavailableError:
            if mode_id not in ("tcg_hp", "tcg_type", "tcg_illustrator", "tcg_rarity"):
                raise
        from pokenux.services import tcg_library

        candidates = [
            (serie, card_set, card)
            for serie in self._series
            for card_set in serie.sets
            for card in card_set.cards
        ]
        random.shuffle(candidates)
        worker = get_current_worker()
        last_error: TCGdexError | None = None
        for serie, card_set, card in candidates[:5]:
            if worker.is_cancelled:
                raise QuizUnavailableError("Question annulée.")
            try:
                detailed = tcg_library.fetch_card_details(card.id)
            except TCGdexError as error:
                last_error = error
                cached_question = self._generate_cached_tcg_question(mode_id)
                if cached_question is not None:
                    return cached_question
                continue
            if worker.is_cancelled:
                raise QuizUnavailableError("Question annulée.")
            enriched = replace(serie, sets=[replace(card_set, cards=[detailed])])
            try:
                return tcg_quiz.generate_question(mode_id, [enriched])
            except QuizUnavailableError:
                continue
        cached_question = self._generate_cached_tcg_question(mode_id)
        if cached_question is not None:
            return cached_question
        if last_error is not None:
            raise last_error
        raise QuizUnavailableError(
            "Aucune carte adaptée trouvée. Réessaie pour en tirer d’autres."
        )

    def _generate_cached_tcg_question(self, mode_id: str) -> QuizQuestion | None:
        from pokenux.services import tcg_library

        cached = {card.id: card for card in tcg_library.get_cached_card_details()}
        if not cached:
            return None
        series = [
            replace(
                serie,
                sets=[
                    replace(
                        card_set,
                        cards=[
                            cached[card.id]
                            for card in card_set.cards
                            if card.id in cached
                        ],
                    )
                    for card_set in serie.sets
                ],
            )
            for serie in self._series
        ]
        try:
            question = tcg_quiz.generate_question(mode_id, series)
        except QuizUnavailableError:
            return None
        if not get_current_worker().is_cancelled:
            self._cached_tcg_series = series
        return question

    @on(QuestionReady)
    async def question_ready(self, event: QuestionReady) -> None:
        event.stop()
        if event.revision != self._revision:
            return
        question = event.question
        self._state = QuestionState(question)
        self._seen_questions.add(self._question_key(question))
        self.query_one("#quiz_prompt", Label).update(question.prompt)
        self.query_one("#quiz_hint", Label).update(
            question.hint or "Pas d’indice pour cette question."
        )
        if question.answer_kind == "order":
            helper = "Saisis tous les noms dans l’ordre, séparés par des virgules."
        elif question.answer_kind == "collection":
            helper = (
                "Un nom à la fois, ou plusieurs réponses séparées par des virgules."
            )
        else:
            helper = "Saisis ta réponse puis appuie sur Entrée."
        self.query_one("#quiz_answer_help", Label).update(helper)
        slot = self.query_one("#quiz_art_slot", Vertical)
        await slot.remove_children()
        if event.revision != self._revision:
            return
        slot.display = bool(question.image_url)
        slot.set_class(question.image_effect == "shadow", "quiz-art-shadow")
        self._image_ready = not question.image_url
        if question.image_url:
            self._question_image = QuizImage(question.image_url, question.image_effect)
            await slot.mount(self._question_image)
        self._set_answer_enabled(self._image_ready)
        self.query_one("#quiz_show_hint", Button).disabled = False
        self.query_one("#quiz_skip", Button).disabled = False
        self.query_one("#quiz_reveal", Button).disabled = not self._image_ready
        self._feedback(
            "À toi de jouer !" if self._image_ready else "Chargement de l’image…"
        )
        self._update_score()
        self.query_one("#quiz_question_panel", VerticalScroll).scroll_home(
            animate=False
        )
        self.call_after_refresh(self._focus_visible)

    @on(QuestionFailed)
    def question_failed(self, event: QuestionFailed) -> None:
        event.stop()
        if event.revision != self._revision:
            return
        self.query_one("#quiz_prompt", Label).update(
            "Impossible de préparer cette question."
        )
        self._feedback(event.message, error=True)
        retry = self.query_one("#quiz_next", Button)
        retry.label = "Réessayer"
        retry.disabled = False
        self.call_after_refresh(retry.focus)

    @on(QuizImage.Loaded)
    def artwork_ready(self, event: QuizImage.Loaded) -> None:
        event.stop()
        if (
            event._sender is not self._question_image
            or self._state is None
            or self._state.complete
        ):
            return
        self._image_ready = True
        self._image_failed = False
        self._set_answer_enabled(True)
        self.query_one("#quiz_reveal", Button).disabled = False
        self.query_one("#quiz_retry", Button).display = False
        self._feedback("À toi de jouer !")
        self.call_after_refresh(self._focus_visible)

    @on(QuizImage.Failed)
    def artwork_failed(self, event: QuizImage.Failed) -> None:
        event.stop()
        if (
            event._sender is not self._question_image
            or self._state is None
            or self._state.complete
        ):
            return
        self._image_ready = False
        self._image_failed = True
        self._set_answer_enabled(False)
        self._feedback(
            "Image indisponible. Réessaie ou passe sans pénalité.", error=True
        )
        retry = self.query_one("#quiz_retry", Button)
        retry.disabled = False
        retry.display = True

    @on(Button.Pressed, "#quiz_retry")
    async def retry_artwork(self) -> None:
        if not self._state or not self._state.question.image_url:
            return
        revision = self._revision
        question = self._state.question
        self._question_image = None
        slot = self.query_one("#quiz_art_slot", Vertical)
        await slot.remove_children()
        if revision != self._revision:
            return
        self._question_image = QuizImage(question.image_url, question.image_effect)
        self._image_ready = self._image_failed = False
        self._set_answer_enabled(False)
        self.query_one("#quiz_retry", Button).display = False
        self._feedback("Chargement de l’image…")
        await slot.mount(self._question_image)

    def _set_answer_enabled(self, enabled: bool) -> None:
        self.query_one("#quiz_answer", Input).disabled = not enabled
        self.query_one("#quiz_submit", Button).disabled = not enabled

    @on(Input.Submitted, "#quiz_answer")
    @on(Button.Pressed, "#quiz_submit")
    def submit_answer(self) -> None:
        if self._state is None or not self._image_ready:
            return
        if self._state.complete:
            self.action_next_question()
            return
        answer = self.query_one("#quiz_answer", Input)
        previous_errors = self._state.mistakes
        result = self._state.submit(answer.value)
        self._mistakes += self._state.mistakes - previous_errors
        self._apply_result(result)
        if result.status not in ("empty", "incorrect"):
            answer.value = ""
        elif not result.complete:
            answer.select_all()
        if not result.complete:
            answer.focus()

    def _apply_result(self, result: AnswerResult) -> None:
        self._feedback(result.message, error=result.status == "incorrect")
        if self._state is None:
            return
        if self._state.question.answer_kind == "collection":
            found = [
                t.label
                for t in self._state.question.targets
                if t.key in self._state.found
            ]
            label = self.query_one("#quiz_found", Label)
            label.update(
                f"Trouvés : {', '.join(found)}"
                if found
                else "Aucune réponse trouvée pour l’instant."
            )
            label.display = True
        if result.complete:
            self._record_completion()
            self._set_answer_enabled(False)
            self.query_one("#quiz_reveal", Button).disabled = True
            self.query_one("#quiz_show_hint", Button).disabled = True
            self.query_one("#quiz_skip", Button).disabled = True
            next_button = self.query_one("#quiz_next", Button)
            next_button.disabled = False
            next_button.label = (
                "Résultats →"
                if self._length and self._completed >= self._length
                else "Suivante →"
            )
            self._show_solution()
            self.call_after_refresh(next_button.focus)
        self._update_score()

    def _record_completion(self) -> None:
        if self._state and self._state.complete and not self._recorded:
            self._recorded = True
            self._completed += 1
            self._correct += int(self._state.succeeded)

    def _show_solution(self) -> None:
        if self._state is None:
            return
        label = self.query_one("#quiz_solution", Label)
        question = self._state.question
        details = "\n".join(t.detail for t in question.targets if t.detail)
        label.update(
            "Réponse : "
            + self._state.solution
            + "\n"
            + question.explanation
            + ("\n" + details if details else "")
        )
        label.display = True
        self.query_one("#quiz_question_panel", VerticalScroll).scroll_to_widget(
            label, animate=False
        )

    @on(Button.Pressed, "#quiz_show_hint")
    def show_hint(self) -> None:
        label = self.query_one("#quiz_hint", Label)
        if not label.display:
            self._hints += 1
        label.display = True
        self._update_score()
        self.query_one("#quiz_answer", Input).focus()

    @on(Button.Pressed, "#quiz_reveal")
    def reveal_answer(self) -> None:
        if self._state and self._image_ready:
            self._apply_result(self._state.reveal())

    @on(Button.Pressed, "#quiz_skip")
    def skip_question(self) -> None:
        if self._state and self._image_ready:
            self._state.reveal()
            self._record_completion()
        self._next_question()

    @on(Button.Pressed, "#quiz_next")
    def action_next_question(self) -> None:
        if self._state is None or self._state.complete:
            self._next_question()

    def _update_score(self) -> None:
        number = self._completed + int(not self._recorded)
        if self._length:
            number = min(number, self._length)
        total = str(self._length) if self._length else "∞"
        self.query_one("#quiz_score", Label).update(
            f"Question {number} / {total}  ·  Réussies {self._correct} / {self._completed}  ·  Erreurs {self._mistakes}  ·  Indices {self._hints}"
        )

    def _show_summary(self) -> None:
        self._show_panel("quiz_summary")
        percent = round(self._correct / self._completed * 100) if self._completed else 0
        self.query_one("#quiz_summary_score", Label).update(
            f"{self._correct} / {self._completed} questions réussies · {percent} %"
        )
        mode = self._mode.title if self._mode else "Quiz"
        self.query_one("#quiz_summary_details", Label).update(
            f"{mode}\n{self._mistakes} erreur(s) · {self._hints} indice(s) utilisés"
        )
        self.call_after_refresh(self._focus_visible)

    @on(Button.Pressed, "#quiz_replay")
    def replay_quiz(self) -> None:
        if self._mode:
            self.start_mode(self._mode.id)

    @on(Button.Pressed, "#quiz_back")
    @on(Button.Pressed, "#quiz_choose")
    def action_quiz_menu(self) -> None:
        self._revision += 1
        self.workers.cancel_group(self, "quiz-question")
        self._state = None
        self._question_image = None
        self.query_one("#quiz_art_slot").remove_children()
        self._show_panel("quiz_menu")
        self.call_after_refresh(self._focus_visible)

    def _feedback(self, message: str, *, error: bool = False) -> None:
        label = self.query_one("#quiz_feedback", Label)
        label.update(message)
        label.set_class(error, "quiz-error")

    def on_unmount(self) -> None:
        self._ready = False
        self._revision += 1

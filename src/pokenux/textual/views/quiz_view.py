"""A keyboard-friendly quiz arena with varied challenges and scored sessions."""

from dataclasses import replace
import random
from typing import ClassVar, cast, override

from rich.text import Text

from textual import events, on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import (
    Button,
    Input,
    Label,
    ProgressBar,
    Select,
    TabbedContent,
    TabPane,
)
from textual.worker import Worker
from textual.worker import get_current_worker  # pyright: ignore[reportUnknownVariableType]

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
from pokenux.services.games.quiz_session import QuizSession
from pokenux.textual.widgets.quiz_image import QuizImage


MIXED_MODES = (
    "anagram",
    "missing_letters",
    "evolution",
    "pre_evolution",
    "fake_name",
    "height_order",
    "weight_order",
    "generation",
    "number_to_name",
)

MODE_GROUPS = (
    (
        "01  ·  QUI EST CE POKÉMON ?",
        ("image_shadow", "image", "image_pixelate", "image_blur"),
    ),
    (
        "02  ·  JOUE AVEC LES MOTS",
        ("anagram", "missing_letters", "fake_name", "initial"),
    ),
    (
        "03  ·  PROUVE TON EXPERTISE",
        (
            "evolution",
            "pre_evolution",
            "evolution_family",
            "generation",
            "height_order",
            "weight_order",
            "name_to_number",
            "number_to_name",
        ),
    ),
)


class QuizView(Vertical):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "quiz_menu", "Menu Quiz"),
        Binding("ctrl+n", "next_question", "Suivante"),
        Binding("f1", "hint", "Indice"),
        Binding("f2", "skip", "Passer"),
    ]

    class QuestionReady(Message):
        def __init__(self, revision: int, question: QuizQuestion) -> None:
            super().__init__()
            self.revision: int = revision
            self.question: QuizQuestion = question

    class QuestionFailed(Message):
        def __init__(self, revision: int, message: str) -> None:
            super().__init__()
            self.revision: int = revision
            self.message: str = message

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
                _ = tcg_library.set_language(user_data.get_tcg_lang())
            series = tcg_library.series
        self._pokemon: list[Pokemon] = list(pokemon)
        self._series: list[Serie] = list(series)
        self._cached_tcg_series: list[Serie] | None = None
        self._modes: dict[str, QuizMode] = {
            mode.id: mode for mode in [*pokemon_quiz.MODES, *tcg_quiz.MODES]
        }
        self._modes["mixed"] = QuizMode(
            "mixed", "Défi surprise", "Un mélange de jeux pour tester tes réflexes."
        )
        self._mode: QuizMode | None = None
        self._state: QuestionState | None = None
        self._length: int = 10
        self._missing_letters: int | None = None
        self._session: QuizSession = QuizSession(length=self._length)
        self._hint_used: bool = False
        self._play_pokemon: list[Pokemon] = list(self._pokemon)
        self._last_mode: str = ""
        self._recorded: bool = False
        self._revision: int = 0
        self._question_image: QuizImage | None = None
        self._image_ready: bool = True
        self._image_failed: bool = False
        self._ready: bool = False
        self._order_choices: list[str] = []
        self._seen_questions: set[tuple[str, str | None, tuple[str, ...]]] = set()

    @override
    def compose(self) -> ComposeResult:
        with Vertical(id="quiz_menu"):
            with Horizontal(id="quiz_hero"):
                with Vertical(id="quiz_intro"):
                    yield Label("LE COIN DES DRESSEURS", id="quiz_eyebrow")
                    yield Label("À toi de jouer.", id="quiz_heading")
                    yield Label(
                        "Des Pokémon à reconnaître, des noms à démêler, des records à battre.",
                        classes="quiz-note",
                    )
                yield Label("  ╭─────╮\n──┤  ◉  ├──\n  ╰─────╯", id="quiz_emblem")
            yield Button(
                Text.assemble(
                    ("▶  DÉFI SURPRISE · POKÉDEX", "bold #eee4ff"),
                    (
                        "\nDes épreuves variées · un seul objectif : enchaîner les bonnes réponses",
                        "#b9a9d2",
                    ),
                ),
                id="quiz_quickplay",
            )
            with Horizontal(id="quiz_settings"):
                with Vertical(classes="quiz-setting"):
                    yield Label("Ta partie")
                    yield Select(
                        [
                            ("5 · express", 5),
                            ("10 · classique", 10),
                            ("20 · marathon", 20),
                            ("Libre ∞", 0),
                        ],
                        value=10,
                        allow_blank=False,
                        id="quiz_length",
                    )
                with Vertical(classes="quiz-setting"):
                    yield Label("Pokémon")
                    generations = sorted(
                        {
                            item.generation
                            for item in self._pokemon
                            if item.pokedex_id > 0
                        }
                    )
                    yield Select(
                        [("Toutes", 0)] + [(f"Gén. {n}", n) for n in generations],
                        value=0,
                        allow_blank=False,
                        id="quiz_generation",
                        tooltip="Limite les quiz Pokédex à une génération. Sans effet sur le TCG.",
                    )
                with Vertical(classes="quiz-setting"):
                    yield Label("Lettres cachées")
                    yield Select(
                        [("Auto", 0)] + [(str(n), n) for n in range(1, 9)],
                        value=0,
                        allow_blank=False,
                        id="quiz_missing_letters",
                        tooltip="Nombre de lettres à cacher dans le mode Lettres manquantes.",
                    )
            with TabbedContent(id="quiz_categories"):
                with TabPane("◉  Pokédex", id="quiz_pokedex_modes"):
                    with VerticalScroll(classes="quiz-mode-scroll"):
                        for title, modes in MODE_GROUPS:
                            yield Label(title, classes="quiz-section")
                            with Grid(classes="quiz-mode-grid"):
                                for mode_id in modes:
                                    yield self._mode_button(self._modes[mode_id])
                with TabPane("▧  Cartes TCG", id="quiz_tcg_modes"):
                    with VerticalScroll(classes="quiz-mode-scroll"):
                        yield Label("LA PASSION DES CARTES", classes="quiz-section")
                        with Grid(classes="quiz-mode-grid"):
                            for mode in tcg_quiz.MODES:
                                yield self._mode_button(mode)
            yield Label(
                "100 pts · −25 par erreur · indice : ÷2 · série parfaite : jusqu’à +100 · aucun chrono",
                id="quiz_normalization_note",
            )

        with Vertical(id="quiz_game"):
            with Horizontal(id="quiz_game_heading"):
                yield Label("", id="quiz_game_title", markup=False)
                yield Button(
                    "Bilan",
                    id="quiz_finish",
                    tooltip="Terminer et voir les réponses déjà jouées.",
                )
                yield Button("← Menu", id="quiz_back")
            with Horizontal(id="quiz_hud"):
                yield Label("", id="quiz_points", markup=False)
                yield Label("", id="quiz_streak", markup=False)
                yield Label("", id="quiz_accuracy", markup=False)
            with Horizontal(id="quiz_progress_row"):
                yield Label("", id="quiz_score", markup=False)
                yield ProgressBar(
                    total=10, show_percentage=False, show_eta=False, id="quiz_progress"
                )
            with VerticalScroll(id="quiz_question_panel"):
                yield Label("", id="quiz_round_label", markup=False)
                yield Label("", id="quiz_prompt", markup=False)
                yield Label("", id="quiz_puzzle", markup=False)
                yield Vertical(id="quiz_art_slot")
                yield Horizontal(id="quiz_order_choices")
                yield Button("↺ Recommencer l’ordre", id="quiz_order_reset")
                yield Label("", id="quiz_hint", markup=False)
                yield Label("", id="quiz_found", markup=False)
                yield Label("", id="quiz_solution", markup=False)
            with Horizontal(id="quiz_feedback_bar"):
                yield Label("", id="quiz_feedback", markup=False)
                yield Button("Réessayer", id="quiz_retry", disabled=True)
            yield Label("", id="quiz_answer_help", markup=False)
            with Horizontal(id="quiz_answer_row"):
                yield Input(placeholder="Ta réponse…", id="quiz_answer", disabled=True)
                yield Button("Valider ↵", id="quiz_submit", variant="primary")
            with Horizontal(id="quiz_actions"):
                yield Button(
                    "Indice · F1",
                    id="quiz_show_hint",
                    tooltip="F1 · divise les points par deux, interrompt la série.",
                )
                yield Button("Solution", id="quiz_reveal")
                yield Button(
                    "Passer · F2",
                    id="quiz_skip",
                    tooltip="F2 · question comptée sans points.",
                )
                yield Button(
                    "Suite →", id="quiz_next", disabled=True, variant="primary"
                )

        with VerticalScroll(id="quiz_summary"):
            yield Label("✦  PARTIE TERMINÉE  ✦", id="quiz_summary_title")
            yield Label("", id="quiz_summary_rank", markup=False)
            yield Label("", id="quiz_summary_message", markup=False)
            with Horizontal(id="quiz_summary_stats"):
                yield Label("", id="quiz_summary_points", markup=False)
                yield Label("", id="quiz_summary_score", markup=False)
                yield Label("", id="quiz_summary_streak", markup=False)
            yield Label("", id="quiz_summary_details", markup=False)
            yield Label("", id="quiz_summary_review", markup=False)
            with Horizontal(id="quiz_summary_actions"):
                yield Button("Rejouer ↵", id="quiz_replay", variant="primary")
                yield Button("Changer de défi", id="quiz_choose")

    @staticmethod
    def _mode_button(mode: QuizMode) -> Button:
        button = Button(
            Text.assemble(
                (mode.title, "bold #e4dbf5"),
                ("\n" + mode.description, "#99aabd"),
            ),
            id=f"quiz_mode_{mode.id}",
            classes="quiz-mode-button",
        )
        button.tooltip = mode.description
        return button

    def on_mount(self) -> None:
        self._ready = True
        self._show_panel("quiz_menu")
        _ = self.call_after_refresh(self._focus_visible)

    def on_show(self) -> None:
        if self._ready:
            _ = self.call_after_refresh(self._focus_visible)

    def _focus_visible(self) -> None:
        if not self.is_mounted or self.region.height <= 0:
            return
        if self.query_one("#quiz_menu").display:
            _ = self.query_one("#quiz_quickplay", Button).focus()
        elif self.query_one("#quiz_summary").display:
            _ = self.query_one("#quiz_replay", Button).focus()
        elif self._state and self._state.complete:
            _ = self.query_one("#quiz_next", Button).focus()
        elif self._state and self._image_ready:
            _ = self.query_one("#quiz_answer", Input).focus()
        else:
            _ = self.query_one("#quiz_back", Button).focus()

    def on_resize(self, event: events.Resize) -> None:
        _ = self.set_class(event.size.width < 90, "narrow")
        _ = self.set_class(event.size.height < 36, "short")
        _ = self.set_class(event.size.height < 22, "tiny")
        if self._ready:
            self.query_one("#quiz_art_slot").styles.height = max(
                5, min(22, event.size.height - 17)
            )

    def _show_panel(self, identifier: str) -> None:
        for panel in ("quiz_menu", "quiz_game", "quiz_summary"):
            self.query_one(f"#{panel}").display = panel == identifier

    @on(Button.Pressed, ".quiz-mode-button")
    def choose_mode(self, event: Button.Pressed) -> None:
        if event.button.id:
            self.start_mode(event.button.id.removeprefix("quiz_mode_"))

    @on(Button.Pressed, "#quiz_quickplay")
    def quickplay(self) -> None:
        self.start_mode("mixed")

    def start_mode(self, mode_id: str) -> None:
        self._mode = self._modes[mode_id]
        self._length = int(
            str(cast(Select[int], self.query_one("#quiz_length", Select)).value)
        )
        missing = int(
            str(
                cast(Select[int], self.query_one("#quiz_missing_letters", Select)).value
            )
        )
        self._missing_letters = missing or None
        self._session = QuizSession(length=self._length)
        generation = int(
            str(cast(Select[int], self.query_one("#quiz_generation", Select)).value)
        )
        self._play_pokemon = [
            item
            for item in self._pokemon
            if not generation or item.generation == generation
        ]
        self._hint_used = False
        self._last_mode = ""
        self._seen_questions.clear()
        self._cached_tcg_series = None
        self.query_one("#quiz_game_title", Label).update(self._mode.title)
        self._show_panel("quiz_game")
        self._next_question()

    def _next_question(self) -> None:
        if self._session.finished:
            self._show_summary()
            return
        if self._mode is None:
            return
        self._revision += 1
        _ = cast(
            list[Worker[None]],
            self.workers.cancel_group(self, "quiz-question"),  # pyright: ignore[reportUnknownMemberType]
        )
        self._state = None
        self._recorded = False
        self._hint_used = False
        self._order_choices.clear()
        self._image_ready = False
        self._image_failed = False
        self._question_image = None
        self.query_one("#quiz_prompt", Label).update("Préparation de la question…")
        self.query_one("#quiz_art_slot").display = False
        for identifier in (
            "quiz_hint",
            "quiz_puzzle",
            "quiz_found",
            "quiz_solution",
            "quiz_order_choices",
            "quiz_order_reset",
        ):
            self.query_one(f"#{identifier}").display = False
        answer = self.query_one("#quiz_answer", Input)
        answer.value = ""
        self._set_answer_enabled(False)
        for identifier in ("quiz_show_hint", "quiz_reveal", "quiz_skip", "quiz_next"):
            self.query_one(f"#{identifier}", Button).disabled = True
        self.query_one("#quiz_next", Button).label = "Suite →"
        self.query_one("#quiz_show_hint", Button).label = "Indice · F1"
        self.query_one("#quiz_answer_help", Label).update(
            "Entrée pour valider · accents et majuscules libres"
        )
        panel = self.query_one("#quiz_question_panel", VerticalScroll)
        _ = panel.remove_class("quiz-correct", "quiz-incorrect")
        self.query_one("#quiz_round_label", Label).update("NOUVELLE MANCHE")
        self.query_one("#quiz_retry", Button).display = False
        self._feedback("Chargement…")
        self._update_score()
        _ = self._generate_question(
            self._revision, self._mode.id, self._missing_letters
        )

    @work(thread=True, exclusive=True, group="quiz-question", exit_on_error=False)
    def _generate_question(
        self, revision: int, mode_id: str, missing: int | None
    ) -> None:
        worker = cast(Worker[None], get_current_worker())
        try:
            mode = self._modes[mode_id]
            question: QuizQuestion | None = None
            candidates = list(MIXED_MODES) if mode_id == "mixed" else [mode_id]
            if mode_id == "mixed":
                if len({item.generation for item in self._play_pokemon}) < 2:
                    candidates.remove("generation")
                random.shuffle(candidates)
                candidates.sort(
                    key=lambda candidate: (
                        sum(
                            record.mode_id == candidate
                            for record in self._session.records
                        ),
                        candidate == self._last_mode,
                    )
                )
            last_error: QuizUnavailableError | None = None
            for attempt in range(max(12, len(candidates))):
                if worker.is_cancelled:
                    return
                selected_mode = candidates[attempt % len(candidates)]
                try:
                    if mode.category == "pokedex":
                        language = user_data.get_pokemon_lang()
                        question = pokemon_quiz.generate_question(
                            selected_mode,
                            self._play_pokemon,
                            language=language if language in ("fr", "en") else "fr",
                            missing_letters=missing,
                        )
                    else:
                        question = self._generate_tcg_question(selected_mode)
                except QuizUnavailableError as error:
                    if mode_id != "mixed":
                        raise
                    last_error = error
                    continue
                if self._question_key(question) not in self._seen_questions:
                    break
            if question is None:
                raise last_error or QuizUnavailableError(
                    "Aucune question disponible pour cette sélection."
                )
            if not worker.is_cancelled:
                _ = self.post_message(self.QuestionReady(revision, question))
        except (QuizUnavailableError, TCGdexError, OSError, ValueError) as error:
            if not worker.is_cancelled:
                _ = self.post_message(self.QuestionFailed(revision, str(error)))

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
        worker = cast(Worker[None], get_current_worker())
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
        if not cast(Worker[None], get_current_worker()).is_cancelled:
            self._cached_tcg_series = series
        return question

    @on(QuestionReady)
    async def question_ready(self, event: QuestionReady) -> None:
        _ = event.stop()
        if event.revision != self._revision:
            return
        question = event.question
        self._state = QuestionState(question)
        self._last_mode = question.mode_id
        title = self._modes.get(question.mode_id)
        self.query_one("#quiz_round_label", Label).update(
            f"MANCHE {self._session.completed + 1:02d}  /  {title.title.upper() if title else 'À TOI DE JOUER'}"
        )
        self._seen_questions.add(self._question_key(question))
        prompt, separator, puzzle = question.prompt.rpartition(" : ")
        is_puzzle = question.mode_id in (
            "anagram",
            "missing_letters",
            "tcg_anagram",
        ) and bool(separator)
        self.query_one("#quiz_prompt", Label).update(
            prompt if is_puzzle else question.prompt
        )
        puzzle_label = self.query_one("#quiz_puzzle", Label)
        puzzle_label.update(" ".join(puzzle) if len(puzzle) <= 18 else puzzle)
        puzzle_label.display = is_puzzle
        self.query_one("#quiz_hint", Label).update(
            question.hint or "Pas d’indice pour cette question."
        )
        if question.answer_kind == "order":
            helper = "Clique les noms dans l’ordre, ou saisis-les avec des virgules."
        elif question.answer_kind == "collection":
            helper = (
                "Un nom à la fois, ou plusieurs réponses séparées par des virgules."
            )
        elif question.mode_id == "fake_name":
            helper = "Oui = nom inventé · non = vrai Pokémon · Entrée pour valider"
        elif question.mode_id in ("generation", "name_to_number", "tcg_hp"):
            helper = "Saisis un nombre, puis Entrée pour valider."
        elif question.mode_id in ("tcg_card_name", "tcg_anagram"):
            helper = "Nom complet, avec le suffixe (ex, V…) · accents libres"
        else:
            helper = "Entrée pour valider · accents et majuscules libres"
        self.query_one("#quiz_answer_help", Label).update(helper)
        choices = self.query_one("#quiz_order_choices", Horizontal)
        await choices.remove_children()
        if event.revision != self._revision:
            return
        is_order = question.answer_kind == "order"
        choices.display = is_order
        self.query_one("#quiz_order_reset").display = is_order
        if is_order:
            self._order_choices = [target.label for target in question.targets]
            random.shuffle(self._order_choices)
            await choices.mount(
                *(
                    Button(label, id=f"quiz_order_{index}", classes="quiz-order-choice")
                    for index, label in enumerate(self._order_choices)
                )
            )
            if event.revision != self._revision:
                return
        slot = self.query_one("#quiz_art_slot", Vertical)
        await slot.remove_children()
        if event.revision != self._revision:
            return
        slot.display = bool(question.image_url)
        _ = slot.set_class(question.image_effect == "shadow", "quiz-art-shadow")
        self._image_ready = not question.image_url
        if question.image_url:
            self._question_image = QuizImage(question.image_url, question.image_effect)
            await slot.mount(self._question_image)
        self._set_answer_enabled(self._image_ready)
        if question.answer_kind == "collection":
            self.query_one("#quiz_found", Label).update(
                f"◎  0 / {len(question.targets)} trouvés"
            )
            self.query_one("#quiz_found").display = True
        self.query_one("#quiz_show_hint", Button).disabled = not (
            question.hint and self._image_ready
        )
        self.query_one("#quiz_skip", Button).disabled = False
        self.query_one("#quiz_reveal", Button).disabled = not self._image_ready
        self._feedback(
            "À toi de jouer !" if self._image_ready else "Chargement de l’image…"
        )
        self._update_score()
        self.query_one("#quiz_question_panel", VerticalScroll).scroll_home(
            animate=False
        )
        _ = self.call_after_refresh(self._focus_visible)

    @on(QuestionFailed)
    def question_failed(self, event: QuestionFailed) -> None:
        _ = event.stop()
        if event.revision != self._revision:
            return
        self.query_one("#quiz_prompt", Label).update(
            "Impossible de préparer cette question."
        )
        self._feedback(event.message, error=True)
        retry = self.query_one("#quiz_next", Button)
        retry.label = "Réessayer"
        retry.disabled = False
        _ = self.call_after_refresh(retry.focus)

    @on(QuizImage.Loaded)
    def artwork_ready(self, event: QuizImage.Loaded) -> None:
        _ = event.stop()
        if (
            event._sender is not self._question_image  # pyright: ignore[reportPrivateUsage]
            or self._state is None
            or self._state.complete
        ):
            return
        self._image_ready = True
        self._image_failed = False
        self._set_answer_enabled(True)
        self.query_one("#quiz_show_hint", Button).disabled = not bool(
            self._state.question.hint
        )
        self.query_one("#quiz_reveal", Button).disabled = False
        self.query_one("#quiz_retry", Button).display = False
        self._feedback("À toi de jouer !")
        _ = self.call_after_refresh(self._focus_visible)

    @on(QuizImage.Failed)
    def artwork_failed(self, event: QuizImage.Failed) -> None:
        _ = event.stop()
        if (
            event._sender is not self._question_image  # pyright: ignore[reportPrivateUsage]
            or self._state is None
            or self._state.complete
        ):
            return
        self._image_ready = False
        self._image_failed = True
        self._set_answer_enabled(False)
        self.query_one("#quiz_show_hint", Button).disabled = True
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
        for button in self.query(".quiz-order-choice"):
            button.disabled = not enabled
        self.query_one("#quiz_order_reset", Button).disabled = not enabled

    @on(Button.Pressed, ".quiz-order-choice")
    def choose_order(self, event: Button.Pressed) -> None:
        if (
            self._state is None
            or self._state.complete
            or self._state.question.answer_kind != "order"
            or not self._image_ready
            or not event.button.id
            or event.button.parent is not self.query_one("#quiz_order_choices")
        ):
            return
        index = int(event.button.id.removeprefix("quiz_order_"))
        if not 0 <= index < len(self._order_choices):
            return
        label = self._order_choices[index]
        answer = self.query_one("#quiz_answer", Input)
        parts = [part.strip() for part in answer.value.split(",") if part.strip()]
        if label not in parts:
            parts.append(label)
        answer.value = ", ".join(parts)
        answer.cursor_position = len(answer.value)
        _ = answer.focus()

    @on(Input.Changed, "#quiz_answer")
    def update_order_choices(self, event: Input.Changed) -> None:
        if self._state is None or self._state.question.answer_kind != "order":
            return
        parts = [part.strip() for part in event.value.split(",") if part.strip()]
        for button in self.query(".quiz-order-choice").results(Button):
            index = int((button.id or "quiz_order_0").removeprefix("quiz_order_"))
            if not 0 <= index < len(self._order_choices):
                continue
            label = self._order_choices[index]
            position = parts.index(label) + 1 if label in parts else 0
            button.label = f"{position}. {label}" if position else label
            _ = button.set_class(bool(position), "quiz-order-selected")

    @on(Button.Pressed, "#quiz_order_reset")
    def reset_order(self) -> None:
        if self._state and not self._state.complete:
            answer = self.query_one("#quiz_answer", Input)
            answer.value = ""
            _ = answer.focus()

    @on(Input.Submitted, "#quiz_answer")
    @on(Button.Pressed, "#quiz_submit")
    def submit_answer(self) -> None:
        if (
            not self.query_one("#quiz_game").display
            or self._state is None
            or not self._image_ready
        ):
            return
        if self._state.complete:
            self.action_next_question()
            return
        answer = self.query_one("#quiz_answer", Input)
        result = self._state.submit(answer.value)
        self._apply_result(result)
        if (
            result.status not in ("empty", "incorrect")
            and self._state.question.answer_kind != "order"
        ):
            answer.value = ""
        elif not result.complete:
            answer.select_all()
        if not result.complete:
            _ = answer.focus()

    def _apply_result(self, result: AnswerResult) -> None:
        self._feedback(result.message, error=result.status == "incorrect")
        panel = self.query_one("#quiz_question_panel")
        _ = panel.set_class(result.status == "incorrect", "quiz-incorrect")
        _ = panel.set_class(result.complete and result.correct, "quiz-correct")
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
                f"●  {len(found)} / {len(self._state.question.targets)} trouvés · {' · '.join(found)}"
                if found
                else "Aucune réponse trouvée pour l’instant."
            )
            label.display = True
        if result.complete:
            self._record_completion()
            if result.correct:
                earned = self._session.records[-1].points
                combo = (
                    f" · Série de {self._session.streak} !"
                    if self._session.streak > 1
                    else ""
                )
                self._feedback(f"✦  {result.message}  +{earned} pts{combo}")
            self._set_answer_enabled(False)
            self.query_one("#quiz_reveal", Button).disabled = True
            self.query_one("#quiz_show_hint", Button).disabled = True
            self.query_one("#quiz_skip", Button).disabled = True
            next_button = self.query_one("#quiz_next", Button)
            next_button.disabled = False
            next_button.label = "Résultats →" if self._session.finished else "Suite →"
            self._show_solution()
            _ = self.call_after_refresh(next_button.focus)
        self._update_score()

    def _record_completion(self, *, skipped: bool = False) -> None:
        if self._state and self._state.complete and not self._recorded:
            _ = self._session.record(
                self._state, used_hint=self._hint_used, skipped=skipped
            )
            self._recorded = True

    def _show_solution(self) -> None:
        if self._state is None:
            return
        label = self.query_one("#quiz_solution", Label)
        question = self._state.question
        details = "\n".join(t.detail for t in question.targets if t.detail)
        explanation = (
            question.explanation if question.explanation != self._state.solution else ""
        )
        label.update(
            "\n".join(
                part
                for part in ("Réponse : " + self._state.solution, explanation, details)
                if part
            )
        )
        label.display = True
        if self._question_image and question.image_effect != "normal":
            _ = self.call_later(
                self._reveal_artwork, self._question_image, self._revision
            )
        _ = self.query_one("#quiz_question_panel", VerticalScroll).scroll_to_widget(
            label, animate=False
        )

    async def _reveal_artwork(self, artwork: QuizImage, revision: int) -> None:
        if revision != self._revision or artwork is not self._question_image:
            return
        await artwork.reveal()
        if revision == self._revision and artwork is self._question_image:
            _ = self.query_one("#quiz_art_slot").remove_class("quiz-art-shadow")

    @on(Button.Pressed, "#quiz_show_hint")
    def show_hint(self) -> None:
        if (
            not self._state
            or self._state.complete
            or not self._image_ready
            or not self._state.question.hint
        ):
            return
        self._hint_used = True
        label = self.query_one("#quiz_hint", Label)
        label.display = True
        self.query_one("#quiz_show_hint", Button).disabled = True
        self.query_one("#quiz_show_hint", Button).label = "Indice ✓"
        self._feedback(
            "Un coup de pouce ! Les points de cette manche sont divisés par deux."
        )
        self._update_score()
        _ = self.query_one("#quiz_question_panel", VerticalScroll).scroll_to_widget(
            label, animate=False
        )
        _ = self.query_one("#quiz_answer", Input).focus()

    def action_hint(self) -> None:
        if self.query_one("#quiz_game").display:
            self.show_hint()

    @on(Button.Pressed, "#quiz_reveal")
    def reveal_answer(self) -> None:
        if self._state and self._image_ready and not self._state.complete:
            self._apply_result(self._state.reveal())

    @on(Button.Pressed, "#quiz_skip")
    def skip_question(self) -> None:
        if self._state is None or self._state.complete:
            return
        if self._image_ready:
            _ = self._state.reveal()
            self._record_completion(skipped=True)
        self._next_question()

    def action_skip(self) -> None:
        if self.query_one("#quiz_game").display:
            self.skip_question()

    @on(Button.Pressed, "#quiz_next")
    def action_next_question(self) -> None:
        if self.query_one("#quiz_game").display and (
            self._state is None or self._state.complete
        ):
            self._next_question()

    def _update_score(self) -> None:
        session = self._session
        number = session.completed + int(not self._recorded)
        total = str(self._length) if self._length else "∞"
        self.query_one("#quiz_score", Label).update(
            f"Manche {min(number, self._length) if self._length else number} / {total}"
        )
        self.query_one("#quiz_points", Label).update(f"✦  {session.points} pts")
        active_clean = not self._hint_used and not (
            self._state and self._state.mistakes
        )
        streak = session.streak if active_clean or self._recorded else 0
        self.query_one("#quiz_streak", Label).update(f"ϟ  Série {streak}")
        self.query_one("#quiz_accuracy", Label).update(
            f"●  {session.correct}/{session.completed} réussies"
        )
        _ = self.query_one("#quiz_streak").set_class(streak >= 2, "quiz-on-fire")
        progress = self.query_one("#quiz_progress", ProgressBar)
        progress.display = bool(self._length)
        progress.update(total=self._length or 1, progress=session.completed)

    @on(Button.Pressed, "#quiz_finish")
    def finish_quiz(self) -> None:
        self._revision += 1
        _ = cast(
            list[Worker[None]],
            self.workers.cancel_group(self, "quiz-question"),  # pyright: ignore[reportUnknownMemberType]
        )
        self._question_image = None
        self._state = None
        _ = self.query_one("#quiz_art_slot").remove_children()
        self._show_summary()

    def _show_summary(self) -> None:
        self._show_panel("quiz_summary")
        session = self._session
        self.query_one("#quiz_summary_rank", Label).update(session.rank)
        self.query_one("#quiz_summary_message", Label).update(session.message)
        self.query_one("#quiz_summary_points", Label).update(
            f"{session.points}\nPOINTS"
        )
        self.query_one("#quiz_summary_score", Label).update(
            f"{session.accuracy} %\nRÉUSSITE"
        )
        self.query_one("#quiz_summary_streak", Label).update(
            f"{session.best_streak}\nMEILLEURE SÉRIE"
        )
        mode = self._mode.title if self._mode else "Quiz"
        self.query_one("#quiz_summary_details", Label).update(
            f"{mode} · {session.correct} / {session.completed} réussies\n"
            + f"{session.mistakes} erreur(s) · {session.hints} indice(s) · seules les manches terminées comptent"
        )
        to_review = [
            record
            for record in session.records
            if not record.succeeded or record.mistakes or record.used_hint
        ]
        review = "\n\n".join(
            f"{index:02d}  {record.prompt}\n     → {record.solution}"
            for index, record in enumerate(to_review, 1)
        )
        label = self.query_one("#quiz_summary_review", Label)
        label.update(
            "POUR LA PROCHAINE FOIS\n\n" + review
            if review
            else "✧  Tout est maîtrisé. Prêt pour un autre défi ?"
        )
        label.display = bool(session.completed)
        self.query_one("#quiz_summary", VerticalScroll).scroll_home(animate=False)
        _ = self.call_after_refresh(self._focus_visible)

    @on(Button.Pressed, "#quiz_replay")
    def replay_quiz(self) -> None:
        if self._mode:
            self.start_mode(self._mode.id)

    @on(Button.Pressed, "#quiz_back")
    @on(Button.Pressed, "#quiz_choose")
    def action_quiz_menu(self) -> None:
        self._revision += 1
        _ = cast(
            list[Worker[None]],
            self.workers.cancel_group(self, "quiz-question"),  # pyright: ignore[reportUnknownMemberType]
        )
        self._state = None
        self._question_image = None
        _ = self.query_one("#quiz_art_slot").remove_children()
        self._show_panel("quiz_menu")
        _ = self.call_after_refresh(self._focus_visible)

    def _feedback(self, message: str, *, error: bool = False) -> None:
        label = self.query_one("#quiz_feedback", Label)
        label.update(message)
        _ = label.set_class(error, "quiz-error")

    def on_unmount(self) -> None:
        self._ready = False
        self._revision += 1

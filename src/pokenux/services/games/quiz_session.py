"""Session scoring and results shared by every quiz mode."""

from pokenux.services.localization import text

from dataclasses import dataclass, field

from pokenux.services.games.quiz import QuestionState


@dataclass(frozen=True)
class RoundRecord:
    """An immutable snapshot of a completed question."""

    prompt: str
    solution: str
    succeeded: bool
    mistakes: int
    used_hint: bool
    skipped: bool
    points: int
    mode_id: str

    @property
    def clean(self) -> bool:
        return self.succeeded and not self.mistakes and not self.used_hint


@dataclass
class QuizSession:
    """Track a challenge, or free play when ``length`` is ``None`` or zero.

    A clean answer earns 100 points, with a 20-point bonus per consecutive
    clean answer after the first, capped at 100 bonus points. Mistakes cost
    25 points each down to a 25-point minimum; a hint halves those points.
    Mistakes, hints and unsuccessful rounds all break the clean-answer streak.
    """

    length: int | None = 10
    records: list[RoundRecord] = field(default_factory=list, init=False)
    _recorded_states: dict[int, tuple[QuestionState, RoundRecord]] = field(
        default_factory=dict, init=False, repr=False
    )

    def __post_init__(self) -> None:
        if self.length is not None and self.length < 0:
            raise ValueError(
                text(
                    "La longueur d’une session ne peut pas être négative.",
                    "A session cannot have a negative length.",
                )
            )

    def reset(self) -> None:
        self.records.clear()
        self._recorded_states.clear()

    @property
    def completed(self) -> int:
        return len(self.records)

    @property
    def correct(self) -> int:
        return sum(record.succeeded for record in self.records)

    @property
    def mistakes(self) -> int:
        return sum(record.mistakes for record in self.records)

    @property
    def hints(self) -> int:
        return sum(record.used_hint for record in self.records)

    @property
    def points(self) -> int:
        return sum(record.points for record in self.records)

    @property
    def streak(self) -> int:
        streak = 0
        for record in reversed(self.records):
            if not record.clean:
                break
            streak += 1
        return streak

    @property
    def best_streak(self) -> int:
        best = current = 0
        for record in self.records:
            current = current + 1 if record.clean else 0
            best = max(best, current)
        return best

    @property
    def finished(self) -> bool:
        return bool(self.length) and self.completed >= self.length

    @property
    def accuracy(self) -> int:
        return round(100 * self.correct / self.completed) if self.completed else 0

    @property
    def rank(self) -> str:
        if not self.completed:
            return text("Dresseur en herbe", "Budding Trainer")
        if self.accuracy == 100 and not self.mistakes and not self.hints:
            return text("Maître Pokémon", "Pokémon Master")
        if self.accuracy >= 80:
            return text("Champion d’arène", "Gym Leader")
        if self.accuracy >= 50:
            return text("Dresseur confirmé", "Experienced Trainer")
        return text("Explorateur Pokémon", "Pokémon explorer")

    @property
    def title(self) -> str:
        if not self.completed:
            return text("À toi de jouer !", "Your turn!")
        if self.accuracy == 100 and not self.mistakes and not self.hints:
            return text("Un sans-faute légendaire !", "A legendary perfect score!")
        if self.accuracy >= 80:
            return text("Quel talent de dresseur !", "What a talented Trainer!")
        if self.accuracy >= 50:
            return text("Une belle aventure !", "A great adventure!")
        return text(
            "Chaque rencontre t’apprend quelque chose !",
            "Every encounter teaches you something!",
        )

    @property
    def message(self) -> str:
        if not self.completed:
            return text(
                "Trouve les réponses et enchaîne les réussites pour gagner des points.",
                "Find the answers and keep your streak going to earn points.",
            )
        if self.accuracy == 100 and not self.mistakes and not self.hints:
            return text(
                "Toutes les réponses, sans erreur ni indice. Le prochain défi t’attend !",
                "Every answer, without a mistake or hint. Your next challenge awaits!",
            )
        if self.accuracy >= 80:
            return text(
                "Tu connais ton sujet ! Vise une série sans erreur pour battre ton score.",
                "You know your stuff! Aim for a clean streak to beat your score.",
            )
        if self.accuracy >= 50:
            return text(
                "De belles réponses ! Revisite les solutions et tente un nouveau défi.",
                "Some great answers! Review the solutions and try another challenge.",
            )
        return text(
            "De nouvelles découvertes à chaque manche. Rejoue pour voir tes progrès !",
            "Discover something new each round. Play again to see your progress!",
        )

    def record(
        self,
        state: QuestionState,
        *,
        used_hint: bool = False,
        skipped: bool = False,
    ) -> RoundRecord:
        """Record a finished question once; repeat calls return its first snapshot."""
        previous = self._recorded_states.get(id(state))
        if previous is not None:
            return previous[1]
        if not state.complete:
            raise ValueError(
                text(
                    "La question doit être terminée avant d’être comptabilisée.",
                    "Finish the question before recording it.",
                )
            )
        if self.finished:
            raise ValueError(
                text(
                    "Cette session est déjà terminée.",
                    "This session is already complete.",
                )
            )

        succeeded = state.succeeded and not skipped
        points = 0
        if succeeded:
            points = max(25, 100 - 25 * state.mistakes)
            if used_hint:
                points //= 2
            elif not state.mistakes:
                points += min(100, 20 * self.streak)

        record = RoundRecord(
            prompt=state.question.prompt,
            solution=state.solution,
            succeeded=succeeded,
            mistakes=state.mistakes,
            used_hint=used_hint,
            skipped=skipped,
            points=points,
            mode_id=state.question.mode_id,
        )
        self.records.append(record)
        # Keep the state alive: a recycled object ID must never suppress a round.
        self._recorded_states[id(state)] = (state, record)
        return record

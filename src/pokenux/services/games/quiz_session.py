"""Session scoring and results shared by every quiz mode."""

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
            raise ValueError("La longueur d’une session ne peut pas être négative.")

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
            return "Dresseur en herbe"
        if self.accuracy == 100 and not self.mistakes and not self.hints:
            return "Maître Pokémon"
        if self.accuracy >= 80:
            return "Champion d’arène"
        if self.accuracy >= 50:
            return "Dresseur confirmé"
        return "Explorateur Pokémon"

    @property
    def title(self) -> str:
        if not self.completed:
            return "À toi de jouer !"
        if self.accuracy == 100 and not self.mistakes and not self.hints:
            return "Un sans-faute légendaire !"
        if self.accuracy >= 80:
            return "Quel talent de dresseur !"
        if self.accuracy >= 50:
            return "Une belle aventure !"
        return "Chaque rencontre t’apprend quelque chose !"

    @property
    def message(self) -> str:
        if not self.completed:
            return (
                "Trouve les réponses et enchaîne les réussites pour gagner des points."
            )
        if self.accuracy == 100 and not self.mistakes and not self.hints:
            return "Toutes les réponses, sans erreur ni indice. Le prochain défi t’attend !"
        if self.accuracy >= 80:
            return "Tu connais ton sujet ! Vise une série sans erreur pour battre ton score."
        if self.accuracy >= 50:
            return (
                "De belles réponses ! Revisite les solutions et tente un nouveau défi."
            )
        return (
            "De nouvelles découvertes à chaque manche. Rejoue pour voir tes progrès !"
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
                "La question doit être terminée avant d’être comptabilisée."
            )
        if self.finished:
            raise ValueError("Cette session est déjà terminée.")

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

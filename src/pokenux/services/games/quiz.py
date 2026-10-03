"""Shared free-text answer rules for Pokémon and card quizzes."""

from dataclasses import dataclass, field
import re
import unicodedata


def normalize_answer(value: str) -> str:
    """Ignore case, accents and punctuation while retaining meaningful sex signs."""
    value = value.casefold().replace("œ", "oe").replace("æ", "ae")
    value = value.replace("♀", "f").replace("♂", "m")
    value = "".join(
        char
        for char in unicodedata.normalize("NFKD", value)
        if char.isalnum() and not unicodedata.combining(char)
    )
    if value.isdecimal():
        digits = "".join(str(unicodedata.decimal(char)) for char in value)
        return digits.lstrip("0") or "0"
    return value


class QuizUnavailableError(ValueError):
    """The selected catalogue has no usable question for this mode."""


@dataclass(frozen=True)
class QuizMode:
    id: str
    title: str
    description: str
    category: str = "pokedex"


@dataclass(frozen=True)
class QuizTarget:
    key: str
    label: str
    aliases: tuple[str, ...]
    detail: str = ""

    def accepts(self, response: str) -> bool:
        answer = normalize_answer(response)
        return bool(answer) and any(
            answer == normalize_answer(alias) for alias in (self.label, *self.aliases)
        )


@dataclass(frozen=True)
class QuizQuestion:
    mode_id: str
    prompt: str
    targets: tuple[QuizTarget, ...]
    answer_kind: str = "single"
    image_url: str | None = None
    image_effect: str = "normal"
    hint: str = ""
    explanation: str = ""
    ordering_groups: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class AnswerResult:
    status: str
    message: str
    complete: bool = False
    correct: bool = False
    accepted: tuple[str, ...] = ()


@dataclass
class QuestionState:
    question: QuizQuestion
    found: set[str] = field(default_factory=set)
    mistakes: int = 0
    complete: bool = False
    succeeded: bool = False

    @property
    def solution(self) -> str:
        targets = self.question.targets
        if self.question.answer_kind == "single":
            return " / ".join(dict.fromkeys(t.label for t in targets))
        if self.question.answer_kind == "order":
            by_key = {target.key: target for target in targets}
            groups = self.question.ordering_groups or tuple((t.key,) for t in targets)
            return " → ".join(
                " = ".join(by_key[key].label for key in group) for group in groups
            )
        return ", ".join(target.label for target in targets)

    def submit(self, response: str) -> AnswerResult:
        if self.complete:
            return AnswerResult(
                "finished", "Cette question est terminée.", True, self.succeeded
            )
        if not normalize_answer(response):
            return AnswerResult("empty", "Saisis une réponse pour continuer.")
        if self.question.answer_kind == "collection":
            return self._submit_collection(response)
        if self.question.answer_kind == "order":
            return self._submit_order(response)
        if any(target.accepts(response) for target in self.question.targets):
            self.complete = self.succeeded = True
            return AnswerResult("correct", "Bonne réponse !", True, True)
        self.mistakes += 1
        return AnswerResult("incorrect", "Ce n’est pas la réponse. Réessaie !")

    def _submit_collection(self, response: str) -> AnswerResult:
        accepted: list[str] = []
        unknown: list[str] = []
        duplicates: list[str] = []
        for part in re.split(r"[,;\n]+", response):
            if not normalize_answer(part):
                continue
            target = next((t for t in self.question.targets if t.accepts(part)), None)
            if target is None:
                unknown.append(part.strip())
            elif target.key in self.found:
                duplicates.append(target.label)
            else:
                self.found.add(target.key)
                accepted.append(target.label)
        self.mistakes += len(unknown)
        self.complete = len(self.found) == len(self.question.targets)
        self.succeeded = self.complete
        message = f"{len(self.found)} / {len(self.question.targets)} trouvés."
        if unknown:
            message += " Réponse inconnue : " + ", ".join(unknown) + "."
        elif duplicates and not accepted:
            message += " Déjà trouvé !"
        if self.complete:
            message = "Tout trouvé ! " + message
        status = (
            "correct"
            if self.complete
            else "progress"
            if accepted
            else "incorrect"
            if unknown
            else "duplicate"
        )
        return AnswerResult(
            status, message, self.complete, self.complete, tuple(accepted)
        )

    def _submit_order(self, response: str) -> AnswerResult:
        parts = [
            part.strip()
            for part in re.split(r"[,;\n>→]+", response)
            if normalize_answer(part)
        ]
        keys: list[str] = []
        for part in parts:
            target = next((t for t in self.question.targets if t.accepts(part)), None)
            if target is None:
                break
            keys.append(target.key)
        expected = {target.key for target in self.question.targets}
        valid = len(keys) == len(parts) == len(expected) and set(keys) == expected
        groups = self.question.ordering_groups or tuple(
            (t.key,) for t in self.question.targets
        )
        offset = 0
        for group in groups:
            valid = valid and set(keys[offset : offset + len(group)]) == set(group)
            offset += len(group)
        if valid:
            self.complete = self.succeeded = True
            return AnswerResult("correct", "Le classement est correct !", True, True)
        self.mistakes += 1
        return AnswerResult(
            "incorrect", "Classe tous les noms dans l’ordre, séparés par des virgules."
        )

    def reveal(self) -> AnswerResult:
        if not self.complete:
            self.complete = True
            self.succeeded = False
        return AnswerResult(
            "revealed", "Solution : " + self.solution, True, self.succeeded
        )

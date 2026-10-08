"""Free-answer card quizzes generated from the catalogue supplied by the caller."""

import random
from pokenux.services.localization import text

from urllib.parse import urlsplit, urlunsplit

from pokenux.models.tcg.card import Card
from pokenux.models.tcg.serie import Serie
from pokenux.models.tcg.set import Set
from pokenux.services.games.quiz import (
    QuizMode,
    QuizQuestion,
    QuizTarget,
    QuizUnavailableError,
    normalize_answer,
)


def get_modes() -> list[QuizMode]:
    return [
        QuizMode(
            "tcg_card_name",
            text("Reconnaître une carte", "Name the card"),
            text(
                "Nomme la carte à partir de son illustration, sans son titre.",
                "Name the card from its illustration, with its title hidden.",
            ),
            category="tcg",
        ),
        QuizMode(
            "tcg_set",
            text("Trouver l’extension", "Find the set"),
            text(
                "Identifie l’extension d’une carte visible en entier.",
                "Identify the set from a complete card.",
            ),
            category="tcg",
        ),
        QuizMode(
            "tcg_series",
            text("Trouver la série", "Find the series"),
            text(
                "Retrouve la série à laquelle appartient une extension.",
                "Find which series a set belongs to.",
            ),
            category="tcg",
        ),
        QuizMode(
            "tcg_anagram",
            text("Anagramme de carte", "Card anagram"),
            text(
                "Remets les lettres du nom d’une carte dans l’ordre.",
                "Unscramble the name of a card.",
            ),
            category="tcg",
        ),
        QuizMode(
            "tcg_hp",
            text("Points de vie", "Hit points"),
            text(
                "Donne les PV d’une édition précise d’une carte.",
                "Give the HP of a specific card edition.",
            ),
            category="tcg",
        ),
        QuizMode(
            "tcg_type",
            text("Types d’une carte", "Card types"),
            text(
                "Retrouve tous les types d’une édition précise d’une carte.",
                "Find all the types of a specific card edition.",
            ),
            category="tcg",
        ),
        QuizMode(
            "tcg_illustrator",
            text("Qui a illustré cette carte ?", "Who illustrated this card?"),
            text(
                "Retrouve l’illustrateur d’une édition précise d’une carte.",
                "Identify the illustrator of a specific card edition.",
            ),
            category="tcg",
        ),
        QuizMode(
            "tcg_rarity",
            text("Rareté d’une carte", "Card rarity"),
            text(
                "Donne la rareté d’une édition précise d’une carte.",
                "Give the rarity of a specific card edition.",
            ),
            category="tcg",
        ),
    ]


MODES = get_modes()


_TYPE_ALIASES: tuple[tuple[str, ...], ...] = (
    ("Plante", "Grass"),
    ("Feu", "Fire"),
    ("Eau", "Water"),
    ("Électrique", "Lightning", "Electric"),
    ("Psy", "Psychic"),
    ("Combat", "Fighting"),
    ("Obscurité", "Ténèbres", "Darkness", "Dark"),
    ("Métal", "Metal", "Acier", "Steel"),
    ("Dragon",),
    ("Fée", "Fairy"),
    ("Incolore", "Colorless", "Colourless"),
)

_RARITY_ALIASES: tuple[tuple[str, ...], ...] = (
    ("Commune", "Common"),
    ("Peu commune", "Uncommon"),
    ("Rare",),
    ("Rare Holo", "Rare Holographique", "Holo Rare"),
    ("Ultra Rare",),
    ("Double Rare",),
    ("Rare Illustration", "Illustration Rare"),
    ("Rare Illustration Spéciale", "Special Illustration Rare"),
    ("Hyper Rare",),
)


def card_image_url(image: str) -> str | None:
    """Resolve TCGdex image roots without changing complete image URLs."""
    if not image.strip():
        return None
    url = urlsplit(image.strip())
    path = url.path.rstrip("/")
    if not path.lower().endswith((".png", ".webp", ".jpg", ".jpeg", ".gif")):
        path += "/high.png"
    return urlunsplit((url.scheme, url.netloc, path, url.query, url.fragment))


def _aliases(label: str, groups: tuple[tuple[str, ...], ...]) -> tuple[str, ...]:
    normalized = normalize_answer(label)
    for group in groups:
        if any(normalize_answer(alias) == normalized for alias in group):
            return group
    return (label,)


def _card_reference(card: Card, card_set: Set) -> str:
    local_id = card.local_id or card.id.rsplit("-", 1)[-1]
    return text(
        "{v0} — {v1}, carte n° {v2}",
        "{v0} — {v1}, card #{v2}",
        v0=card.name,
        v1=card_set.name,
        v2=local_id,
    )


def _name_hint(name: str) -> str:
    letters = [letter for letter in name if letter.isalpha()]
    words = name.split()
    clues = [
        text(
            "{v0} mot{v1}",
            "{v0} word{v1}",
            v0=len(words),
            v1="s" if len(words) > 1 else "",
        )
    ]
    if len(letters) > 2:
        clues.append(
            text("commence par {v0}", "starts with {v0}", v0=letters[0].upper())
        )
    clues.append(
        text(
            "{v0} lettre{v1}",
            "{v0} letter{v1}",
            v0=len(letters),
            v1="s" if len(letters) > 1 else "",
        )
    )
    return " · ".join(clues) + "."


def _card_name_hint(card: Card) -> str:
    clues = [_name_hint(card.name)]
    if types := list(dict.fromkeys(value for value in card.types if value.strip())):
        clues.append(
            "Type" + ("s" if len(types) > 1 else "") + " : " + " / ".join(types)
        )
    if card.hp is not None:
        clues.append(text("{v0} PV", "{v0} HP", v0=card.hp))
    return " · ".join(clues)


def _release_hint(name: str, release_date: str) -> str:
    year = release_date[:4]
    release = (
        text("Parution en {v0} · ", "Released in {v0} · ", v0=year)
        if len(year) == 4 and year.isdecimal()
        else ""
    )
    return release + _name_hint(name)


def _shuffle_name(name: str, rng: random.Random) -> str:
    letters = list(normalize_answer(name))
    initial = letters.copy()
    rng.shuffle(letters)
    if letters == initial:
        # Ensure that even a deterministic RNG cannot return the original name.
        for index in range(1, len(letters)):
            if letters[index] != letters[0]:
                letters[0], letters[index] = letters[index], letters[0]
                break
    return " ".join(letters).upper()


def generate_question(
    mode_id: str,
    series: list[Serie],
    *,
    rng: random.Random | None = None,
) -> QuizQuestion:
    """Generate a question only from available metadata; never fetch at import."""
    if mode_id not in {mode.id for mode in MODES}:
        raise QuizUnavailableError(
            text("Mode TCG inconnu : {v0}.", "Unknown TCG mode: {v0}.", v0=mode_id)
        )
    randomizer = rng if rng is not None else random.Random()

    if mode_id == "tcg_series":
        candidates = [
            (serie, card_set)
            for serie in series
            if serie.name.strip()
            for card_set in serie.sets
            if card_set.name.strip()
        ]
        if not candidates:
            raise QuizUnavailableError(
                text(
                    "Aucune extension disponible pour ce quiz.",
                    "No set is available for this quiz.",
                )
            )
        serie, card_set = randomizer.choice(candidates)
        return QuizQuestion(
            mode_id=mode_id,
            prompt=text(
                "À quelle série appartient l’extension « {v0} » ?",
                "Which series does the set “{v0}” belong to?",
                v0=card_set.name,
            ),
            targets=(QuizTarget(serie.id, serie.name, (serie.name, serie.id)),),
            hint=_release_hint(serie.name, serie.release_date),
            explanation=text(
                "{v0} appartient à la série {v1}.",
                "{v0} belongs to the {v1} series.",
                v0=card_set.name,
                v1=serie.name,
            ),
        )

    cards = [
        (card_set, card)
        for serie in series
        for card_set in serie.sets
        for card in card_set.cards
        if card.name.strip()
    ]
    if mode_id in ("tcg_card_name", "tcg_set"):
        cards = [(card_set, card) for card_set, card in cards if card.image.strip()]
    elif mode_id == "tcg_anagram":
        cards = [
            (card_set, card)
            for card_set, card in cards
            if len(set(normalize_answer(card.name))) > 1
        ]
    elif mode_id == "tcg_hp":
        cards = [(card_set, card) for card_set, card in cards if card.hp is not None]
    elif mode_id == "tcg_type":
        cards = [
            (card_set, card)
            for card_set, card in cards
            if any(card_type.strip() for card_type in card.types)
        ]
    elif mode_id == "tcg_illustrator":
        cards = [
            (card_set, card) for card_set, card in cards if card.illustrator.strip()
        ]
    elif mode_id == "tcg_rarity":
        cards = [(card_set, card) for card_set, card in cards if card.rarity.strip()]
    if not cards:
        raise QuizUnavailableError(
            text(
                "Aucune carte ne contient les informations nécessaires pour ce quiz.",
                "No card has the metadata needed for this quiz.",
            )
        )
    card_set, card = randomizer.choice(cards)
    reference = _card_reference(card, card_set)

    if mode_id == "tcg_card_name":
        return QuizQuestion(
            mode_id=mode_id,
            prompt=text(
                "Quel est le nom de cette carte ?", "What is this card's name?"
            ),
            targets=(QuizTarget(card.id, card.name, (card.name,)),),
            image_url=card_image_url(card.image),
            image_effect="crop",
            hint=_card_name_hint(card),
            explanation=reference,
        )
    if mode_id == "tcg_set":
        return QuizQuestion(
            mode_id=mode_id,
            prompt=text(
                "De quelle extension provient cette carte ?",
                "Which set is this card from?",
            ),
            targets=(
                QuizTarget(
                    card_set.id,
                    card_set.name,
                    tuple(
                        alias
                        for alias in (card_set.name, card_set.id, card_set.abbreviation)
                        if alias
                    ),
                ),
            ),
            image_url=card_image_url(card.image),
            hint=_release_hint(card_set.name, card_set.release_date),
            explanation=reference,
        )
    if mode_id == "tcg_anagram":
        return QuizQuestion(
            mode_id=mode_id,
            prompt=text(
                "Retrouve le nom de cette carte : {v0}",
                "Unscramble this card name : {v0}",
                v0=_shuffle_name(card.name, randomizer),
            ),
            targets=(QuizTarget(card.id, card.name, (card.name,)),),
            hint=_card_name_hint(card),
            explanation=reference,
        )
    if mode_id == "tcg_hp":
        assert card.hp is not None
        hp = str(card.hp)
        return QuizQuestion(
            mode_id=mode_id,
            prompt=text(
                "Combien de PV possède {v0} ?",
                "How many HP does {v0} have?",
                v0=reference,
            ),
            targets=(QuizTarget(card.id, hp, (hp, f"{hp} PV", f"{hp} HP")),),
            hint=text(
                "Entre {v0} et {v1} PV.",
                "Between {v0} and {v1} HP.",
                v0=card.hp // 50 * 50,
                v1=card.hp // 50 * 50 + 49,
            ),
            explanation=text(
                "{v0} possède {v1} PV.", "{v0} has {v1} HP.", v0=reference, v1=hp
            ),
        )
    if mode_id == "tcg_type":
        types = list(
            dict.fromkeys(card_type for card_type in card.types if card_type.strip())
        )
        return QuizQuestion(
            mode_id=mode_id,
            prompt=text(
                "Quels sont tous les types de {v0} ?",
                "What are all the types of {v0}?",
                v0=reference,
            ),
            targets=tuple(
                QuizTarget(card_type, card_type, _aliases(card_type, _TYPE_ALIASES))
                for card_type in types
            ),
            answer_kind="collection",
            hint=text(
                "{v0} type{v1} à retrouver. ",
                "Find {v0} type{v1}. ",
                v0=len(types),
                v1="s" if len(types) > 1 else "",
            )
            + text("Initiale", "Initial")
            + ("s" if len(types) > 1 else "")
            + " : "
            + ", ".join(card_type.strip()[0].upper() for card_type in types)
            + ".",
            explanation=f"{reference} : {', '.join(types)}.",
        )
    if mode_id == "tcg_illustrator":
        return QuizQuestion(
            mode_id=mode_id,
            prompt=text("Qui a illustré {v0} ?", "Who illustrated {v0}?", v0=reference),
            targets=(QuizTarget(card.id, card.illustrator, (card.illustrator,)),),
            hint=_name_hint(card.illustrator),
            explanation=text(
                "{v0} a été illustrée par {v1}.",
                "{v0} was illustrated by {v1}.",
                v0=reference,
                v1=card.illustrator,
            ),
        )
    return QuizQuestion(
        mode_id=mode_id,
        prompt=text(
            "Quelle est la rareté de {v0} ?",
            "What is the rarity of {v0}?",
            v0=reference,
        ),
        targets=(
            QuizTarget(card.id, card.rarity, _aliases(card.rarity, _RARITY_ALIASES)),
        ),
        hint=_name_hint(card.rarity),
        explanation=f"{reference} : {card.rarity}.",
    )

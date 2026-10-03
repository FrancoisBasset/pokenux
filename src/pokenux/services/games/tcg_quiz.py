"""Free-answer card quizzes generated from the catalogue supplied by the caller."""

import random
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


MODES: list[QuizMode] = [
    QuizMode(
        "tcg_card_name",
        "Reconnaître une carte",
        "Nomme la carte à partir de son illustration, sans son titre.",
        category="tcg",
    ),
    QuizMode(
        "tcg_set",
        "Trouver l’extension",
        "Identifie l’extension d’une carte visible en entier.",
        category="tcg",
    ),
    QuizMode(
        "tcg_series",
        "Trouver la série",
        "Retrouve la série à laquelle appartient une extension.",
        category="tcg",
    ),
    QuizMode(
        "tcg_anagram",
        "Anagramme de carte",
        "Remets les lettres du nom d’une carte dans l’ordre.",
        category="tcg",
    ),
    QuizMode(
        "tcg_hp",
        "Points de vie",
        "Donne les PV d’une édition précise d’une carte.",
        category="tcg",
    ),
    QuizMode(
        "tcg_type",
        "Types d’une carte",
        "Retrouve tous les types d’une édition précise d’une carte.",
        category="tcg",
    ),
    QuizMode(
        "tcg_illustrator",
        "Qui a illustré cette carte ?",
        "Retrouve l’illustrateur d’une édition précise d’une carte.",
        category="tcg",
    ),
    QuizMode(
        "tcg_rarity",
        "Rareté d’une carte",
        "Donne la rareté d’une édition précise d’une carte.",
        category="tcg",
    ),
]


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
    return f"{card.name} — {card_set.name}, carte n° {local_id}"


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
        raise QuizUnavailableError(f"Mode TCG inconnu : {mode_id}.")
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
            raise QuizUnavailableError("Aucune extension disponible pour ce quiz.")
        serie, card_set = randomizer.choice(candidates)
        return QuizQuestion(
            mode_id=mode_id,
            prompt=f"À quelle série appartient l’extension « {card_set.name} » ?",
            targets=(QuizTarget(serie.id, serie.name, (serie.name, serie.id)),),
            hint="Saisis le nom de la série.",
            explanation=f"{card_set.name} appartient à la série {serie.name}.",
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
            "Aucune carte ne contient les informations nécessaires pour ce quiz."
        )
    card_set, card = randomizer.choice(cards)
    reference = _card_reference(card, card_set)

    if mode_id == "tcg_card_name":
        return QuizQuestion(
            mode_id=mode_id,
            prompt="Quel est le nom de cette carte ?",
            targets=(QuizTarget(card.id, card.name, (card.name,)),),
            image_url=card_image_url(card.image),
            image_effect="crop",
            hint="Saisis le nom complet de la carte, y compris son éventuel suffixe.",
            explanation=reference,
        )
    if mode_id == "tcg_set":
        return QuizQuestion(
            mode_id=mode_id,
            prompt="De quelle extension provient cette carte ?",
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
            hint="Saisis le nom de l’extension ou son abréviation officielle.",
            explanation=reference,
        )
    if mode_id == "tcg_anagram":
        return QuizQuestion(
            mode_id=mode_id,
            prompt=f"Retrouve le nom de cette carte : {_shuffle_name(card.name, randomizer)}",
            targets=(QuizTarget(card.id, card.name, (card.name,)),),
            hint="Toutes les lettres sont présentes. Les espaces ne comptent pas.",
            explanation=reference,
        )
    if mode_id == "tcg_hp":
        hp = str(card.hp)
        return QuizQuestion(
            mode_id=mode_id,
            prompt=f"Combien de PV possède {reference} ?",
            targets=(QuizTarget(card.id, hp, (hp, f"{hp} PV", f"{hp} HP")),),
            hint="Saisis le nombre de points de vie.",
            explanation=f"{reference} possède {hp} PV.",
        )
    if mode_id == "tcg_type":
        types = list(
            dict.fromkeys(card_type for card_type in card.types if card_type.strip())
        )
        return QuizQuestion(
            mode_id=mode_id,
            prompt=f"Quels sont tous les types de {reference} ?",
            targets=tuple(
                QuizTarget(card_type, card_type, _aliases(card_type, _TYPE_ALIASES))
                for card_type in types
            ),
            answer_kind="collection",
            hint="Saisis un type à la fois ou sépare les types par des virgules.",
            explanation=f"{reference} : {', '.join(types)}.",
        )
    if mode_id == "tcg_illustrator":
        return QuizQuestion(
            mode_id=mode_id,
            prompt=f"Qui a illustré {reference} ?",
            targets=(QuizTarget(card.id, card.illustrator, (card.illustrator,)),),
            hint="Saisis le nom de l’illustrateur.",
            explanation=f"{reference} a été illustrée par {card.illustrator}.",
        )
    return QuizQuestion(
        mode_id=mode_id,
        prompt=f"Quelle est la rareté de {reference} ?",
        targets=(
            QuizTarget(card.id, card.rarity, _aliases(card.rarity, _RARITY_ALIASES)),
        ),
        hint="Saisis la rareté de la carte.",
        explanation=f"{reference} : {card.rarity}.",
    )

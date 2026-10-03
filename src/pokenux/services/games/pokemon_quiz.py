"""Pokédex questions generated solely from the supplied catalogue.

The downloadable evolution lists include whole lineages. Questions deliberately
use direct relatives so, for example, Bulbasaur's answer cannot be Venusaur.
"""

from collections import defaultdict
from collections.abc import Mapping
from itertools import groupby
import math
import random
import re
from urllib.parse import urlsplit

from pokenux.models.pokemon.pokemon import Pokemon
from pokenux.models.pokemon.pokemon_evolution import PokemonEvolution
from pokenux.services.games.quiz import (
    QuizMode,
    QuizQuestion,
    QuizTarget,
    QuizUnavailableError,
    normalize_answer,
)


MODES = [
    QuizMode("initial", "Par initiale", "Retrouver tous les Pokémon d'une initiale."),
    QuizMode("anagram", "Anagramme", "Remettre les lettres d'un nom dans l'ordre."),
    QuizMode("missing_letters", "Lettres manquantes", "Compléter un nom troué."),
    QuizMode("evolution", "Évolution", "Nommer une évolution immédiate."),
    QuizMode("pre_evolution", "Pré-évolution", "Nommer la pré-évolution immédiate."),
    QuizMode("evolution_family", "Avant et après", "Nommer les proches d'un Pokémon."),
    QuizMode("fake_name", "Faux nom", "Déterminer si un nom de Pokémon est inventé."),
    QuizMode("height_order", "Classer par taille", "Classer trois Pokémon par taille."),
    QuizMode("weight_order", "Classer par poids", "Classer trois Pokémon par poids."),
    QuizMode("generation", "Génération", "Donner la génération d'un Pokémon."),
    QuizMode("image", "Par image", "Reconnaître un Pokémon sur son image."),
    QuizMode("image_blur", "Image floutée", "Reconnaître un Pokémon flouté."),
    QuizMode("image_pixelate", "Image pixelisée", "Reconnaître un Pokémon pixelisé."),
    QuizMode("image_shadow", "Ombre", "Reconnaître une silhouette de Pokémon."),
    QuizMode(
        "name_to_number", "Nom → numéro", "Donner le numéro national d'un Pokémon."
    ),
    QuizMode("number_to_name", "Numéro → nom", "Retrouver un Pokémon par son numéro."),
]


def _name(pokemon: Pokemon, language: str) -> str:
    return pokemon.name.en if language == "en" else pokemon.name.fr


def _target(pokemon: Pokemon, language: str, detail: str = "") -> QuizTarget:
    return QuizTarget(
        key=str(pokemon.pokedex_id),
        label=_name(pokemon, language),
        aliases=tuple(dict.fromkeys((pokemon.name.fr, pokemon.name.en))),
        detail=detail,
    )


def _entry_id(entry: PokemonEvolution | Mapping[str, object]) -> int | None:
    value = entry.get("pokedex_id") if isinstance(entry, Mapping) else entry.pokedex_id
    try:
        return int(str(value))
    except ValueError:
        return None


def _relatives(
    pokemon: list[Pokemon],
) -> tuple[dict[int, list[Pokemon]], dict[int, list[Pokemon]]]:
    catalogue = {item.pokedex_id: item for item in pokemon}
    pre_ids = {
        item.pokedex_id: [
            value
            for entry in item.evolution.pre or []
            if (value := _entry_id(entry)) is not None
        ]
        for item in pokemon
    }
    next_ids = {
        item.pokedex_id: {
            value
            for entry in item.evolution.next or []
            if (value := _entry_id(entry)) is not None
        }
        for item in pokemon
    }
    edges: set[tuple[int, int]] = set()
    for child_id, ancestors in pre_ids.items():
        if ancestors and ancestors[-1] in catalogue and ancestors[-1] != child_id:
            edges.add((ancestors[-1], child_id))
    for parent_id, descendants in next_ids.items():
        for child_id in descendants:
            if child_id not in catalogue or child_id == parent_id or pre_ids[child_id]:
                continue
            # If the child's own lineage is unavailable, eliminate candidates
            # that another descendant already lists as its descendants.
            if any(
                child_id in next_ids.get(intermediate, set())
                for intermediate in descendants - {child_id, parent_id}
            ):
                continue
            edges.add((parent_id, child_id))
    parents: dict[int, list[Pokemon]] = defaultdict(list)
    children: dict[int, list[Pokemon]] = defaultdict(list)
    for parent_id, child_id in sorted(edges):
        parents[child_id].append(catalogue[parent_id])
        children[parent_id].append(catalogue[child_id])
    return dict(parents), dict(children)


def _measurement(value: str) -> float | None:
    match = re.search(r"-?\d+(?:[,.]\d+)?", str(value))
    if match is None:
        return None
    number = float(match.group().replace(",", "."))
    return number if math.isfinite(number) and number > 0 else None


def _image_url(url: object) -> str | None:
    if not isinstance(url, str):
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    return url if parsed.scheme in ("http", "https") and parsed.netloc else None


def _invent_name(name: str, all_names: set[str], rng: random.Random) -> str:
    letters = [index for index, letter in enumerate(name) if letter.isalpha()]
    for _ in range(40):
        position = rng.choice(letters)
        candidate = (
            name[:position]
            + rng.choice("abcdefghijklmnopqrstuvwxyz")
            + name[position + 1 :]
        )
        if normalize_answer(candidate) not in all_names:
            return candidate
    candidate = name + "nux"
    while normalize_answer(candidate) in all_names:
        candidate += "nux"
    return candidate


def _choose(pokemon: list[Pokemon], rng: random.Random, label: str) -> Pokemon:
    if not pokemon:
        title = next((mode.title for mode in MODES if mode.id == label), label)
        raise QuizUnavailableError(f"Aucun Pokémon disponible pour le mode {title}.")
    return rng.choice(pokemon)


def generate_question(
    mode_id: str,
    pokemon: list[Pokemon],
    *,
    language: str = "fr",
    missing_letters: int | None = None,
    rng: random.Random | None = None,
) -> QuizQuestion:
    """Create a solvable question, raising ValueError for unavailable modes.

    Names in either catalogue language are acceptable. Missing-letter questions
    always leave at least one letter visible, and an explicit count is exact.
    """
    if mode_id not in {mode.id for mode in MODES}:
        raise ValueError(f"Mode de quiz inconnu : {mode_id}.")
    chooser = rng if rng is not None else random.Random()
    language = "en" if language == "en" else "fr"
    catalogue = list(
        {
            item.pokedex_id: item
            for item in pokemon
            if item.pokedex_id > 0 and normalize_answer(_name(item, language))
        }.values()
    )
    if not catalogue:
        raise QuizUnavailableError("Le catalogue Pokémon est vide.")

    if mode_id == "initial":
        by_initial: dict[str, list[Pokemon]] = defaultdict(list)
        for item in catalogue:
            initial = normalize_answer(_name(item, language))[:1]
            if initial:
                by_initial[initial].append(item)
        initial = chooser.choice(sorted(by_initial))
        members = sorted(by_initial[initial], key=lambda item: _name(item, language))
        return QuizQuestion(
            mode_id=mode_id,
            prompt=f"Nomme les {len(members)} Pokémon commençant par {initial.upper()}.",
            targets=tuple(_target(item, language) for item in members),
            answer_kind="collection",
            hint="Saisis un nom à la fois ; chaque Pokémon compte une seule fois.",
        )

    if mode_id in ("evolution", "pre_evolution", "evolution_family"):
        parents, children = _relatives(catalogue)
        candidates = [
            item
            for item in catalogue
            if (
                mode_id == "evolution"
                and children.get(item.pokedex_id)
                or mode_id == "pre_evolution"
                and parents.get(item.pokedex_id)
                or mode_id == "evolution_family"
                and parents.get(item.pokedex_id)
                and children.get(item.pokedex_id)
            )
        ]
        selected = _choose(candidates, chooser, mode_id)
        name = _name(selected, language)
        if mode_id == "evolution_family":
            relatives = parents[selected.pokedex_id] + children[selected.pokedex_id]
            return QuizQuestion(
                mode_id=mode_id,
                prompt=f"Nomme la pré-évolution et les évolutions immédiates de {name}.",
                targets=tuple(_target(item, language) for item in relatives),
                answer_kind="collection",
                hint=f"{len(relatives)} noms à retrouver, un par saisie.",
            )
        relatives = (
            children[selected.pokedex_id]
            if mode_id == "evolution"
            else parents[selected.pokedex_id]
        )
        subject = "une évolution" if mode_id == "evolution" else "la pré-évolution"
        return QuizQuestion(
            mode_id=mode_id,
            prompt=f"Nomme {subject} immédiate de {name}.",
            targets=tuple(_target(item, language) for item in relatives),
            hint="Une seule réponse suffit." if len(relatives) > 1 else "",
            explanation=" / ".join(_name(item, language) for item in relatives),
        )

    if mode_id in ("height_order", "weight_order"):
        field = "height" if mode_id == "height_order" else "weight"
        values = {
            item.pokedex_id: value
            for item in catalogue
            if (
                value := _measurement(item.height if field == "height" else item.weight)
            )
            is not None
        }
        candidates = [item for item in catalogue if item.pokedex_id in values]
        if len(candidates) < 3 or len(set(values.values())) < 2:
            raise QuizUnavailableError(
                "Il faut trois Pokémon et au moins deux mesures différentes."
            )
        selected = chooser.sample(candidates, 3)
        if len({values[item.pokedex_id] for item in selected}) == 1:
            selected[-1] = chooser.choice(
                [
                    item
                    for item in candidates
                    if values[item.pokedex_id] != values[selected[0].pokedex_id]
                ]
            )
        ordered = sorted(selected, key=lambda item: values[item.pokedex_id])
        groups = tuple(
            tuple(str(item.pokedex_id) for item in members)
            for _, members in groupby(ordered, key=lambda item: values[item.pokedex_id])
        )
        dimension = "taille" if field == "height" else "poids"
        direction = (
            "petit au plus grand" if field == "height" else "léger au plus lourd"
        )
        return QuizQuestion(
            mode_id=mode_id,
            prompt=f"Classe par {dimension}, du plus {direction} : "
            + " · ".join(_name(item, language) for item in selected),
            targets=tuple(
                _target(
                    item, language, item.height if field == "height" else item.weight
                )
                for item in ordered
            ),
            answer_kind="order",
            ordering_groups=groups,
            hint="Saisis les trois noms dans l'ordre, séparés par des virgules.",
            explanation=" → ".join(
                f"{_name(item, language)} ({item.height if field == 'height' else item.weight})"
                for item in ordered
            ),
        )

    if mode_id.startswith("image"):
        selected = _choose(
            [item for item in catalogue if _image_url(item.sprites.regular)],
            chooser,
            mode_id,
        )
        effect = {
            "image": "normal",
            "image_blur": "blur",
            "image_pixelate": "pixelate",
            "image_shadow": "shadow",
        }[mode_id]
        return QuizQuestion(
            mode_id=mode_id,
            prompt="Quel est ce Pokémon ?",
            targets=(_target(selected, language),),
            image_url=_image_url(selected.sprites.regular),
            image_effect=effect,
            hint="Donne son nom.",
        )

    if mode_id == "anagram":
        candidates = [
            item
            for item in catalogue
            if len(set(normalize_answer(_name(item, language)))) > 1
        ]
        selected = _choose(candidates, chooser, mode_id)
        name = _name(selected, language)
        original = normalize_answer(name)
        letters = list(original)
        chooser.shuffle(letters)
        if "".join(letters) == original:
            # Guaranteed progress even with a deterministic RNG or repeated letters.
            different = next(
                index for index, letter in enumerate(letters) if letter != letters[0]
            )
            letters[0], letters[different] = letters[different], letters[0]
        return QuizQuestion(
            mode_id=mode_id,
            prompt=f"Retrouve le nom : {''.join(letters).upper()}",
            targets=tuple(
                _target(item, language)
                for item in catalogue
                if sorted(normalize_answer(_name(item, language))) == sorted(original)
            ),
            hint="Toutes les lettres du nom sont présentes.",
        )

    if mode_id == "missing_letters":
        if missing_letters is not None and missing_letters < 1:
            raise ValueError("Le nombre de lettres manquantes doit être positif.")
        candidates = [
            item
            for item in catalogue
            if sum(letter.isalpha() for letter in _name(item, language))
            > (missing_letters if missing_letters is not None else 1)
        ]
        selected = _choose(candidates, chooser, mode_id)
        name = _name(selected, language)
        positions = [index for index, letter in enumerate(name) if letter.isalpha()]
        count = (
            missing_letters
            if missing_letters is not None
            else chooser.randint(1, len(positions) - 1)
        )
        hidden = set(chooser.sample(positions, count))
        pattern = "".join(
            "_" if index in hidden else letter for index, letter in enumerate(name)
        )
        return QuizQuestion(
            mode_id=mode_id,
            prompt=f"Complète le nom : {pattern}",
            targets=tuple(
                _target(item, language)
                for item in catalogue
                if len(_name(item, language)) == len(name)
                and all(
                    index in hidden
                    and letter.isalpha()
                    or index not in hidden
                    and normalize_answer(letter) == normalize_answer(name[index])
                    for index, letter in enumerate(_name(item, language))
                )
            ),
            hint=f"{count} lettre{'s' if count > 1 else ''} manquante{'s' if count > 1 else ''}. Saisis le nom complet.",
        )

    if mode_id == "fake_name":
        selected = _choose(
            [
                item
                for item in catalogue
                if any(letter.isalpha() for letter in _name(item, language))
            ],
            chooser,
            mode_id,
        )
        fake = chooser.choice((False, True))
        name = _name(selected, language)
        all_names = {
            normalize_answer(alias)
            for item in catalogue
            for alias in (item.name.fr, item.name.en)
        }
        if fake:
            name = _invent_name(name, all_names, chooser)
        answer = QuizTarget(
            key="yes" if fake else "no",
            label="Oui" if fake else "Non",
            aliases=("oui", "yes", "o", "faux", "inventé")
            if fake
            else ("non", "no", "n", "réel", "vrai nom"),
        )
        return QuizQuestion(
            mode_id=mode_id,
            prompt=f"« {name} » est-il un faux nom de Pokémon ?",
            targets=(answer,),
            hint="Saisis oui ou non.",
            explanation=f"« {name} » est {'un nom inventé' if fake else 'un vrai nom de Pokémon'}.",
        )

    selected = _choose(
        [item for item in catalogue if item.generation > 0]
        if mode_id == "generation"
        else catalogue,
        chooser,
        mode_id,
    )
    name = _name(selected, language)
    if mode_id == "generation":
        generation = selected.generation
        roman = ("", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX")
        aliases = (
            str(generation),
            f"génération {generation}",
            f"gen {generation}",
            f"g{generation}",
            *((roman[generation],) if generation < len(roman) else ()),
        )
        return QuizQuestion(
            mode_id=mode_id,
            prompt=f"Dans quelle génération apparaît {name} ?",
            targets=(QuizTarget(str(generation), f"Génération {generation}", aliases),),
            hint="Donne le numéro de génération.",
        )
    if mode_id == "name_to_number":
        number = selected.pokedex_id
        return QuizQuestion(
            mode_id=mode_id,
            prompt=f"Quel est le numéro de {name} dans le Pokédex national ?",
            targets=(
                QuizTarget(
                    str(number),
                    f"#{number:04d}",
                    (
                        str(number),
                        f"{number:03d}",
                        f"{number:04d}",
                        f"n° {number}",
                        f"numéro {number}",
                    ),
                ),
            ),
            hint="Saisis son numéro national.",
        )
    return QuizQuestion(
        mode_id=mode_id,
        prompt=f"Quel Pokémon porte le numéro #{selected.pokedex_id:04d} dans le Pokédex national ?",
        targets=(_target(selected, language),),
        hint="Donne son nom.",
    )

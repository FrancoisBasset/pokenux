"""Pokédex questions generated solely from the supplied catalogue.

The downloadable evolution lists include whole lineages. Questions deliberately
use direct relatives so, for example, Bulbasaur's answer cannot be Venusaur.
"""

from pokenux.services.localization import text

from collections import defaultdict
from collections.abc import Mapping
from itertools import groupby
import math
import random
import re
from urllib.parse import urlsplit

from pokenux.models.pokemon.pokemon import Pokemon
from pokenux.models.pokemon.pokemon_evolution import PokemonEvolution
from pokenux.models.pokemon.pokemon_type import PokemonType, localized_type_name
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
            "initial",
            text("Par initiale", "By initial"),
            text(
                "Retrouver tous les Pokémon d'une initiale.",
                "Find every Pokémon beginning with one letter.",
            ),
        ),
        QuizMode(
            "anagram",
            text("Anagramme", "Anagram"),
            text(
                "Remettre les lettres d'un nom dans l'ordre.",
                "Unscramble a Pokémon name.",
            ),
        ),
        QuizMode(
            "missing_letters",
            text("Lettres manquantes", "Missing letters"),
            text("Compléter un nom troué.", "Fill in the missing letters of a name."),
        ),
        QuizMode(
            "evolution",
            text("Évolution", "Evolution"),
            text("Nommer une évolution immédiate.", "Name an immediate evolution."),
        ),
        QuizMode(
            "pre_evolution",
            text("Pré-évolution", "Previous evolution"),
            text(
                "Nommer la pré-évolution immédiate.",
                "Name the immediate previous evolution.",
            ),
        ),
        QuizMode(
            "evolution_family",
            text("Avant et après", "Before and after"),
            text(
                "Nommer les proches d'un Pokémon.",
                "Name a Pokémon's immediate relatives.",
            ),
        ),
        QuizMode(
            "fake_name",
            text("Faux nom", "Fake name"),
            text(
                "Déterminer si un nom de Pokémon est inventé.",
                "Decide whether a Pokémon name is made up.",
            ),
        ),
        QuizMode(
            "height_order",
            text("Classer par taille", "Order by height"),
            text("Classer trois Pokémon par taille.", "Order three Pokémon by height."),
        ),
        QuizMode(
            "weight_order",
            text("Classer par poids", "Order by weight"),
            text("Classer trois Pokémon par poids.", "Order three Pokémon by weight."),
        ),
        QuizMode(
            "generation",
            text("Génération", "Generation"),
            text("Donner la génération d'un Pokémon.", "Give a Pokémon's generation."),
        ),
        QuizMode(
            "image",
            text("Par image", "By image"),
            text(
                "Reconnaître un Pokémon sur son image.",
                "Recognize a Pokémon from its picture.",
            ),
        ),
        QuizMode(
            "image_blur",
            text("Image floutée", "Blurred image"),
            text("Reconnaître un Pokémon flouté.", "Recognize a blurred Pokémon."),
        ),
        QuizMode(
            "image_pixelate",
            text("Image pixelisée", "Pixelated image"),
            text("Reconnaître un Pokémon pixelisé.", "Recognize a pixelated Pokémon."),
        ),
        QuizMode(
            "image_shadow",
            text("Ombre", "Silhouette"),
            text(
                "Reconnaître une silhouette de Pokémon.",
                "Recognize a Pokémon silhouette.",
            ),
        ),
        QuizMode(
            "name_to_number",
            text("Nom → numéro", "Name → number"),
            text(
                "Donner le numéro national d'un Pokémon.",
                "Give a Pokémon's National Pokédex number.",
            ),
        ),
        QuizMode(
            "number_to_name",
            text("Numéro → nom", "Number → name"),
            text(
                "Retrouver un Pokémon par son numéro.",
                "Identify a Pokémon from its number.",
            ),
        ),
    ]


MODES = get_modes()


def _name(pokemon: Pokemon, language: str) -> str:
    return pokemon.name.en if language == "en" else pokemon.name.fr


def _target(pokemon: Pokemon, language: str, detail: str = "") -> QuizTarget:
    return QuizTarget(
        key=str(pokemon.pokedex_id),
        label=_name(pokemon, language),
        aliases=tuple(dict.fromkeys((pokemon.name.fr, pokemon.name.en))),
        detail=detail,
    )


def _name_hint(name: str) -> str:
    letters = [letter for letter in name if letter.isalpha()]
    if not letters:
        return text(
            "Le nom contient {v0} caractères.",
            "The name has {v0} characters.",
            v0=len(name),
        )
    length = text(
        "{v0} lettre{v1}",
        "{v0} letter{v1}",
        v0=len(letters),
        v1="s" if len(letters) > 1 else "",
    )
    if len(letters) < 3:
        return text("Le nom contient {v0}.", "The name has {v0}.", v0=length)
    return text(
        "Le nom commence par {v0} et contient {v1}.",
        "The name starts with {v0} and has {v1}.",
        v0=letters[0].upper(),
        v1=length,
    )


def _identity_hint(pokemon: Pokemon, language: str) -> str:
    """Give catalogue clues without printing the name being sought."""
    clues: list[str] = []
    if pokemon.generation > 0:
        clues.append(text("Génération {v0}", "Generation {v0}", v0=pokemon.generation))

    def type_name(item: PokemonType | Mapping[str, object]) -> str:
        return str(item.get("name", "") if isinstance(item, Mapping) else item.name)

    types = [localized_type_name(type_name(item), language) for item in pokemon.types]
    if names := list(dict.fromkeys(name for name in types if name.strip())):
        clues.append(
            "Type" + ("s" if len(names) > 1 else "") + " : " + " / ".join(names)
        )
    clues.append(_name_hint(_name(pokemon, language)))
    return " · ".join(clues)


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
        title = next((mode.title for mode in get_modes() if mode.id == label), label)
        raise QuizUnavailableError(
            text(
                "Aucun Pokémon disponible pour le mode {v0}.",
                "No Pokémon is available for {v0} mode.",
                v0=title,
            )
        )
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
        raise ValueError(
            text("Mode de quiz inconnu : {v0}.", "Unknown quiz mode: {v0}.", v0=mode_id)
        )
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
        raise QuizUnavailableError(
            text("Le catalogue Pokémon est vide.", "The Pokémon catalogue is empty.")
        )

    if mode_id == "initial":
        by_initial: dict[str, list[Pokemon]] = defaultdict(list)
        for item in catalogue:
            initial = normalize_answer(_name(item, language))[:1]
            if initial:
                by_initial[initial].append(item)
        initial = chooser.choice(sorted(by_initial))
        members = sorted(by_initial[initial], key=lambda item: _name(item, language))
        generations: dict[int, int] = defaultdict(int)
        for item in members:
            if item.generation > 0:
                generations[item.generation] += 1
        return QuizQuestion(
            mode_id=mode_id,
            prompt=text(
                "Nomme les {v0} Pokémon commençant par {v1}.",
                "Name the {v0} Pokémon beginning with {v1}.",
                v0=len(members),
                v1=initial.upper(),
            ),
            targets=tuple(_target(item, language) for item in members),
            answer_kind="collection",
            hint=(
                text("Répartition : ", "Breakdown: ")
                + " · ".join(
                    text(
                        "génération {v0} : {v1}",
                        "generation {v0}: {v1}",
                        v0=generation,
                        v1=count,
                    )
                    for generation, count in sorted(generations.items())
                )
                if generations
                else text("Longueurs des noms : ", "Name lengths: ")
                + ", ".join(
                    str(sum(letter.isalpha() for letter in _name(item, language)))
                    for item in members
                )
                + text(" lettres.", " letters.")
            ),
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
                prompt=text(
                    "Nomme la pré-évolution et les évolutions immédiates de {v0}.",
                    "Name the previous evolution and immediate evolutions of {v0}.",
                    v0=name,
                ),
                targets=tuple(_target(item, language) for item in relatives),
                answer_kind="collection",
                hint=" · ".join(
                    (
                        text("Avant : ", "Before: ")
                        if item in parents[selected.pokedex_id]
                        else text("Après : ", "After: ")
                    )
                    + _name_hint(_name(item, language))
                    for item in relatives
                ),
            )
        relatives = (
            children[selected.pokedex_id]
            if mode_id == "evolution"
            else parents[selected.pokedex_id]
        )
        subject = (
            text("une évolution", "evolution")
            if mode_id == "evolution"
            else text("la pré-évolution", "previous evolution")
        )
        return QuizQuestion(
            mode_id=mode_id,
            prompt=text(
                "Nomme {v0} immédiate de {v1}.",
                "Name an immediate {v0} of {v1}.",
                v0=subject,
                v1=name,
            ),
            targets=tuple(_target(item, language) for item in relatives),
            hint=(
                text("Une possibilité : ", "One possibility: ")
                if len(relatives) > 1
                else ""
            )
            + _identity_hint(relatives[0], language),
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
                text(
                    "Il faut trois Pokémon et au moins deux mesures différentes.",
                    "Three Pokémon with at least two different measurements are needed.",
                )
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
        dimension = (
            text("taille", "height") if field == "height" else text("poids", "weight")
        )
        direction = (
            text("petit au plus grand", "shortest to tallest")
            if field == "height"
            else text("léger au plus lourd", "lightest to heaviest")
        )
        return QuizQuestion(
            mode_id=mode_id,
            prompt=text(
                "Classe par {v0}, du plus {v1} : ",
                "Order by {v0}, from {v1}: ",
                v0=dimension,
                v1=direction,
            )
            + " · ".join(_name(item, language) for item in selected),
            targets=tuple(
                _target(
                    item, language, item.height if field == "height" else item.weight
                )
                for item in ordered
            ),
            answer_kind="order",
            ordering_groups=groups,
            hint=text("{v0} est plus ", "{v0} is ", v0=_name(ordered[0], language))
            + (
                text("petit", "shorter")
                if field == "height"
                else text("léger", "lighter")
            )
            + text(" que {v0}.", " than {v0}.", v0=_name(ordered[-1], language)),
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
            prompt=text("Quel est ce Pokémon ?", "Who's that Pokémon?"),
            targets=(_target(selected, language),),
            image_url=_image_url(selected.sprites.regular),
            image_effect=effect,
            hint=_identity_hint(selected, language),
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
            prompt=text(
                "Retrouve le nom : {v0}",
                "Unscramble the name : {v0}",
                v0="".join(letters).upper(),
            ),
            targets=tuple(
                _target(item, language)
                for item in catalogue
                if sorted(normalize_answer(_name(item, language))) == sorted(original)
            ),
            hint=_identity_hint(selected, language),
        )

    if mode_id == "missing_letters":
        if missing_letters is not None and missing_letters < 1:
            raise ValueError(
                text(
                    "Le nombre de lettres manquantes doit être positif.",
                    "The number of missing letters must be positive.",
                )
            )
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
            prompt=text(
                "Complète le nom : {v0}", "Complete the name : {v0}", v0=pattern
            ),
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
            hint=text(
                "{v0} lettre{v1} manquante{v2}. ",
                "{v0} missing letter{v1}. ",
                v0=count,
                v1="s" if count > 1 else "",
                v2="s" if count > 1 else "",
            )
            + _identity_hint(selected, language),
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
            label=text("Oui", "Yes") if fake else text("Non", "No"),
            aliases=("oui", "yes", "o", "faux", "inventé")
            if fake
            else ("non", "no", "n", "réel", "vrai nom"),
        )
        return QuizQuestion(
            mode_id=mode_id,
            prompt=text(
                "« {v0} » est-il un faux nom de Pokémon ?",
                "Is “{v0}” a made-up Pokémon name?",
                v0=name,
            ),
            targets=(answer,),
            hint=text(
                "Observe chaque lettre : un nom inventé peut ne différer du vrai que d'une lettre.",
                "Look at every letter: a made-up name may differ from the real one by just one letter.",
            ),
            explanation=text(
                "« {v0} » est {v1}.",
                "“{v0}” is {v1}.",
                v0=name,
                v1=text("un nom inventé", "a made-up name")
                if fake
                else text("un vrai nom de Pokémon", "a real Pokémon name"),
            ),
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
            prompt=text(
                "Dans quelle génération apparaît {v0} ?",
                "Which generation introduced {v0}?",
                v0=name,
            ),
            targets=(
                QuizTarget(
                    str(generation),
                    text("Génération {v0}", "Generation {v0}", v0=generation),
                    aliases,
                ),
            ),
            hint=text(
                "Son numéro dans le Pokédex national est #{v0:04d}.",
                "Its National Pokédex number is #{v0:04d}.",
                v0=selected.pokedex_id,
            ),
        )
    if mode_id == "name_to_number":
        number = selected.pokedex_id
        return QuizQuestion(
            mode_id=mode_id,
            prompt=text(
                "Quel est le numéro de {v0} dans le Pokédex national ?",
                "What is {v0}'s National Pokédex number?",
                v0=name,
            ),
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
            hint=text(
                "Son numéro se situe entre #{v0:04d} ",
                "Its number is between #{v0:04d} ",
                v0=(number - 1) // 50 * 50 + 1,
            )
            + text("et #{v0:04d}.", "and #{v0:04d}.", v0=((number - 1) // 50 + 1) * 50),
        )
    return QuizQuestion(
        mode_id=mode_id,
        prompt=text(
            "Quel Pokémon porte le numéro #{v0:04d} dans le Pokédex national ?",
            "Which Pokémon is #{v0:04d} in the National Pokédex?",
            v0=selected.pokedex_id,
        ),
        targets=(_target(selected, language),),
        hint=_identity_hint(selected, language),
    )

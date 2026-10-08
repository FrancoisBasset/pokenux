import random
import re
import unicodedata

from pokenux.models.pokemon.pokemon import Pokemon
from pokenux.models.pokemon.pokemon_type import PokemonType
from pokenux.services import user_data

all_pokemon: list[Pokemon]


def get_pokemon_by_id(id: int) -> Pokemon | None:
    pokemons: list[Pokemon] = [
        pokemon for pokemon in all_pokemon if pokemon.pokedex_id == id
    ]
    return pokemons[0] if len(pokemons) != 0 else None


def get_pokemon_by_name(name: str, language: str = "en") -> Pokemon | None:
    pokemons: list[Pokemon] = [
        pokemon
        for pokemon in all_pokemon
        if _search_text(pokemon.localized_name(language)) == _search_text(name)
    ]
    return pokemons[0] if len(pokemons) != 0 else None


def get_all_pokemon_by_generation(generation: int) -> list[Pokemon]:
    return [pokemon for pokemon in all_pokemon if pokemon.generation == generation]


def get_random_pokemon() -> Pokemon:
    return random.choice(all_pokemon)


def get_all_pokemon_by_initial(
    letter: str, language: str | None = None
) -> list[Pokemon]:
    language = language or user_data.get_pokemon_lang()
    filtered_pokemon: list[Pokemon] = [
        pokemon
        for pokemon in all_pokemon
        if _search_text(pokemon.localized_name(language)).startswith(
            _search_text(letter)
        )
    ]
    filtered_pokemon.sort(key=lambda p: _search_text(p.localized_name(language)))

    return filtered_pokemon


def filter_pokemon(
    generation: list[str],
    types: list[str],
    evolutions: list[str],
    *,
    search: str = "",
    sort_by: str = "by_number",
    descending: bool = False,
    language: str | None = None,
) -> list[Pokemon]:
    """Filter the catalogue and return a new, deterministically sorted list.

    Evolution codes are independent of the interface language; the historical
    French and English labels remain accepted. Measurements in the asset data
    are expressed in metres and kilograms with decimal commas.
    """
    filtered_pokemon: list[Pokemon] = list(all_pokemon)

    if generation:
        filtered_pokemon = [
            pokemon
            for pokemon in filtered_pokemon
            if str(pokemon.generation) in generation
        ]

    if types:
        type_codes = {type_code(name) for name in types}
        filtered_pokemon = [
            pokemon
            for pokemon in filtered_pokemon
            if any(
                type_code(_type_name(type_)) in type_codes for type_ in pokemon.types
            )
        ]

    if evolutions:
        evolution_codes = {
            _EVOLUTION_CODES.get(_search_text(evolution), evolution)
            for evolution in evolutions
        }
        filtered_pokemon = [
            pokemon
            for pokemon in filtered_pokemon
            if pokemon.stage_code in evolution_codes
        ]

    query = _search_text(search.strip())
    if query:
        filtered_pokemon = [
            pokemon
            for pokemon in filtered_pokemon
            if any(
                query in _search_text(value)
                for value in (
                    pokemon.name.fr,
                    pokemon.name.en,
                    str(pokemon.pokedex_id),
                    f"#{pokemon.pokedex_id:04d}",
                )
            )
        ]

    name_language = language or user_data.get_pokemon_lang()
    if name_language not in ("fr", "en"):
        name_language = "fr"

    sort_field = sort_by.removeprefix("by_")
    stage_order = {"base": 0, "stage_1": 1, "stage_2": 2, "no_evolution": 3}

    def sort_key(pokemon: Pokemon) -> int | float | str | tuple[str, ...]:
        match sort_field:
            case "name":
                return _search_text(
                    pokemon.name.en if name_language == "en" else pokemon.name.fr
                )
            case "generation":
                return pokemon.generation
            case "type":
                return tuple(
                    _search_text(type_name(_type_name(type_), name_language))
                    for type_ in pokemon.types
                )
            case "evolution":
                return stage_order.get(pokemon.stage_code, 4)
            case "height":
                return _measurement_value(pokemon.height)
            case "weight":
                return _measurement_value(pokemon.weight)
            case _:
                return pokemon.pokedex_id

    # Keep number order for equal primary values, including descending sorts.
    filtered_pokemon.sort(key=lambda pokemon: pokemon.pokedex_id)
    filtered_pokemon.sort(key=sort_key, reverse=descending)
    return filtered_pokemon


def _search_text(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize(
            "NFKD", value.casefold().replace("œ", "oe").replace("æ", "ae")
        )
        if not unicodedata.combining(character)
    )


def _measurement_value(value: str) -> float:
    number = re.search(r"\d+(?:[,.]\d+)?", value)
    return float(number.group().replace(",", ".")) if number else float("inf")


def _type_name(pokemon_type: PokemonType | dict[str, str]) -> str:
    # from_dict retains type dictionaries; hand-built models may use dataclasses.
    return pokemon_type["name"] if isinstance(pokemon_type, dict) else pokemon_type.name


def type_code(name: str) -> str:
    """Use stable English catalogue IDs for filtering in either data language."""
    normalized = _search_text(name)
    for entry in _type_catalogue:
        if normalized in (_search_text(entry["fr"]), _search_text(entry["en"])):
            return entry["en"]
    return name


def type_name(name: str, language: str | None = None) -> str:
    language = language or user_data.get_pokemon_lang()
    code = type_code(name)
    return next(
        (
            entry.get(language, entry["en"])
            for entry in _type_catalogue
            if entry["en"] == code
        ),
        name,
    )


def pokemon_types(pokemon: Pokemon, language: str | None = None) -> list[str]:
    return [type_name(_type_name(entry), language) for entry in pokemon.types]


def stage_name(pokemon: Pokemon, language: str | None = None) -> str:
    language = language or user_data.get_pokemon_lang()
    stages = {
        "base": ("Base", "Basic"),
        "stage_1": ("Niveau 1", "Stage 1"),
        "stage_2": ("Niveau 2", "Stage 2"),
        "no_evolution": ("Sans évolution", "No evolution"),
    }
    return stages.get(pokemon.stage_code, ("", ""))[language == "en"]


_EVOLUTION_CODES = {
    "base": "base",
    "stage_1": "stage_1",
    "stage 1": "stage_1",
    "niveau 1": "stage_1",
    "stage_2": "stage_2",
    "stage 2": "stage_2",
    "niveau 2": "stage_2",
    "no_evolution": "no_evolution",
    "no evolution": "no_evolution",
    "sans evolution": "no_evolution",
}


_type_catalogue: list[dict[str, str]] = user_data.get_all_types()
all_pokemon: list[Pokemon] = user_data.get_all_pokemon()


def reload_catalogue() -> None:
    """Refresh installed assets after a catalogue update without network access."""
    global all_pokemon, _type_catalogue
    all_pokemon = user_data.get_all_pokemon()
    _type_catalogue = user_data.get_all_types()

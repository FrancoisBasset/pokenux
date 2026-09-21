import locale

from pokenux.models.pokemon.pokemon import Pokemon

import random

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
        if getattr(pokemon.name, language).lower() == name.lower()
    ]
    return pokemons[0] if len(pokemons) != 0 else None


def get_all_pokemon_by_generation(generation: int) -> list[Pokemon]:
    return [pokemon for pokemon in all_pokemon if pokemon.generation == generation]


def get_random_pokemon() -> Pokemon:
    return random.choice(all_pokemon)


def get_all_pokemon_by_initial(letter: str) -> list[Pokemon]:
    filtered_pokemon: list[Pokemon] = [
        pokemon for pokemon in all_pokemon if pokemon.name.fr[0] == letter.upper()
    ]
    filtered_pokemon.sort(key=lambda p: locale.strxfrm(p.name.fr))

    return filtered_pokemon


def filter_pokemon(
    generation: list[str], types: list[str], evolutions: list[str]
) -> list[Pokemon]:
    filtered_pokemon: list[Pokemon] = all_pokemon

    if generation:
        filtered_pokemon = [
            pokemon
            for pokemon in filtered_pokemon
            if str(pokemon.generation) in generation
        ]

    if types:
        filtered_pokemon = [
            pokemon
            for pokemon in filtered_pokemon
            if any(t["name"] in types for t in pokemon.types)
        ]

    if evolutions:
        filtered_pokemon = [
            pokemon
            for pokemon in filtered_pokemon
            if any(e in evolutions for e in pokemon.evolutions)
        ]

    return filtered_pokemon


all_pokemon: list[Pokemon] = user_data.get_all_pokemon()

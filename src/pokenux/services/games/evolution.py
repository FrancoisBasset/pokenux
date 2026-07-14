import random

from pokenux.models.pokemon.pokemon import Pokemon
from pokenux.services.pokedex import Pokedex


def get_random_pokemon_evolution() -> tuple[str, str]:
    pokedex = Pokedex()

    all_pokemon_with_evolution: list[Pokemon] = [
        pokemon for pokemon in pokedex.all_pokemon if pokemon.evolution.next is not None
    ]

    pokemon_with_evolution = random.choice(all_pokemon_with_evolution)

    return (
        pokemon_with_evolution.name.fr.lower(),
        pokemon_with_evolution.evolution.next[0]["name"].lower(),
    )

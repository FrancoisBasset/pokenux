from pokenux.services.pokedex import Pokedex
import random


def get_random_pokemon_anagram() -> tuple[str, str]:
    pokedex = Pokedex()
    random_pokemon_name: str = pokedex.get_random_pokemon().name.fr.lower()
    shuffled_name = "".join(
        random.sample(random_pokemon_name, len(random_pokemon_name))
    )

    return (shuffled_name, random_pokemon_name)

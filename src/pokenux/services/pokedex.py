import locale

from pokenux.models.pokemon.pokemon import Pokemon
from pokenux.services import jsons

import random


class Pokedex:
    all_pokemon: list[Pokemon]

    def __init__(self):
        self.all_pokemon = jsons.get_all_pokemon_from_jsons()

    def get_pokemon_by_id(self, id: int) -> Pokemon | None:
        pokemons: list[Pokemon] = [
            pokemon for pokemon in self.all_pokemon if pokemon.pokedex_id == id
        ]
        return pokemons[0] if len(pokemons) != 0 else None

    def get_pokemon_by_name(self, name: str, language: str = "en") -> Pokemon | None:
        pokemons: list[Pokemon] = [
            pokemon
            for pokemon in self.all_pokemon
            if getattr(pokemon.name, language).lower() == name.lower()
        ]
        return pokemons[0] if len(pokemons) != 0 else None

    def get_all_pokemon_by_generation(self, generation: int) -> list[Pokemon]:
        return [
            pokemon for pokemon in self.all_pokemon if pokemon.generation == generation
        ]

    def get_random_pokemon(self) -> Pokemon:
        return random.choice(self.all_pokemon)

    def get_all_pokemon_by_initial(self, letter: str) -> list[Pokemon]:
        all_pokemon: list[Pokemon] = [
            pokemon
            for pokemon in self.all_pokemon
            if pokemon.name.fr[0] == letter.upper()
        ]
        all_pokemon.sort(key=lambda p: locale.strxfrm(p.name.fr))

        return all_pokemon

import locale

from pokenux.models.pokemon.pokemon import Pokemon

import random

from pokenux.services import user_data


class Pokedex:
    all_pokemon: list[Pokemon]

    def __init__(self):
        self.all_pokemon = user_data.get_all_pokemon()

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

    def filter_pokemon(
        self, generation: list[str], types: list[str], evolutions: list[str]
    ) -> list[Pokemon]:
        filtered_pokemon: list[Pokemon] = self.all_pokemon

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

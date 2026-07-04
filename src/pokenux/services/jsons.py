import json

from pokenux.models.pokemon.pokemon import Pokemon


def get_all_pokemon_from_jsons() -> list[Pokemon]:
    with open("src/pokenux/jsons/pokemon.json", "r") as f:
        return [Pokemon.from_dict(data) for data in json.load(f)]

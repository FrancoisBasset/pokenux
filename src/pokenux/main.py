from pokenux.models.pokemon.pokemon import Pokemon
from pokenux.services.pokedex import Pokedex


def main():
    print("Running Pokenux...")

    pokedex: Pokedex = Pokedex()
    chochodile: Pokemon = pokedex.get_pokemon_by_name("Chochodile", "fr")

    print(chochodile)

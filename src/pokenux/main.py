from pokenux.models.pokemon import Pokemon
from pokenux.services.pokedex import Pokedex


def main():
    print("Running Pokenux...")

    pokedex: Pokedex = Pokedex()
    chochodile: Pokemon = pokedex.get_pokemon_by_name("Chochodile", "fr")

    if chochodile:
        print(chochodile.name.fr)

    pokemon_gen_9: list[Pokemon] = pokedex.get_all_pokemon_by_generation(9)
    print(pokemon_gen_9[3])

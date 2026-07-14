import locale

from pokenux.models.pokemon.pokemon import Pokemon
from pokenux.models.tcg.card import Card
from pokenux.models.tcg.serie import Serie
from pokenux.models.tcg.set import Set
from pokenux.services.games import anagram, evolution
from pokenux.services.pokedex import Pokedex
from pokenux.services.tcg_library import TcgLibrary


def show_all():
    tcg_library = TcgLibrary("fr")
    for serie in tcg_library.series:
        print(f"Serie: {serie.name} {serie.id}")
        for set in serie.sets:
            print(f"  Set: {set.name} {set.id}")
            for card in set.cards:
                print(f"    Card: {card.name} {card.id}")


def guess_anagram():
    [prompt, solution] = anagram.get_random_pokemon_anagram()

    try_count: int = 0
    found: bool = False

    discovered: str = ""

    while try_count < len(solution):
        guess = input(f"{prompt} : ")
        if guess == solution:
            found = True
            break

        try_count += 1

        discovered: str = "".join([solution[i] for i in range(try_count)])
        print(f"[{discovered}]")

    if found:
        print("Correct !")
    else:
        print("Raté !")


def test():
    pokedex: Pokedex = Pokedex()
    chochodile: Pokemon = pokedex.get_pokemon_by_name("Chochodile", "fr")
    print(chochodile.name.fr)

    tcg_library = TcgLibrary("fr")
    serie: Serie = tcg_library.get_serie_by_id("sv")
    print(serie.name)
    set: Set = tcg_library.get_set_by_id("sv02")
    print(set.name)

    card: Card = tcg_library.get_card_by_id("sv02-203")
    print(card.name)


def search_pokemon_card():
    tcg_library = TcgLibrary("fr")

    chochodiles: list[Card] = tcg_library.get_cards_by_name("Chochodile")
    for chochodile in chochodiles:
        set: Set = tcg_library.get_set_by_id(chochodile.set_id)
        serie: Serie = tcg_library.get_serie_by_id(set.serie_id)
        print(
            f"Chochodile card: {serie.name} {set.name} {chochodile.name} {chochodile.id} {set.name}"
        )


def guess_evolution():
    [prompt, solution] = evolution.get_random_pokemon_evolution()

    guess: str = input(f"Évolution de {prompt.capitalize()} : ")
    if guess == solution:
        print("Correct !")
    else:
        print(f"Non, c'est {solution.capitalize()}")


def guess_pre_evolution():
    [solution, prompt] = evolution.get_random_pokemon_evolution()

    guess: str = input(f"Pré-évolution de {prompt.capitalize()} : ")
    if guess == solution:
        print("Correct !")
    else:
        print(f"Non, c'est {solution.capitalize()}")


def complete_name():
    pokemon_name: str = Pokedex().get_random_pokemon().name.fr.lower()

    response: str = ""

    for i in range(1, 6):
        response = input(f"{i}/5 {pokemon_name[0:4]} : ").lower()

        if response == pokemon_name:
            print("Correct !")
            return

    print(f"Perdu, c'est {pokemon_name}")


def guess_all_pokemon_by_initial():
    letter: str = input("Lettre : ")

    all_pokemon_to_guess = Pokedex().get_all_pokemon_by_initial(letter)
    all_pokemon_names = [pokemon.name.fr.lower() for pokemon in all_pokemon_to_guess]

    count: int = 0

    while len(all_pokemon_names) > 0:
        try:
            pokemon_name: str = input(
                f"Pokémon en {letter} ({count}/{len(all_pokemon_to_guess)}) "
            )
        except KeyboardInterrupt:
            print("\nPokemon restants :")
            for pokemon_name in all_pokemon_names:
                print(f"- {pokemon_name.capitalize()}")
            break

        if pokemon_name in all_pokemon_names:
            all_pokemon_names.remove(pokemon_name)
            count += 1


def guess_pokemon_by_pokedex_id():
    pokemon: Pokemon = Pokedex().get_random_pokemon()

    response: str = input(f"Nom du Pokémon #{pokemon.pokedex_id} : ")
    if response.lower() == pokemon.name.fr.lower():
        print("Correct !")
    else:
        print(f"Non ! C'est {pokemon.name.fr}")


def guess_pokemon_id():
    pokemon: Pokemon = Pokedex().get_random_pokemon()

    response: str = input(f"ID du Pokémon {pokemon.name.fr} : ")
    if response.lower() == pokemon.pokedex_id:
        print("Correct !")
    else:
        print(f"Non ! C'est {pokemon.pokedex_id}")


def main():
    print("Running Pokenux...")

    locale.setlocale(locale.LC_COLLATE, "fr_FR.UTF-8")

    guess_pokemon_id()

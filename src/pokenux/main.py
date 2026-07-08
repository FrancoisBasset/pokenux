from pokenux.models.pokemon.pokemon import Pokemon
from pokenux.models.tcg.card import Card
from pokenux.models.tcg.serie import Serie
from pokenux.models.tcg.set import Set
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


def main():
    print("Running Pokenux...")

    # test()
    # show_all()

    tcg_library = TcgLibrary("fr")

    chochodiles: list[Card] = tcg_library.get_cards_by_name("Chochodile")
    for chochodile in chochodiles:
        set: Set = tcg_library.get_set_by_id(chochodile.set_id)
        serie: Serie = tcg_library.get_serie_by_id(set.serie_id)
        print(
            f"Chochodile card: {serie.name} {set.name} {chochodile.name} {chochodile.id} {set.name}"
        )

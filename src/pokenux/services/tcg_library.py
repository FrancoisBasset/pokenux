from pokenux.models.tcg.serie import Serie
from pokenux.services import user_data

series: list[Serie] = user_data.get_all_series(user_data.get_tcg_lang())


def set_language(language: str):
    global series

    series = user_data.get_all_series(language)


def get_serie_by_id(id: str):
    filtered_series = [serie for serie in series if serie.id == id]
    return filtered_series[0] if len(filtered_series) != 0 else None


def get_serie_by_name(name: str):
    filtered_series = [serie for serie in series if serie.name.lower() == name.lower()]
    return filtered_series[0] if len(filtered_series) != 0 else None


def get_set_by_id(id: str):
    sets = [set for serie in series for set in serie.sets if set.id == id]
    return sets[0] if len(sets) != 0 else None


def get_set_by_name(name: str):
    sets = [
        set
        for serie in series
        for set in serie.sets
        if set.name.lower() == name.lower()
    ]
    return sets[0] if len(sets) != 0 else None


def get_card_by_id(id: str):
    cards = [
        card
        for serie in series
        for set in serie.sets
        for card in set.cards
        if card.id == id
    ]
    return cards[0] if len(cards) != 0 else None


def get_cards_by_name(name: str):
    return [
        card
        for serie in series
        for set in serie.sets
        for card in set.cards
        if card.name.lower() == name.lower()
    ]

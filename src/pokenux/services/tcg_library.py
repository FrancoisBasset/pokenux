from pokenux.services import jsons


class TcgLibrary:
    def __init__(self, language: str):
        self.language = language
        self.series = jsons.get_series_from_jsons(language)

    def get_serie_by_id(self, id: str):
        series = [serie for serie in self.series if serie.id == id]
        return series[0] if len(series) != 0 else None

    def get_serie_by_name(self, name: str):
        series = [serie for serie in self.series if serie.name.lower() == name.lower()]
        return series[0] if len(series) != 0 else None

    def get_set_by_id(self, id: str):
        sets = [set for serie in self.series for set in serie.sets if set.id == id]
        return sets[0] if len(sets) != 0 else None

    def get_set_by_name(self, name: str):
        sets = [
            set
            for serie in self.series
            for set in serie.sets
            if set.name.lower() == name.lower()
        ]
        return sets[0] if len(sets) != 0 else None

    def get_card_by_id(self, id: str):
        cards = [
            card
            for serie in self.series
            for set in serie.sets
            for card in set.cards
            if card.id == id
        ]
        return cards[0] if len(cards) != 0 else None

    def get_cards_by_name(self, name: str):
        return [
            card
            for serie in self.series
            for set in serie.sets
            for card in set.cards
            if card.name.lower() == name.lower()
        ]

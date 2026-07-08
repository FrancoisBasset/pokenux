from dataclasses import dataclass

from pokenux.models.tcg.card import Card


@dataclass
class SetLegal:
    standard: bool
    expanded: bool


@dataclass
class Set:
    id: str
    name: str
    logo: str
    release_date: str
    symbol: str
    abbreviation: str
    legal: SetLegal
    cards: list[Card]
    serie_id: str

    @classmethod
    def from_dict(cls, data: dict) -> Set:
        data["legal"] = SetLegal(**data["legal"])
        data["cards"] = [Card.from_dict(card) for card in data["cards"]]
        return cls(**data)

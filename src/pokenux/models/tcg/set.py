from dataclasses import dataclass
from typing import Any

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
    def from_dict(cls, data: dict[str, Any]) -> Set:
        legal = data.get("legal") or {}
        return cls(
            id=data["id"],
            name=data["name"],
            logo=data.get("logo") or "",
            release_date=data.get("release_date") or data.get("releaseDate") or "",
            symbol=data.get("symbol") or "",
            abbreviation=data.get("abbreviation") or "",
            legal=SetLegal(
                standard=bool(legal.get("standard", False)),
                expanded=bool(legal.get("expanded", False)),
            ),
            cards=[
                Card.from_dict({"set_id": data["id"], **card})
                for card in data.get("cards", [])
            ],
            serie_id=data.get("serie_id") or (data.get("serie") or {}).get("id", ""),
        )

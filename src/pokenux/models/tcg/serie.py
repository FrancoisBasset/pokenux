from dataclasses import dataclass
from typing import Any
from pokenux.models.tcg.set import Set


@dataclass
class Serie:
    id: str
    name: str
    logo: str
    release_date: str
    sets: list[Set]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Serie:
        return cls(
            id=data["id"],
            name=data["name"],
            logo=data.get("logo") or "",
            release_date=data.get("release_date") or data.get("releaseDate") or "",
            sets=[
                Set.from_dict({"serie_id": data["id"], **card_set})
                for card_set in data.get("sets", [])
            ],
        )

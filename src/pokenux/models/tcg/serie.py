from dataclasses import dataclass
from pokenux.models.tcg.set import Set


@dataclass
class Serie:
    id: str
    name: str
    logo: str
    release_date: str
    sets: list[Set]

    @classmethod
    def from_dict(cls, data: dict) -> Serie:
        data["sets"] = [Set.from_dict(set) for set in data["sets"]]
        return cls(**data)

from dataclasses import dataclass


@dataclass
class Card:
    id: str
    name: str
    image: str
    set_id: str

    @classmethod
    def from_dict(cls, data: dict) -> Card:
        return cls(**data)

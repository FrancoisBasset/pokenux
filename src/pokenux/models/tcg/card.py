from dataclasses import dataclass, field
from typing import Any, cast


@dataclass
class Card:
    id: str
    name: str
    image: str
    set_id: str
    hp: int | None = None
    types: list[str] = field(default_factory=list)
    illustrator: str = ""
    rarity: str = ""
    category: str = ""
    local_id: str = ""
    details_loaded: bool = False
    variants: dict[str, bool] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Card:
        """Read old installed assets as well as TCGdex brief/full cards."""
        card_id = str(data["id"])
        hp = data.get("hp")
        try:
            hp = int(hp) if hp is not None else None
        except TypeError, ValueError:
            hp = None
        raw_variants = cast(object, data.get("variants"))
        variants = (
            cast(dict[object, object], raw_variants)
            if isinstance(raw_variants, dict)
            else {}
        )
        return cls(
            id=card_id,
            name=data["name"],
            image=data.get("image") or "",
            set_id=data.get("set_id")
            or (data.get("set") or {}).get("id")
            or card_id.rsplit("-", 1)[0],
            hp=hp,
            types=list(data.get("types") or []),
            illustrator=data.get("illustrator") or "",
            rarity=data.get("rarity") or "",
            category=data.get("category") or "",
            local_id=str(
                data.get("local_id")
                or data.get("localId")
                or card_id.rsplit("-", 1)[-1]
            ),
            details_loaded=bool(data.get("details_loaded", "category" in data)),
            variants={
                key: value
                for key, value in variants.items()
                if isinstance(key, str) and isinstance(value, bool)
            },
        )

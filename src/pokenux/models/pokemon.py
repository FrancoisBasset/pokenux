from dataclasses import dataclass

from pokenux.models.pokemon_name import PokemonName
from pokenux.models.pokemon_sprite import PokemonSprite
from pokenux.models.pokemon_type import PokemonType
from pokenux.models.pokemon_talent import PokemonTalent
from pokenux.models.pokemon_stat import PokemonStat
from pokenux.models.pokemon_resistance import PokemonResistance
from pokenux.models.pokemon_evolutions import PokemonEvolutions
from pokenux.models.pokemon_sex import PokemonSex
from pokenux.services.utils import filter_valid_fields


@dataclass
class Pokemon:
    pokedex_id: int
    generation: int
    name: PokemonName
    category: str
    sprites: PokemonSprite
    types: list[PokemonType]
    talents: list[PokemonTalent]
    stats: PokemonStat
    resistances: list[PokemonResistance]
    evolution: PokemonEvolutions
    height: str
    weight: str
    egg_groups: list[str]
    sex: PokemonSex | None
    catch_rate: int

    @classmethod
    def from_dict(cls, data: dict) -> Pokemon:
        data = data.copy()

        del data["name"]["jp"]
        data["name"] = PokemonName(**data["name"])

        if data["talents"]:
            data["talents"] = [
                PokemonTalent(name=t["name"], hidden=t["tc"]) for t in data["talents"]
            ]

        sexe = data.pop("sexe", None)
        data["sex"] = PokemonSex(**sexe) if sexe else None

        return cls(**filter_valid_fields(data, cls))

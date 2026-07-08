from dataclasses import dataclass

from pokenux.models.pokemon.pokemon_name import PokemonName
from pokenux.models.pokemon.pokemon_sprite import PokemonSprite
from pokenux.models.pokemon.pokemon_type import PokemonType
from pokenux.models.pokemon.pokemon_talent import PokemonTalent
from pokenux.models.pokemon.pokemon_stat import PokemonStat
from pokenux.models.pokemon.pokemon_resistance import PokemonResistance
from pokenux.models.pokemon.pokemon_evolutions import PokemonEvolutions
from pokenux.models.pokemon.pokemon_sex import PokemonSex


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

        data["name"] = PokemonName(**data["name"])
        data["sprites"] = PokemonSprite(**data["sprites"])
        data["talents"] = [PokemonTalent(**talent) for talent in data["talents"]]
        data["stats"] = PokemonStat(**data["stats"])
        data["resistances"] = [
            PokemonResistance(**resistance) for resistance in data["resistances"]
        ]
        data["evolution"] = PokemonEvolutions(**data["evolution"])
        if data["sex"] is not None:
            data["sex"] = PokemonSex(**data["sex"])

        return cls(**data)

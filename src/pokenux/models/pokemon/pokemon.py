from dataclasses import dataclass, field

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
    category_en: str = ""
    egg_groups_en: list[str] = field(default_factory=list)

    def localized_name(self, language: str) -> str:
        return self.name.en if language == "en" else self.name.fr

    def localized_category(self, language: str) -> str:
        return self.category_en if language == "en" else self.category

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

    @property
    def stage_code(self) -> str:
        if not self.evolution.pre and self.evolution.next:
            return "base"
        if len(self.evolution.pre or []) == 1:
            return "stage_1"
        if len(self.evolution.pre or []) == 2:
            return "stage_2"
        if not self.evolution.pre and not self.evolution.next:
            return "no_evolution"

        return ""

    @property
    def stage(self) -> str:
        return {
            "base": "Base",
            "stage_1": "Niveau 1",
            "stage_2": "Niveau 2",
            "no_evolution": "Sans évolution",
        }.get(self.stage_code, "")

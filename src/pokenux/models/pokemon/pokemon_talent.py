from dataclasses import dataclass


@dataclass
class PokemonTalent:
    name: str
    hidden: bool
    name_en: str = ""

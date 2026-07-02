from dataclasses import dataclass


@dataclass
class PokemonStat:
    hp: int
    attack: int
    defense: int
    special_attack: int
    special_defense: int
    speed: int

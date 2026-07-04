from dataclasses import dataclass


@dataclass
class PokemonSpriteGmax:
    regular: str
    shiny: str


@dataclass
class PokemonSprite:
    regular: str
    shiny: str
    gmax: PokemonSpriteGmax | None

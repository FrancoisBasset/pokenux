from dataclasses import dataclass

from pokenux.models.pokemon_sprite import PokemonSprite


@dataclass
class PokemonMegaEvolution:
    orbe: str
    sprites: PokemonSprite

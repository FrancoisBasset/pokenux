from dataclasses import dataclass

from pokenux.models.pokemon.pokemon_evolution import PokemonEvolution
from pokenux.models.pokemon.pokemon_mega_evolution import PokemonMegaEvolution


@dataclass
class PokemonEvolutions:
    pre: list[PokemonEvolution]
    next: list[PokemonEvolution]
    mega: list[PokemonMegaEvolution]

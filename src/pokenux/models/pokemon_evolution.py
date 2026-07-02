from dataclasses import dataclass


@dataclass
class PokemonEvolution:
    pokedex_id: int
    name: str
    condition: str

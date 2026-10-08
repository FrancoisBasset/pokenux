from dataclasses import dataclass


@dataclass
class PokemonType:
    name: str
    image: str


_TYPE_NAMES = dict(
    zip(
        (
            "Normal",
            "Feu",
            "Eau",
            "Plante",
            "Électrik",
            "Glace",
            "Combat",
            "Poison",
            "Sol",
            "Vol",
            "Psy",
            "Insecte",
            "Roche",
            "Spectre",
            "Dragon",
            "Ténèbres",
            "Acier",
            "Fée",
        ),
        (
            "Normal",
            "Fire",
            "Water",
            "Grass",
            "Electric",
            "Ice",
            "Fighting",
            "Poison",
            "Ground",
            "Flying",
            "Psychic",
            "Bug",
            "Rock",
            "Ghost",
            "Dragon",
            "Dark",
            "Steel",
            "Fairy",
        ),
    )
)


def localized_type_name(name: str, language: str) -> str:
    """Translate the official type names without loading a catalogue or UI."""
    if language == "en":
        return _TYPE_NAMES.get(name, name)
    return next((fr for fr, en in _TYPE_NAMES.items() if en == name), name)

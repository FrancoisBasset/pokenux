"""Consistent, readable Pokémon type accents for the Pokédex."""

from collections.abc import Iterable

from rich.text import Text


TYPE_COLORS: dict[str, str] = {
    "Normal": "#b8bac8",
    "Feu": "#f5a373",
    "Eau": "#83b7ff",
    "Plante": "#91d49a",
    "Électrik": "#efcf77",
    "Glace": "#8ad8dc",
    "Combat": "#e79b89",
    "Poison": "#c9a1f4",
    "Sol": "#d6b989",
    "Vol": "#aebbf0",
    "Psy": "#f3a0c3",
    "Insecte": "#bed37d",
    "Roche": "#c9bd93",
    "Spectre": "#b1a4dc",
    "Dragon": "#afa2f6",
    "Ténèbres": "#bcaea4",
    "Acier": "#a7c4d1",
    "Fée": "#f0b0d5",
}


# Both official name sets share the same visual type identity.
for _english, _french in zip(
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
    tuple(TYPE_COLORS),
):
    TYPE_COLORS[_english] = TYPE_COLORS[_french]


def type_badges(names: Iterable[str]) -> Text:
    badges = Text()
    for index, name in enumerate(names):
        if index:
            _ = badges.append(" ")
        _ = badges.append(
            f" {name} ", style=f"bold {TYPE_COLORS.get(name, '#e4ebf5')} on #1c2c40"
        )
    return badges

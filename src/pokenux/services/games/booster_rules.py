"""Estimated euro prices and era profiles; these are game rules, not quotations."""

from dataclasses import dataclass
from datetime import date
from typing import Literal

from pokenux.services.localization import text
from pokenux.models.tcg.card import Card
from pokenux.models.tcg.set import Set
from pokenux.services.games.quiz import normalize_answer


RarityGroup = Literal[
    "common",
    "uncommon",
    "rare",
    "holo",
    "double",
    "ultra",
    "illustration",
    "special",
    "hyper",
    "energy",
]


@dataclass(frozen=True)
class BoosterRules:
    era: str
    common: int
    uncommon: int
    reverse: int
    rare: int = 1
    energy: int = 0
    special_foil: int = 0

    @property
    def card_count(self) -> int:
        return (
            self.common
            + self.uncommon
            + self.reverse
            + self.rare
            + self.energy
            + self.special_foil
        )

    @property
    def composition(self) -> str:
        if self.era == "anniversary":
            return text(
                "5 cartes holographiques dont 1 Pikachu garanti · répartition estimée · Énergie bonus non simulée",
                "5 holographic cards including 1 guaranteed Pikachu · estimated distribution · bonus Energy not simulated",
            )
        if self.era == "anniversary_classic":
            return text(
                "3 cartes holographiques de la Collection Classique · répartition estimée",
                "3 holographic Classic Collection cards · estimated distribution",
            )
        if self.special_foil:
            return text(
                f"{self.special_foil} cartes holographiques, répartition simplifiée estimée",
                f"{self.special_foil} holographic cards, simplified estimated distribution",
            )
        parts = [
            text(f"{self.common} communes", f"{self.common} common"),
            text(f"{self.uncommon} peu communes", f"{self.uncommon} uncommon"),
        ]
        if self.energy:
            parts.append(
                text(
                    f"{self.energy} énergies (ou communes si non identifiées)",
                    f"{self.energy} Energy (or common if unidentified)",
                )
            )
        if self.reverse:
            parts.append(
                text(
                    f"{self.reverse} emplacements Reverse",
                    f"{self.reverse} Reverse slots",
                )
            )
        parts.append(text("1 rare ou mieux", "1 rare or better"))
        return " · ".join(parts)


_EXCLUDED_SERIES = {"tcgp", "tk", "mc", "misc", "pop"}
_EXCLUDED_SETS = {
    "basep",
    "wp",
    "np",
    "dpp",
    "hgssp",
    "bwp",
    "xyp",
    "smp",
    "swshp",
    "svp",
    "mep",
    "sve",
    "mee",
    "xy0",
    "xya",
    "exu",
    "rc",
    "sma",
    # Célébrations mixes its main set with a separate Classic Collection;
    # this catalogue does not model that collation across two sets.
    "cel25",
    "cel25cc",
    "swsh4.5sv",
    "dc1",
    "dv1",
}


def supports_booster(card_set: Set, serie_id: str) -> bool:
    # The Classic Collection has its own three-card booster in the 30th UPC.
    if card_set.id == "30th-c":
        return True
    name = normalize_answer(card_set.name)
    return (
        serie_id not in _EXCLUDED_SERIES
        and card_set.id not in _EXCLUDED_SETS
        and not card_set.id.endswith(("tg", "gg"))
        and not any(
            word in name
            for word in (
                "promo",
                "galeried",
                "kitdresseur",
                "coffreetincelant",
                "collectionclassique",
            )
        )
    )


def rules_for_set(card_set: Set, serie_id: str) -> BoosterRules:
    if card_set.id == "30th":
        return BoosterRules("anniversary", 0, 0, 0, rare=0, special_foil=5)
    if card_set.id == "30th-c":
        return BoosterRules("anniversary_classic", 0, 0, 0, rare=0, special_foil=3)
    if card_set.id == "det1":
        return BoosterRules("special", 0, 0, 0, rare=0, special_foil=4)
    if serie_id in {"base", "neo"}:
        return BoosterRules("vintage", 5, 3, 0, energy=2)
    if serie_id in {"ecard", "ex"}:
        return BoosterRules("ex", 5, 2, 1)
    if serie_id in {"sv", "me"}:
        return BoosterRules("modern", 4, 3, 2)
    try:
        year = date.fromisoformat(card_set.release_date).year
    except ValueError:
        year = 2025
    if year <= 2001:
        return BoosterRules("vintage", 5, 3, 0, energy=2)
    if year <= 2006:
        return BoosterRules("ex", 5, 2, 1)
    if year >= 2023:
        return BoosterRules("modern", 4, 3, 2)
    return BoosterRules("legacy", 5, 3, 1)


_PRICE_OVERRIDES = {
    "base1": 59900,
    "base2": 24900,
    "base3": 24900,
    "base5": 34900,
    "neo3": 44900,
    "neo4": 54900,
    "xy12": 4999,
    "sm12": 2499,
    "swsh7": 3499,
    "swsh12.5": 1299,
    "det1": 999,
    "sv03.5": 1499,
    "sv3.5": 1499,
    "sv04.5": 999,
    "sv4.5": 999,
    "sv06.5": 999,
    "sv6.5": 999,
    "sv08.5": 1499,
    "sv8.5": 1499,
    "sv08": 799,
    "sv8": 799,
    "me02.5": 1299,
}


def estimated_price(card_set: Set, serie_id: str) -> int:
    """Stable guide estimates, varying by era and named premium/special sets."""
    if card_set.id in _PRICE_OVERRIDES:
        return _PRICE_OVERRIDES[card_set.id]
    if ".5" in card_set.id and serie_id in {"sv", "me", "swsh"}:
        return 999
    by_era = {
        "base": 24900,
        "neo": 29900,
        "ecard": 44900,
        "ex": 24900,
        "dp": 14900,
        "pl": 12900,
        "hgss": 11900,
        "col": 9900,
        "bw": 7900,
        "xy": 2999,
        "sm": 1599,
        "swsh": 899,
        "sv": 599,
        "me": 599,
    }
    if serie_id in by_era:
        return by_era[serie_id]
    try:
        year = date.fromisoformat(card_set.release_date).year
    except ValueError:
        year = 2025
    return next(
        price
        for cutoff, price in (
            (2001, 24900),
            (2006, 24900),
            (2010, 12900),
            (2013, 7900),
            (2016, 2999),
            (2019, 1599),
            (2022, 899),
            (9999, 599),
        )
        if year <= cutoff
    )


_GROUP_NAMES: dict[RarityGroup, tuple[str, ...]] = {
    "common": ("Common", "Commune"),
    "uncommon": ("Uncommon", "Peu Commune"),
    "rare": ("Rare",),
    "holo": ("Holo Rare", "Rare Holo", "Rare Holographique"),
    "double": ("Double rare", "Holo Rare V", "Holo Rare VMAX", "Holo Rare VSTAR"),
    "ultra": (
        "Ultra Rare",
        "Full Art Trainer",
        "Dresseur Full Art",
        "Rare Holo LV.X",
        "Rare PRIME",
        "Rare Prime",
        "LEGEND",
        "LÉGENDE",
        "ACE SPEC Rare",
        "HIGH-TECH rare",
        "Shiny Ultra Rare",
        "Chromatique ultra rare",
        "Shiny rare V",
        "Shiny rare VMAX",
    ),
    "illustration": (
        "Illustration rare",
        "Shiny rare",
        "Amazing Rare",
        "Magnifique",
        "Magnifique rare",
        "Radiant Rare",
        "Radieux Rare",
    ),
    "special": (
        "Special illustration rare",
        "Illustration spéciale rare",
        "Mega Attack Rare",
        "Classic Collection",
        "Collection Classique",
    ),
    "hyper": (
        "Hyper rare",
        "Secret Rare",
        "Mega Hyper Rare",
        "Méga Hyper Rare",
        "Pikachu Rare",
        "RGB Rare",
        "Futuristic Rare",
        "Black White Rare",
        "Rare Noir Blanc",
    ),
    "energy": (),
}
_GROUP_BY_NAME: dict[str, RarityGroup] = {
    normalize_answer(name): group
    for group, names in _GROUP_NAMES.items()
    for name in names
}


def rarity_group(card: Card) -> RarityGroup | None:
    # These officially unranked cards belong to a dedicated all-holo product.
    # Keep their displayed rarity intact; this group only drives the simulation.
    if card.set_id == "30th-c" and normalize_answer(card.rarity) in {
        "none",
        "sansrarete",
    }:
        return "holo"
    group = _GROUP_BY_NAME.get(normalize_answer(card.rarity))
    energy = normalize_answer(card.category) in {"energy", "energie", "energies"}
    if energy and (
        group == "common" or normalize_answer(card.rarity) in {"none", "sansrarete"}
    ):
        return "energy"
    return group


def is_anniversary_pikachu(card: Card) -> bool:
    return card.set_id == "30th" and normalize_answer(card.rarity) == "pikachurare"


def estimated_card_value(card: Card, finish: str, era: str) -> int:
    if is_anniversary_pikachu(card):
        # A guaranteed slot is ordinary foil bulk in the game's economy,
        # rather than the high-value hyper hit used by other rarity labels.
        return 50
    group = rarity_group(card)
    if group is None:
        return 3
    if group in {"common", "uncommon", "energy"}:
        bulk = (
            {"common": 50, "uncommon": 100, "energy": 20}
            if era == "vintage"
            else {"common": 10, "uncommon": 20, "energy": 5}
            if era == "ex"
            else {"common": 3, "uncommon": 5, "energy": 2}
        )
        base = bulk[group]
        return (
            max(base, 60 if era == "ex" else 10 if group != "uncommon" else 15)
            if finish == "Reverse"
            else base
        )
    if group == "rare" and finish == "Holographique":
        group = "holo"
    values = {
        "rare": 15,
        "holo": 60,
        "double": 150,
        "ultra": 600,
        "illustration": 450,
        "special": 2500,
        "hyper": 4000,
    }
    value = values.get(group, 3)
    if finish == "Reverse":
        return 35
    if era == "vintage":
        value = {
            "rare": 500,
            "holo": 2500,
            "double": 5000,
            "ultra": 10000,
            "special": 20000,
            "hyper": 30000,
        }.get(group, value)
        if group == "holo" and any(
            name in normalize_answer(card.name)
            for name in ("dracaufeu", "charizard", "noctali", "umbreon")
        ):
            value = 20000
    elif era == "ex":
        value = {
            "rare": 150,
            "holo": 1000,
            "double": 2500,
            "ultra": 5000,
            "special": 12000,
            "hyper": 20000,
        }.get(group, value)
    if group in {"special", "hyper"} and any(
        name in normalize_answer(card.name)
        for name in ("dracaufeu", "charizard", "noctali", "umbreon")
    ):
        value *= 2
    return value

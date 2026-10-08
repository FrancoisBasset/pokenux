"""Load genuine TCGdex booster metadata without fetching every full card.

TCGdex's exact filters return complete brief lists unless pagination is requested.
Querying those lists by rarity and category classifies an extension with a small
number of requests, retaining the caller's installed names, images and order.
"""

from collections.abc import Callable
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal, TypedDict, cast
import unicodedata
from urllib.parse import quote

import requests

from pokenux.services.localization import text
from pokenux.models.tcg.card import Card
from pokenux.services.api.tcgdex import TCGdexError


class BoosterCatalogueError(TCGdexError):
    """Real card metadata is unavailable or incomplete; buying must stay disabled."""


_VERSION = 2
_CORE_VARIANTS = {"normal", "holo", "reverse"}


class _Metadata(TypedDict):
    rarity: str
    category: str
    variants: dict[str, bool]


def _variants_complete(variants: dict[str, bool]) -> bool:
    return _CORE_VARIANTS.issubset(variants) and any(
        variants[variant] for variant in _CORE_VARIANTS
    )


def _check_cancelled(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        raise BoosterCatalogueError(text("Chargement annulé.", "Loading cancelled."))


def _fetch(
    language: str, endpoint: str, params: dict[str, str] | None = None
) -> object:
    """Bounded synchronous HTTP helper, replaceable in offline tests."""
    try:
        response = requests.get(
            f"https://api.tcgdex.net/v2/{quote(language, safe='')}/{endpoint}",
            params=params,
            timeout=(5, 15),
        )
        response.raise_for_status()
        return cast(object, response.json())
    except (requests.RequestException, ValueError) as error:
        raise BoosterCatalogueError(
            text(
                "TCGdex est indisponible. Réessaie pour charger les raretés officielles.",
                "TCGdex is unavailable. Retry to load official rarities.",
            )
        ) from error


def _labels(language: str, endpoint: str) -> list[str]:
    result = _fetch(language, endpoint)
    if not isinstance(result, list) or not result:
        raise BoosterCatalogueError(
            text(
                "TCGdex a renvoyé une liste de valeurs invalide.",
                "TCGdex returned an invalid list of values.",
            )
        )
    values: list[str] = []
    for item in cast(list[object], result):
        if not isinstance(item, str) or not item.strip():
            raise BoosterCatalogueError(
                text(
                    "TCGdex a renvoyé une liste de valeurs invalide.",
                    "TCGdex returned an invalid list of values.",
                )
            )
        if item not in values:
            values.append(item)
    return values


def _normalized(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value.casefold())
        if character.isalnum()
    )


def _priority(value: str) -> int:
    # These are request priorities only: returned labels retain their exact
    # official spelling, and every other language/rarity remains supported.
    order = {
        "common": 0,
        "commune": 0,
        "pokemon": 0,
        "uncommon": 1,
        "peucommune": 1,
        "trainer": 1,
        "dresseur": 1,
        "rare": 2,
        "energy": 2,
        "energie": 2,
        "holorare": 3,
        "rareholo": 3,
        "doublerare": 4,
        "ultrarare": 5,
        "illustrationrare": 6,
        "illustrationspecialerare": 7,
        "specialillustrationrare": 7,
        "hyperrare": 8,
        "none": 9,
        "sansrarete": 9,
    }
    return order.get(_normalized(value), 10)


def _cache_file(cache_path: Path, language: str, set_id: str) -> Path:
    digest = sha256(f"{language}:{set_id}".encode("utf-8")).hexdigest()
    return cache_path / f"{digest}.json"


def _read_cache(path: Path, language: str, set_id: str) -> dict[str, _Metadata]:
    try:
        raw = cast(object, json.loads(path.read_text(encoding="utf-8")))
        if not isinstance(raw, dict):
            return {}
        data = cast(dict[str, object], raw)
        if (
            data.get("version") != _VERSION
            or data.get("language") != language
            or data.get("set_id") != set_id
        ):
            return {}
        raw_cards = data.get("cards")
        if not isinstance(raw_cards, dict):
            return {}
        cards: dict[str, _Metadata] = {}
        for card_id, raw_metadata in cast(dict[object, object], raw_cards).items():
            if not isinstance(card_id, str) or not isinstance(raw_metadata, dict):
                return {}
            metadata = cast(dict[str, object], raw_metadata)
            rarity, category = metadata.get("rarity"), metadata.get("category")
            if (
                not isinstance(rarity, str)
                or not rarity.strip()
                or not isinstance(category, str)
                or not category.strip()
            ):
                return {}
            raw_variants = metadata.get("variants")
            if not isinstance(raw_variants, dict):
                return {}
            variants: dict[str, bool] = {}
            for key, value in cast(dict[object, object], raw_variants).items():
                if not isinstance(key, str) or not isinstance(value, bool):
                    return {}
                variants[key] = value
            if not _variants_complete(variants):
                return {}
            cards[card_id] = {
                "rarity": rarity,
                "category": category,
                "variants": variants,
            }
        return cards
    except OSError, ValueError:
        return {}


def _write_cache(
    path: Path, language: str, set_id: str, metadata: dict[str, _Metadata]
) -> None:
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w", dir=path.parent, encoding="utf-8", delete=False
        ) as file:
            temporary = Path(file.name)
            json.dump(
                {
                    "version": _VERSION,
                    "language": language,
                    "set_id": set_id,
                    "cards": metadata,
                },
                file,
                ensure_ascii=False,
            )
        _ = temporary.replace(path)
    except OSError:
        # A successful classification remains usable when cache storage fails.
        pass
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _classify(
    language: str,
    set_id: str,
    metadata: dict[str, _Metadata],
    field: Literal["rarity", "category"],
    endpoint: str,
    cancelled: Callable[[], bool] | None,
) -> None:
    missing = {card_id for card_id, values in metadata.items() if not values[field]}
    if not missing:
        return
    _check_cancelled(cancelled)
    labels = sorted(_labels(language, endpoint), key=_priority)
    assigned: dict[str, str] = {}
    for label in labels:
        _check_cancelled(cancelled)
        response = _fetch(
            language,
            "cards",
            {"set.id": f"eq:{set_id}", field: f"eq:{label}"},
        )
        if not isinstance(response, list):
            raise BoosterCatalogueError(
                text(
                    "TCGdex a renvoyé une liste de cartes invalide.",
                    "TCGdex returned an invalid list of cards.",
                )
            )
        for item in cast(list[object], response):
            if not isinstance(item, dict):
                raise BoosterCatalogueError(
                    text(
                        "TCGdex a renvoyé une carte invalide.",
                        "TCGdex returned an invalid card.",
                    )
                )
            card_id = cast(dict[str, object], item).get("id")
            if not isinstance(card_id, str) or not card_id:
                raise BoosterCatalogueError(
                    text(
                        "TCGdex a renvoyé une carte invalide.",
                        "TCGdex returned an invalid card.",
                    )
                )
            if card_id not in missing:
                continue
            if card_id in assigned and assigned[card_id] != label:
                raise BoosterCatalogueError(
                    text(
                        "TCGdex a renvoyé des classifications contradictoires.",
                        "TCGdex returned conflicting classifications.",
                    )
                )
            assigned[card_id] = label
            metadata[card_id][field] = label
        if missing.issubset(assigned):
            break
    _check_cancelled(cancelled)
    if not missing.issubset(assigned):
        raise BoosterCatalogueError(
            text(
                f"Les informations officielles de l’extension {set_id} sont incomplètes ",
                f"The official information for set {set_id} is incomplete ",
            )
            + text(
                f"({len(missing - assigned.keys())} carte(s) sans {field}). Réessaie.",
                f"({len(missing - assigned.keys())} cards missing {field}). Please retry.",
            )
        )


def _load_variants(
    language: str,
    set_id: str,
    metadata: dict[str, _Metadata],
    cancelled: Callable[[], bool] | None,
) -> None:
    missing = {
        card_id
        for card_id, values in metadata.items()
        if not _variants_complete(values["variants"])
    }
    if not missing:
        return
    _check_cancelled(cancelled)
    labels = _labels(language, "variants")
    if not _CORE_VARIANTS.issubset(labels):
        raise BoosterCatalogueError(
            text(
                "TCGdex a renvoyé une liste de variantes incomplète.",
                "TCGdex returned an incomplete list of variants.",
            )
        )
    assigned = {card_id: dict.fromkeys(labels, False) for card_id in missing}
    for label in labels:
        _check_cancelled(cancelled)
        # REST's strict string equality (eq:true) does not match booleans.
        # The plain boolean filter does: base1 yields 16 holo / 86 normal.
        response = _fetch(
            language,
            "cards",
            {"set.id": f"eq:{set_id}", f"variants.{label}": "true"},
        )
        if not isinstance(response, list):
            raise BoosterCatalogueError(
                text(
                    "TCGdex a renvoyé une liste de cartes invalide.",
                    "TCGdex returned an invalid list of cards.",
                )
            )
        for item in cast(list[object], response):
            if not isinstance(item, dict):
                raise BoosterCatalogueError(
                    text(
                        "TCGdex a renvoyé une carte invalide.",
                        "TCGdex returned an invalid card.",
                    )
                )
            card_id = cast(dict[str, object], item).get("id")
            if not isinstance(card_id, str) or not card_id:
                raise BoosterCatalogueError(
                    text(
                        "TCGdex a renvoyé une carte invalide.",
                        "TCGdex returned an invalid card.",
                    )
                )
            if card_id in assigned:
                assigned[card_id][label] = True
    _check_cancelled(cancelled)
    if any(not _variants_complete(variants) for variants in assigned.values()):
        raise BoosterCatalogueError(
            text(
                f"Les variantes officielles de l’extension {set_id} sont incomplètes. ",
                f"The official variants for set {set_id} are incomplete. ",
            )
            + text(
                "Réessaie avant d’ouvrir un booster.", "Retry before opening a booster."
            )
        )
    for card_id, variants in assigned.items():
        metadata[card_id]["variants"] = variants


def load_booster_cards(
    language: str,
    set_id: str,
    cards: list[Card],
    cache_path: Path,
    *,
    cancelled: Callable[[], bool] | None = None,
) -> list[Card]:
    """Classify all supplied cards or fail, keeping purchases disabled on failure.

    ``cache_path`` is the cache directory, normally ``user_data.path / 'cache' /
    'boosters'``. Call from a worker. No installed catalogue, game database or
    input card is modified; partial metadata is never saved as a valid cache.
    """
    _check_cancelled(cancelled)
    if not language.strip() or not set_id.strip():
        raise BoosterCatalogueError(
            text("Langue ou extension manquante.", "Missing language or set.")
        )
    if any(card.set_id != set_id or not card.id for card in cards):
        raise BoosterCatalogueError(
            text(
                "Le catalogue contient une carte d’une autre extension.",
                "The catalogue includes a card from another set.",
            )
        )
    if len({card.id for card in cards}) != len(cards):
        raise BoosterCatalogueError(
            text(
                "Le catalogue contient des identifiants de cartes répétés.",
                "The catalogue contains duplicate card identifiers.",
            )
        )
    if not cards:
        return []
    if all(
        card.rarity.strip()
        and card.category.strip()
        and _variants_complete(card.variants)
        for card in cards
    ):
        return [replace(card, variants=dict(card.variants)) for card in cards]
    path = _cache_file(cache_path, language, set_id)
    cached = _read_cache(path, language, set_id)
    metadata: dict[str, _Metadata] = {}
    for card in cards:
        previous = cached.get(card.id)
        metadata[card.id] = {
            "rarity": card.rarity.strip() or (previous["rarity"] if previous else ""),
            "category": card.category.strip()
            or (previous["category"] if previous else ""),
            "variants": dict(card.variants)
            if _variants_complete(card.variants)
            else dict(previous["variants"])
            if previous
            else {},
        }
    _classify(language, set_id, metadata, "rarity", "rarities", cancelled)
    _classify(language, set_id, metadata, "category", "categories", cancelled)
    _load_variants(language, set_id, metadata, cancelled)
    _check_cancelled(cancelled)
    _write_cache(path, language, set_id, {**cached, **metadata})
    return [replace(card, **metadata[card.id]) for card in cards]

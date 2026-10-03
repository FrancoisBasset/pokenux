"""Installed TCG catalogue and bounded, cached searches for missing metadata.

Importing this module only reads installed assets. The online functions are
synchronous so callers can run them in a Textual worker without blocking input.
"""

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
import time
from typing import Any, cast
import unicodedata

from pokenux.models.tcg.card import Card
from pokenux.models.tcg.serie import Serie
from pokenux.models.tcg.set import Set
from pokenux.services import user_data
from pokenux.services.api import tcgdex


@dataclass(frozen=True)
class LanguageStatus:
    requested: str
    active: str
    available: tuple[str, ...]
    warning: str = ""


@dataclass
class SearchResult:
    cards: list[Card]
    source: str = "local"
    warning: str = ""


class SearchUnavailableError(tcgdex.TCGdexError):
    """Required metadata cannot be searched completely without the network."""


series: list[Serie] = []
_language_status = LanguageStatus("en", "en", ())
_details: dict[tuple[str, str], Card] = {}
_SEARCH_CACHE_SECONDS = 24 * 60 * 60
_TYPE_NAMES = {
    "fr": (
        "Plante",
        "Feu",
        "Eau",
        "Électrique",
        "Psy",
        "Combat",
        "Obscurité",
        "Métal",
        "Incolore",
        "Dragon",
        "Fée",
    ),
    "en": (
        "Grass",
        "Fire",
        "Water",
        "Lightning",
        "Psychic",
        "Fighting",
        "Darkness",
        "Metal",
        "Colorless",
        "Dragon",
        "Fairy",
    ),
}


def normalize(value: str) -> str:
    """Case/accent-insensitive matching, also used by the local catalogue UI."""
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", value.casefold().strip())
        if not unicodedata.combining(char)
    )


def set_language(language: str) -> LanguageStatus:
    """Load installed assets, exposing any fallback instead of silently failing."""
    global series, _language_status
    available = tuple(
        sorted(
            path.stem.removeprefix("tcg_")
            for path in (user_data.assets_path / "data").glob("tcg_*.json")
        )
    )
    candidates = list(dict.fromkeys((language, "fr", "en", *available)))
    for candidate in candidates:
        try:
            loaded = user_data.get_all_series(candidate)
        except OSError, ValueError, KeyError, TypeError:
            continue
        series = loaded
        warning = (
            ""
            if candidate == language
            else (
                f"Catalogue {language.upper()} indisponible : données {candidate.upper()} affichées."
            )
        )
        _language_status = LanguageStatus(language, candidate, available, warning)
        return _language_status
    series = []
    _language_status = LanguageStatus(
        language, language, available, "Aucun catalogue TCG installé."
    )
    return _language_status


def get_language_status() -> LanguageStatus:
    return _language_status


def get_sets(serie_id: str | None = None) -> list[Set]:
    return [
        card_set
        for serie in series
        if not serie_id or serie.id == serie_id
        for card_set in serie.sets
    ]


def get_types() -> list[str]:
    types = set(_TYPE_NAMES.get(_language_status.active, ()))
    for card_set in get_sets():
        for card in card_set.cards:
            types.update(_details.get((_language_status.active, card.id), card).types)
    return sorted(types, key=normalize)


def get_serie_by_id(id: str) -> Serie | None:
    return next((serie for serie in series if serie.id == id), None)


def get_serie_by_name(name: str) -> Serie | None:
    return next(
        (serie for serie in series if normalize(serie.name) == normalize(name)), None
    )


def get_set_by_id(id: str) -> Set | None:
    return next((card_set for card_set in get_sets() if card_set.id == id), None)


def get_set_by_name(name: str) -> Set | None:
    return next(
        (
            card_set
            for card_set in get_sets()
            if normalize(card_set.name) == normalize(name)
        ),
        None,
    )


def get_card_by_id(id: str) -> Card | None:
    cached = _details.get((_language_status.active, id))
    if cached is not None:
        return cached
    return next(
        (card for card_set in get_sets() for card in card_set.cards if card.id == id),
        None,
    )


def get_cards_by_name(name: str) -> list[Card]:
    """Retain the existing exact-name lookup used by Pokémon consumers."""
    return [
        card
        for card in search_cards(name=name)
        if normalize(card.name) == normalize(name)
    ]


def _validate_hp(hp: int | None, hp_min: int | None, hp_max: int | None) -> None:
    if any(
        value is not None
        and (isinstance(value, bool) or not isinstance(value, int) or value < 0)
        for value in (hp, hp_min, hp_max)
    ):
        raise ValueError("Les PV doivent être des nombres entiers positifs ou nuls.")
    if hp_min is not None and hp_max is not None and hp_min > hp_max:
        raise ValueError("Le minimum de PV doit être inférieur ou égal au maximum.")
    if hp is not None and (
        (hp_min is not None and hp < hp_min) or (hp_max is not None and hp > hp_max)
    ):
        raise ValueError("Les filtres de PV sont incompatibles.")


def search_cards(
    name: str = "",
    *,
    hp: int | None = None,
    hp_min: int | None = None,
    hp_max: int | None = None,
    card_type: str = "",
    illustrator: str = "",
    serie_id: str | None = None,
    set_id: str | None = None,
) -> list[Card]:
    """Combine all filters locally. Unknown metadata never matches a filter."""
    _validate_hp(hp, hp_min, hp_max)
    name, card_type, illustrator = map(normalize, (name, card_type, illustrator))
    matches: list[Card] = []
    language = _language_status.active
    for card_set in get_sets(serie_id):
        if set_id and card_set.id != set_id:
            continue
        for brief in card_set.cards:
            card = _details.get((language, brief.id), brief)
            if name not in normalize(card.name):
                continue
            if hp is not None and card.hp != hp:
                continue
            if hp_min is not None and (card.hp is None or card.hp < hp_min):
                continue
            if hp_max is not None and (card.hp is None or card.hp > hp_max):
                continue
            if card_type and not any(normalize(t) == card_type for t in card.types):
                continue
            if illustrator and illustrator not in normalize(card.illustrator):
                continue
            matches.append(card)
    return matches


def _cache_path(language: str, kind: str, key: str) -> Path:
    # Only digests become filenames, including language to separate translations.
    digest = sha256(f"{language}:{kind}:{key}".encode()).hexdigest()
    return user_data.path / "cache" / "tcg" / f"{digest}.json"


def _read_cache(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cast(dict[str, Any], data) if isinstance(data, dict) else None
    except OSError, ValueError:
        return None


def _write_cache(path: Path, data: dict[str, Any]) -> None:
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w", dir=path.parent, encoding="utf-8", delete=False
        ) as file:
            temporary = Path(file.name)
            json.dump(data, file, ensure_ascii=False)
        temporary.replace(path)
    except OSError:
        # An unwritable cache must not discard a successful network response.
        pass
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _query_cards(
    language: str, params: dict[str, str]
) -> tuple[list[dict[str, Any]], str, str]:
    path = _cache_path(language, "search", json.dumps(params, sort_keys=True))
    cached = _read_cache(path)
    cards = cached.get("cards") if cached else None
    valid = isinstance(cards, list) and all(
        isinstance(card, dict) and "id" in card and "name" in card for card in cards
    )
    cached_cards = cast(list[dict[str, Any]], cards) if valid else None
    fetched_at = cached.get("fetched_at", 0) if cached else 0
    if (
        cached_cards is not None
        and isinstance(fetched_at, (int, float))
        and time.time() - fetched_at < _SEARCH_CACHE_SECONDS
    ):
        return cached_cards, "cache", ""
    try:
        cards = tcgdex.search_cards(language, params)
    except tcgdex.TCGdexError:
        if cached_cards is not None:
            return (
                cached_cards,
                "cache",
                "TCGdex indisponible : derniers résultats en cache affichés.",
            )
        raise
    _write_cache(path, {"fetched_at": time.time(), "cards": cards})
    return cards, "online", ""


def search_cards_online(
    name: str = "",
    *,
    hp: int | None = None,
    hp_min: int | None = None,
    hp_max: int | None = None,
    card_type: str = "",
    illustrator: str = "",
    serie_id: str | None = None,
    set_id: str | None = None,
) -> SearchResult:
    """Use up to two filtered brief requests when local metadata is incomplete.

    Names and catalogue membership are always matched locally, preserving accent
    insensitive search and avoiding cards outside the installed series/sets.
    The second request intersects HP bounds, as repeated query keys are not a
    documented TCGdex range operation. No per-card requests are made here.
    """
    _validate_hp(hp, hp_min, hp_max)
    if hp is None and hp_min is not None and hp_min == hp_max:
        hp = hp_min
    candidates = search_cards(name=name, serie_id=serie_id, set_id=set_id)
    advanced = (
        hp is not None
        or hp_min is not None
        or hp_max is not None
        or bool(card_type.strip() or illustrator.strip())
    )
    if (
        not advanced
        or not candidates
        or all(card.details_loaded for card in candidates)
    ):
        return SearchResult(
            search_cards(
                name=name,
                hp=hp,
                hp_min=hp_min,
                hp_max=hp_max,
                card_type=card_type,
                illustrator=illustrator,
                serie_id=serie_id,
                set_id=set_id,
            )
        )
    language = _language_status.active
    params: dict[str, str] = {}
    if card_type.strip():
        params["types"] = next(
            (t for t in get_types() if normalize(t) == normalize(card_type)),
            card_type.strip(),
        )
    if illustrator.strip():
        params["illustrator"] = illustrator.strip()
    if set_id:
        params["set.id"] = f"eq:{set_id}"
    if hp is not None:
        params["hp"] = f"eq:{hp}"
    elif hp_min is not None:
        params["hp"] = f"gte:{hp_min}"
    elif hp_max is not None:
        params["hp"] = f"lte:{hp_max}"
    try:
        remote, source, warning = _query_cards(language, params)
        ids = {card["id"] for card in remote}
        if hp is None and hp_min is not None and hp_max is not None:
            upper, upper_source, upper_warning = _query_cards(
                language, {**params, "hp": f"lte:{hp_max}"}
            )
            ids.intersection_update(card["id"] for card in upper)
            if upper_source == "online":
                source = "online"
            warning = warning or upper_warning
    except tcgdex.TCGdexError as error:
        raise SearchUnavailableError(str(error)) from error
    return SearchResult(
        [card for card in candidates if card.id in ids], source, warning
    )


def fetch_card_details(card_id: str) -> Card:
    """Fetch a selected card once, with a persistent cache per language."""
    language = _language_status.active
    existing = get_card_by_id(card_id)
    if existing is not None and existing.details_loaded:
        return existing
    path = _cache_path(language, "card", card_id)
    cached = _read_cache(path)
    data = cached.get("card") if cached else None
    if not isinstance(data, dict) or data.get("id") != card_id or "name" not in data:
        data = tcgdex.fetch_card_by_id(language, card_id)
        if data.get("id") != card_id or "name" not in data:
            raise tcgdex.TCGdexError("TCGdex a renvoyé une carte invalide.")
        _write_cache(path, {"card": data})
    card = Card.from_dict({**data, "details_loaded": True})
    if existing is not None and not card.image:
        card.image = existing.image
    _details[(language, card_id)] = card
    return card


def get_cached_card_details() -> list[Card]:
    """Return detailed cards for the active language without accessing the network.

    Persistent card entries also populate the in-memory cache. Digest matching
    excludes other languages and search results; existing memory entries win.
    """
    language = _language_status.active
    cards = {
        card.id: card
        for (cached_language, _), card in _details.copy().items()
        if cached_language == language and card.details_loaded
    }
    try:
        paths = (user_data.path / "cache" / "tcg").glob("*.json")
        for path in paths:
            cached = _read_cache(path)
            data = cached.get("card") if cached else None
            if not isinstance(data, dict):
                continue
            data = cast(dict[str, object], data)
            card_id, name = data.get("id"), data.get("name")
            if not (
                isinstance(card_id, str)
                and card_id.strip()
                and isinstance(name, str)
                and name.strip()
            ):
                continue
            if path != _cache_path(language, "card", card_id) or card_id in cards:
                continue
            raw_types = data.get("types")
            if raw_types is not None and (
                not isinstance(raw_types, list)
                or any(
                    not isinstance(card_type, str)
                    for card_type in cast(list[object], raw_types)
                )
            ):
                continue
            if any(
                data.get(field) is not None and not isinstance(data[field], str)
                for field in ("image", "set_id", "illustrator", "rarity", "category")
            ):
                continue
            raw_set = data.get("set")
            if raw_set is not None:
                if not isinstance(raw_set, dict):
                    continue
                set_data = cast(dict[str, object], raw_set)
                if set_data.get("id") is not None and not isinstance(
                    set_data["id"], str
                ):
                    continue
            try:
                card = Card.from_dict({**data, "details_loaded": True})
            except KeyError, TypeError, ValueError, AttributeError:
                continue
            _details[(language, card_id)] = card
            cards[card_id] = card
    except OSError:
        # An absent or unreadable cache does not discard usable memory entries.
        pass
    return list(cards.values())


_ = set_language(user_data.get_tcg_lang())

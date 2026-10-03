"""Small synchronous TCGdex client; call from a worker in the UI.

Filtering: https://tcgdex.dev/rest/filtering-sorting-pagination
Card details: https://tcgdex.dev/rest/card
"""

from urllib.parse import quote
from typing import Any, cast

import requests


class TCGdexError(RuntimeError):
    """TCGdex could not return a usable response."""


def _fetch(
    language: str, endpoint: str, params: dict[str, str] | None = None
) -> dict[str, Any] | list[dict[str, Any]]:
    url = f"https://api.tcgdex.net/v2/{quote(language, safe='')}/{endpoint}"
    try:
        response = requests.get(url, params=params, timeout=(5, 15))
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as error:
        raise TCGdexError(
            "TCGdex est indisponible. Vérifiez votre connexion."
        ) from error
    if not isinstance(data, (dict, list)) or (
        isinstance(data, dict) and "error" in data
    ):
        raise TCGdexError("TCGdex a renvoyé une réponse invalide.")
    return cast(dict[str, Any] | list[dict[str, Any]], data)


def _object(language: str, endpoint: str) -> dict[str, Any]:
    result = _fetch(language, endpoint)
    if not isinstance(result, dict) or "id" not in result:
        raise TCGdexError("TCGdex a renvoyé une réponse invalide.")
    return result


def fetch_all_series(language: str) -> list[dict[str, Any]]:
    result = _fetch(language, "series")
    if not isinstance(result, list):
        raise TCGdexError("TCGdex a renvoyé une réponse invalide.")
    return result


def fetch_serie_by_id(language: str, serie_id: str) -> dict[str, Any]:
    return _object(language, f"series/{quote(serie_id, safe='')}")


def fetch_set_by_id(language: str, set_id: str) -> dict[str, Any]:
    return _object(language, f"sets/{quote(set_id, safe='')}")


def fetch_card_by_id(language: str, card_id: str) -> dict[str, Any]:
    return _object(language, f"cards/{quote(card_id, safe='')}")


def search_cards(
    language: str, params: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """Return filtered card briefs in a single call, without detail fan-out."""
    result = _fetch(language, "cards", params)
    if not isinstance(result, list) or any(
        not isinstance(card, dict) or "id" not in card or "name" not in card
        for card in result
    ):
        raise TCGdexError("TCGdex a renvoyé une liste de cartes invalide.")
    return result

import requests


def fetch_all_series(language: str) -> list[dict]:
    return requests.get(f"https://api.tcgdex.net/v2/{language}/series").json()


def fetch_serie_by_id(language: str, serie_id: str) -> dict:
    return requests.get(
        f"https://api.tcgdex.net/v2/{language}/series/{serie_id}"
    ).json()


def fetch_set_by_id(language: str, set_id: str) -> dict:
    return requests.get(f"https://api.tcgdex.net/v2/{language}/sets/{set_id}").json()

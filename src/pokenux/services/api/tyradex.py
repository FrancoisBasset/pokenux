import requests


def fetch_all_pokemon() -> list[dict]:
    return requests.get("https://tyradex.app/api/v1/pokemon").json()


def fetch_all_types() -> list[dict]:
    return requests.get("https://tyradex.app/api/v1/types").json()


def fetch_all_generations() -> list[dict]:
    return requests.get("https://tyradex.app/api/v1/gen").json()

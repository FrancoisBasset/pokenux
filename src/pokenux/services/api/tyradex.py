import requests


def fetch_all_pokemon() -> list[dict]:
    return requests.get("https://tyradex.app/api/v1/pokemon").json()

import requests


def fetch_all_pokemon() -> str:
    return requests.get("https://tyradex.app/api/v1/pokemon").json()

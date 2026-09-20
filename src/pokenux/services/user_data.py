import json
from pathlib import Path
from typing import Callable
from urllib.request import urlopen
from zipfile import ZipFile

import tomlkit
from tcgdexsdk import Serie

from pokenux.models.pokemon.pokemon import Pokemon


path: Path
config_path: Path
assets_path: Path
config_file: tomlkit.TOMLDocument


def init():
    global path, config_path, assets_path, config_file

    path = Path.home() / ".local" / "share" / "pokenux"
    assets_path = path / "assets"
    config_path = path / "config.toml"

    path.mkdir(parents=True, exist_ok=True)
    config_path.touch(exist_ok=True)

    with config_path.open("r") as file:
        config_file = tomlkit.load(file)


def assets_are_missing() -> bool:
    return (
        not assets_path.exists()
        or not any(assets_path.iterdir())
    )


def download_assets(cancelled: Callable[[], bool]) -> bool:
    url = (
        "https://github.com/FrancoisBasset/pokenux/releases/"
        "download/1.0.0/pokenux-data.zip"
    )

    zip_path = path / "pokemon-data.zip"

    try:
        with urlopen(url) as response:
            with zip_path.open("wb") as file:
                while chunk := response.read(1024 * 1024):
                    if cancelled():
                        return False

                    file.write(chunk)

        if cancelled():
            return False

        with ZipFile(zip_path, "r") as zip_file:
            for member in zip_file.infolist():
                if cancelled():
                    return False

                zip_file.extract(member, path)

        return True

    finally:
        zip_path.unlink(missing_ok=True)


def save_config():
    with config_path.open("w") as file:
        tomlkit.dump(config_file, file)


def get_all_pokemon() -> list[Pokemon]:
    with open(assets_path / "data" / "pokemon.json", "r") as file:
        return [Pokemon.from_dict(data) for data in json.load(file)]


def get_all_series(language: str) -> list[Serie]:
    with open(assets_path / "data" / f"tcg_{language}.json", "r") as file:
        return [Serie.from_dict(data) for data in json.load(file)]


def get_all_generations() -> list[str]:
    with open(assets_path / "data" / "generations.json", "r") as file:
        return json.load(file)


def get_all_types() -> list:
    with open(assets_path / "data" / "types.json", "r") as file:
        return json.load(file)


def get_app_lang() -> str:
    return config_file.get("app_lang", "en")


def get_pokemon_lang() -> str:
    return config_file.get("pokemon_lang", "en")


def get_tcg_lang() -> str:
    return config_file.get("tcg_lang", "en")


def set_app_lang(lang: str):
    config_file["app_lang"] = lang


def set_pokemon_lang(lang: str):
    config_file["pokemon_lang"] = lang


def set_tcg_lang(lang: str):
    config_file["tcg_lang"] = lang


init()

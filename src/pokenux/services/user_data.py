import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable

import tomlkit

from pokenux.models.pokemon.pokemon import Pokemon
from pokenux.models.tcg.serie import Serie
from pokenux.paths import data_directory


path: Path
config_path: Path
assets_path: Path
config_file: tomlkit.TOMLDocument


SUPPORTED_LANGUAGES = ("fr", "en")
DEFAULT_LANGUAGES = {"app_lang": "en", "pokemon_lang": "en", "tcg_lang": "en"}
config_load_error: str | None = None


def _validated_language(language: object) -> str:
    if not isinstance(language, str) or language not in SUPPORTED_LANGUAGES:
        raise ValueError("Language must be 'fr' or 'en'.")
    return language


def init():
    global path, config_path, assets_path, config_file, config_load_error

    path = data_directory()
    assets_path = path / "assets"
    config_path = path / "config.toml"
    path.mkdir(parents=True, exist_ok=True)
    config_load_error = None
    try:
        config_file = tomlkit.parse(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        config_file = tomlkit.document()
    except (OSError, UnicodeError, tomlkit.exceptions.ParseError) as error:
        # Leave a damaged file untouched until the user explicitly saves settings.
        config_file = tomlkit.document()
        config_load_error = str(error)
    for key, default in DEFAULT_LANGUAGES.items():
        if config_file.get(key) not in SUPPORTED_LANGUAGES:
            config_file[key] = default


def assets_are_missing() -> bool:
    from pokenux.services.assets import AssetManager

    return not AssetManager(path).status().installed


def download_assets(
    cancelled: Callable[[], bool],
    progress: Callable | None = None,
) -> bool:
    """Install a verified catalogue without exposing a partial download."""
    from pokenux.services.assets import AssetManager

    return AssetManager(path).bootstrap(
        cancelled=cancelled, progress=progress or (lambda _event: None)
    )


def _write_config(document: tomlkit.TOMLDocument) -> None:
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=config_path.parent,
            prefix=".config-",
            suffix=".toml",
            delete=False,
        ) as file:
            temporary = Path(file.name)
            file.write(tomlkit.dumps(document))
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, config_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_config() -> None:
    global config_load_error
    for key in DEFAULT_LANGUAGES:
        _validated_language(config_file.get(key))
    _write_config(config_file)
    config_load_error = None


def save_preferences(*, app_lang: str, pokemon_lang: str, tcg_lang: str) -> None:
    """Persist all three independent choices before changing in-memory settings."""
    global config_file, config_load_error
    values = {"app_lang": app_lang, "pokemon_lang": pokemon_lang, "tcg_lang": tcg_lang}
    for value in values.values():
        _validated_language(value)
    candidate = tomlkit.parse(tomlkit.dumps(config_file))
    candidate.update(values)
    _write_config(candidate)
    config_file = candidate
    config_load_error = None


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
    return str(config_file.get("app_lang", "en"))


def get_pokemon_lang() -> str:
    return str(config_file.get("pokemon_lang", "en"))


def get_tcg_lang() -> str:
    return str(config_file.get("tcg_lang", "en"))


def set_app_lang(lang: str):
    config_file["app_lang"] = _validated_language(lang)


def set_pokemon_lang(lang: str):
    config_file["pokemon_lang"] = _validated_language(lang)


def set_tcg_lang(lang: str):
    config_file["tcg_lang"] = _validated_language(lang)


init()

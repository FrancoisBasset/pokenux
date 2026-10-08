"""Command-line entry point; inspection commands never start the UI."""

import argparse
from collections.abc import Sequence
from contextlib import closing
import gettext
from importlib import import_module, metadata, resources
import platform
from typing import cast

from pokenux import __version__
from pokenux.paths import data_directory


_DEPENDENCIES = (
    ("requests", "requests"),
    ("rich", "rich.console"),
    ("textual", "textual.app"),
    ("textual-image", "textual_image"),
    ("Pillow", "PIL.Image"),
    ("tomlkit", "tomlkit"),
)
_CSS_FILES = (
    "style.css",
    "new_view.css",
    "pokedex_view.css",
    "tcg_view.css",
    "quiz_view.css",
    "simulator_view.css",
)


def check_installation() -> int:
    """Check code and packaged resources offline, without creating user data."""
    print(f"Pokénux {__version__}")
    print(
        f"Python {platform.python_version()} · {platform.system()} {platform.machine()}"
    )
    errors: list[str] = []
    for distribution, module in _DEPENDENCIES:
        try:
            _ = import_module(module)
            installed = metadata.version(distribution)
        except Exception as error:
            errors.append(f"{distribution}: {error}")
        else:
            print(f"OK   {distribution} {installed}")

    try:
        # SQLite is a Python runtime component, not a PyPI dependency.
        from sqlite3 import connect

        with closing(connect(":memory:")) as connection:
            _ = connection.execute("SELECT 1")
        print("OK   SQLite")
    except Exception as error:
        errors.append(f"SQLite: {error}")

    package = resources.files("pokenux")
    for filename in _CSS_FILES:
        stylesheet = package.joinpath("textual", "css", filename)
        try:
            if not stylesheet.read_text(encoding="utf-8").strip():
                raise ValueError("empty stylesheet")
        except (OSError, ValueError) as error:
            errors.append(f"CSS {filename}: {error}")
    for language in ("en", "fr"):
        translation = package.joinpath("locales", language, "LC_MESSAGES", "pokenux.mo")
        try:
            with translation.open("rb") as stream:
                _ = gettext.GNUTranslations(stream)
        except Exception as error:
            errors.append(f"Translation {language}: {error}")

    if not errors:
        print("OK   Packaged stylesheets and translations")
    location = data_directory()
    print(f"Data {location}")
    try:
        from pokenux.services.assets import AssetManager

        status = AssetManager(location).status()
    except OSError as error:
        # Catalogue availability does not determine whether installation works.
        print(f"INFO Local catalogue cannot be inspected: {error}")
    else:
        if not status.installed:
            print(
                "INFO Local catalogue absent; first launch downloads it (network required)."
            )
        else:
            print(
                f"OK   Local catalogue {status.version or 'legacy'} · "
                + " / ".join(language.upper() for language in status.languages)
            )
            if status.legacy:
                print("INFO Check Settings for versioned FR/EN catalogue updates.")
    for error in errors:
        print(f"FAIL {error}")
    print("Installation check failed." if errors else "Installation ready.")
    return 1 if errors else 0


class _Options(argparse.Namespace):
    check: bool = False


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pokenux",
        description="Explore Pokémon, play quizzes and collect cards in your terminal.",
        epilog="Run without arguments to open the app. First launch downloads the catalogue.",
    )
    _ = parser.add_argument(
        "--version", action="version", version=f"Pokénux {__version__}"
    )
    _ = parser.add_argument(
        "--check",
        action="store_true",
        help="check the installation offline without opening the app or changing user data",
    )
    options = parser.parse_args(argv, namespace=_Options())
    if options.check:
        return check_installation()

    # Probe graphics support before Textual starts reading terminal responses.
    # User data and asset-backed views stay unloaded for --help/--version/--check.
    _ = import_module("textual_image.widget")
    from pokenux.textual.pokenux import Pokenux

    _ = cast(object, Pokenux().run())
    return 0

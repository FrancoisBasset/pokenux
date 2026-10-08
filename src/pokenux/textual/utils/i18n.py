"""Interface language, with gettext compatibility for existing message keys."""

import gettext
from pathlib import Path

from pokenux.services import localization, user_data
from pokenux.services.localization import text as text

_translation: gettext.NullTranslations = gettext.NullTranslations()


def set_language(language: str) -> None:
    global _translation
    localization.set_language(language)
    locales_path = Path(__file__).resolve().parent.parent.parent / "locales"
    _translation = gettext.translation(
        "pokenux", localedir=locales_path, languages=[language], fallback=True
    )


def get_language() -> str:
    return localization.language()


def trans(message: str) -> str:
    # Preserve the existing gettext API while using consistent navigation names.
    if message == "parameters":
        return text("Paramètres", "Settings")
    return _translation.gettext(message)


set_language(user_data.get_app_lang())

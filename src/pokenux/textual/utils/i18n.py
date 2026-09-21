import gettext
from pathlib import Path

from pokenux.services import user_data


def set_language(language: str):
    global trans

    localesPath = Path(__file__).resolve().parent.parent.parent / "locales"

    trans = gettext.translation(
        "pokenux", localedir=localesPath, languages=[language]
    ).gettext


set_language(user_data.get_app_lang())

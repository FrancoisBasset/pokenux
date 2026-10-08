"""Small FR/EN message helper shared by services and the terminal interface."""

_language = "en"


def set_language(value: str) -> None:
    global _language
    if value not in ("fr", "en"):
        raise ValueError("Language must be 'fr' or 'en'.")
    _language = value


def language() -> str:
    return _language


def text(fr: str, en: str, **values: object) -> str:
    template = fr if _language == "fr" else en
    return template.format(**values) if values else template

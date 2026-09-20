from textual.binding import Binding

from pokenux.services import user_data
from pokenux.textual.utils import i18n


def get_main_bindings() -> list[Binding]:
    i18n.set_language(user_data.get_app_lang())

    return [
        Binding("q", "quit", i18n.trans("quit")),
        Binding("p", "show_parameters", i18n.trans("parameters")),
    ]

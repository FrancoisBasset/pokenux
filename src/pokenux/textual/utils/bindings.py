from textual.binding import Binding

from pokenux.textual.utils import i18n


def get_main_bindings() -> list[Binding]:
    return [
        Binding("q", "quit", i18n.trans("quit")),
        Binding("p", "show_parameters", i18n.trans("parameters")),
    ]

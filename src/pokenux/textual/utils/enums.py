from pokenux.services import user_data
from pokenux.textual.utils import i18n

i18n.set_language(user_data.get_app_lang())

languages: list = [("Français", "fr"), ("English", "en")]


def sort_by():
    return [
        (i18n.trans("by_number"), "by_number"),
        (i18n.trans("by_generation"), "by_generation"),
        (i18n.trans("by_type"), "by_type"),
        (i18n.trans("by_evolution"), "by_evolution"),
    ]


def evolutions():
    return [
        (i18n.trans("base"), "base"),
        (i18n.trans("stage_1"), "stage_1"),
        (i18n.trans("stage_2"), "stage_2"),
        (i18n.trans("no_evolution"), "no_evolution"),
    ]

from dataclasses import replace
import inspect
import sys
from typing import cast

from textual.app import App
from textual.widget import Widget
from pokenux.services import user_data
from textual.widgets import Button, Input, Label, Select, TabPane, TabbedContent

from pokenux.textual.utils import enums, i18n
from pokenux.textual.utils.bindings import get_main_bindings
from textual.css.query import NoMatches


def refresh_bindings(
    widget: Widget | App[None], descriptions: dict[str, tuple[str, str]]
) -> None:
    """Refresh an instance's binding labels without changing its shortcuts."""
    for key, bindings in widget._bindings.key_to_bindings.items():
        updated = []
        for binding in bindings:
            pair = descriptions.get(binding.action, descriptions.get(key))
            updated.append(
                replace(binding, description=i18n.text(*pair))
                if pair is not None
                else binding
            )
        widget._bindings.key_to_bindings[key] = updated
    if isinstance(widget, App):
        widget.refresh_bindings()
    elif widget.is_attached:
        widget.app.refresh_bindings()


async def translate_app(app: App[None]):
    """Refresh mounted views in place, preserving their ongoing activities."""
    for binding in get_main_bindings():
        app._bindings.key_to_bindings[binding.key] = [binding]
    # Refresh the shared catalogue once before the views redraw their labels.
    tcg = sys.modules.get("pokenux.services.tcg_library")
    if (
        tcg is not None
        and tcg.get_language_status().requested != user_data.get_tcg_lang()
    ):
        tcg.set_language(user_data.get_tcg_lang())
    translate_inputs(app)
    translate_buttons(app)
    translate_panes(app)
    translate_labels(app)
    translate_selects(app)
    for widget in (app, *list(app.query("*"))):
        if isinstance(widget, Widget) and not widget.is_attached:
            continue
        refresh = getattr(widget, "refresh_language", None)
        if callable(refresh):
            result = refresh()
            if inspect.isawaitable(result):
                await result
    app.refresh_bindings()


def translate_selects(app: App[None]):
    for widget in app.query("Select.i18n"):
        select = cast(Select[str], widget)
        if select.name:
            selected = select.value
            select.prompt = i18n.trans(select.name)
            select.set_options(getattr(enums, select.name)())
            select.value = selected


def translate_inputs(app: App[None]):
    for widget in app.query("Input.i18n"):
        input_widget = cast(Input, widget)
        if input_widget.name:
            input_widget.placeholder = i18n.trans(input_widget.name)


def translate_labels(app: App[None]):
    for widget in app.query("Label.i18n"):
        label = cast(Label, widget)
        if label.name:
            label.update(i18n.trans(label.name))


def translate_buttons(app: App[None]):
    for widget in app.query("Button.i18n"):
        button = cast(Button, widget)
        if button.name:
            button.label = i18n.trans(button.name)


def translate_panes(app: App[None]):
    for widget in app.query("TabPane.i18n"):
        tab_pane = cast(TabPane, widget)
        if tab_pane.name:
            try:
                tabbed_content = cast(
                    TabbedContent,
                    tab_pane.query_ancestor("TabbedContent", TabbedContent),
                )
                tab = tabbed_content.get_tab(tab_pane)
            except NoMatches:
                tab_pane._title = tab_pane.render_str(tab_pane_title(tab_pane))
                continue

            title = tab_pane_title(
                tab_pane,
                closable=tab.label_text.rstrip().endswith("×"),
            )
            tab_pane._title = tab_pane.render_str(title)
            tab.label = title


def tab_pane_title(tab_pane: TabPane, closable: bool = False) -> str:
    if tab_pane.name is None:
        return ""

    titles = {
        "home": ("⌂ Accueil", "⌂ Home"),
        "pokedex": ("Pokédex", "Pokédex"),
        "tcg": ("Cartes TCG", "TCG cards"),
        "quiz": ("Quiz", "Quiz"),
        "simulator": ("Boosters", "Boosters"),
        "parameters": ("Paramètres", "Settings"),
    }
    title = (
        i18n.text(*titles[tab_pane.name])
        if tab_pane.name in titles
        else i18n.trans(tab_pane.name)
    )
    if closable and tab_pane.id:
        title += f" [bold @click=app.close_tab('{tab_pane.id}')]×[/]"

    return title

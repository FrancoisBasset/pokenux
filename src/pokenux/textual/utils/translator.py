from typing import cast

from textual.app import App
from textual.widgets import TabPane, TabbedContent

from pokenux.textual.utils import enums, i18n
from pokenux.textual.utils.bindings import get_main_bindings
from textual.css.query import NoMatches


def translate_app(app: App):
    bindings = get_main_bindings()

    for binding in bindings:
        app._bindings.key_to_bindings[binding.key] = [binding]

    app.refresh_bindings()

    translate_inputs(app)
    translate_buttons(app)
    translate_panes(app)
    translate_labels(app)
    translate_selects(app)


def translate_selects(app: App):
    for select in app.query("Select.i18n"):
        if select.name:
            select.prompt = i18n.trans(select.name)
            select.set_options(getattr(enums, select.name)())


def translate_inputs(app: App):
    for input_widget in app.query("Input.i18n"):
        if input_widget.name:
            input_widget.placeholder = i18n.trans(input_widget.name)


def translate_labels(app: App):
    for label in app.query("Label.i18n"):
        if label.name:
            label.update(i18n.trans(label.name))


def translate_buttons(app: App):
    for button in app.query("Button.i18n"):
        if button.name:
            button.label = i18n.trans(button.name)


def translate_panes(app: App):
    for tab_pane in app.query("TabPane.i18n"):
        if tab_pane.name:
            try:
                tabbed_content = cast(
                    TabbedContent,
                    tab_pane.query_ancestor(TabbedContent, TabbedContent),
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

    title = i18n.trans(tab_pane.name)
    if closable and tab_pane.id:
        title += f" [bold @click=app.close_tab('{tab_pane.id}')]×[/]"

    return title

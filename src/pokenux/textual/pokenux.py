from textual.app import App, ComposeResult
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Footer, Header, TabPane, TabbedContent

from pokenux.services import user_data
from pokenux.textual.utils import bindings, i18n
from pokenux.textual.screens.fetching_screen import FetchingScreen
from pokenux.textual.views.parameters_view import ParametersView


class Pokenux(App):
    TITLE = "Pokénux"
    BINDINGS = bindings.get_main_bindings()
    CSS_PATH = [
        "css/style.css",
        "css/new_view.css",
        "css/pokedex_view.css",
        "css/tcg_view.css",
        "css/quiz_view.css",
        "css/simulator_view.css",
    ]

    def on_mount(self):
        self.tabbed_content: TabbedContent = self.query_one("#tabbed_content")
        self.panes: list[TabPane] = []

        if user_data.assets_are_missing():
            self.push_screen(FetchingScreen(), callback=self.on_fetching_finished)
        else:
            self.load_new_view()

    def compose(self) -> ComposeResult:
        yield Header(name="Pokenux", icon="◒")

        with TabbedContent(id="tabbed_content"):
            yield TabPane("⌂ Accueil", id="new_tab_tab")

        yield Footer()

    async def on_fetching_finished(self, finished: bool | None) -> None:
        if not finished:
            self.exit()
            return

        self.load_new_view()

    def load_new_view(self) -> None:
        # These views import catalogues that must only load after asset setup.
        from pokenux.textual.views.new_view import NewView

        self.query_one("#new_tab_tab", TabPane).mount(NewView(self.tabbed_content))

    def action_close_tab(self, tab_id: str) -> None:
        if tab_id == "new_tab_tab" or not self.tabbed_content.is_attached:
            return
        try:
            tab = self.tabbed_content.get_tab(tab_id)
        except NoMatches:
            return
        tab.call_later(self._finish_tab_click, tab, tab_id)

    def _finish_tab_click(self, widget: Widget, tab_id: str) -> None:
        if not widget.is_attached:
            return
        # Follow the queues through which Tab.Clicked bubbles. Also let each
        # ancestor process any activation messages it adds before closing.
        if widget is self.tabbed_content:
            widget.call_later(self._close_tab, tab_id)
        elif isinstance(widget.parent, Widget):
            widget.call_later(
                widget.parent.call_later,
                self._finish_tab_click,
                widget.parent,
                tab_id,
            )

    async def _close_tab(self, tab_id: str) -> None:
        if tab_id == "new_tab_tab" or not self.tabbed_content.is_attached:
            return
        try:
            pane = self.tabbed_content.get_pane(tab_id)
        except NoMatches:
            return
        if not pane.is_attached or pane.parent is None:
            return
        if self.tabbed_content.active == tab_id:
            self.set_focus(None)
            remaining = [
                sibling
                for sibling in pane.parent.children
                if isinstance(sibling, TabPane) and sibling is not pane
            ]
            self.tabbed_content.active = remaining[-1].id or "new_tab_tab"
        await self.tabbed_content.remove_pane(tab_id)

    async def action_show_parameters(self) -> None:
        try:
            self.tabbed_content.get_pane("parameters")
        except NoMatches:
            parameter_view = TabPane(
                i18n.trans("parameters")
                + " [bold @click=app.close_tab('parameters')]×[/]",
                ParametersView(),
                id="parameters",
                name="parameters",
                classes="i18n",
            )
            await self.tabbed_content.add_pane(parameter_view, before="new_tab_tab")

        self.tabbed_content.active = "parameters"

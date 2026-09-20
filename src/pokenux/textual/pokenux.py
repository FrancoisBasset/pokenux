from textual.app import App, ComposeResult
from textual.css.query import NoMatches
from textual.widgets import Footer, Header, TabPane, TabbedContent

from pokenux.services import user_data
from pokenux.textual.utils import bindings, i18n
from pokenux.textual.screens.fetching_screen import FetchingScreen
from pokenux.textual.views.new_view import NewView
from pokenux.textual.views.parameters_view import ParametersView


class Pokenux(App):
    BINDINGS = bindings.get_main_bindings()
    CSS_PATH = ["css/style.css", "css/pokedex_view.css"]

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
            yield TabPane("+", id="new_tab_tab")

        yield Footer()

    async def on_fetching_finished(self, finished: bool | None) -> None:
        if not finished:
            self.exit()
            return

        self.load_new_view()

    def load_new_view(self) -> None:
        self.query_one("#new_tab_tab", TabPane).mount(NewView(self.tabbed_content))

    def action_close_tab(self, tab_id: str) -> None:
        self.tabbed_content.remove_pane(tab_id)

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

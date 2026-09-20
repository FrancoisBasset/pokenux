from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, TabPane, TabbedContent

from pokenux.textual.views.pokedex_view import PokedexView
from pokenux.textual.views.quiz_view import QuizView
from pokenux.textual.views.simulator_view import SimulatorView
from pokenux.textual.views.tcg_view import TcgView


class NewView(Horizontal):
    def __init__(self, tabbed_content: TabbedContent):
        self.tabbed_content: TabbedContent = tabbed_content
        super().__init__(id="new_view")

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Button("Pokédex", id="pokedex_button")
            yield Button("TCG", id="tcg_button")
            yield Button("Quiz", id="quiz_button")
            yield Button("Simulator", id="simulator_button")

    @on(Button.Pressed, "#pokedex_button")
    async def on_pokedex_button_pressed(self):
        await self.open_new_tab("Pokédex", PokedexView)

    @on(Button.Pressed, "#tcg_button")
    async def on_tcg_button_pressed(self):
        await self.open_new_tab("TCG", TcgView)

    @on(Button.Pressed, "#quiz_button")
    async def on_quiz_button_pressed(self):
        await self.open_new_tab("Quiz", QuizView)

    @on(Button.Pressed, "#simulator_button")
    async def on_simulator_button_pressed(self):
        await self.open_new_tab("Simulator", SimulatorView)

    async def open_new_tab(self, label: str, tab_class: type):
        tab_id: str = "tab" + str(self.tabbed_content.tab_count)
        new_pane = TabPane(
            f"{label} [bold @click=app.close_tab({tab_id!r})]×[/]",
            tab_class(),
            id=tab_id,
        )
        await self.tabbed_content.add_pane(new_pane, before="new_tab_tab")
        self.app.set_focus(None)
        self.tabbed_content.active = tab_id

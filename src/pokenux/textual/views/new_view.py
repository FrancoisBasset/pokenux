from itertools import count
from typing import ClassVar, cast, override

from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, Label, TabPane, TabbedContent

from pokenux.textual.views.pokedex_view import PokedexView
from pokenux.textual.views.quiz_view import QuizView
from pokenux.textual.views.simulator_view import SimulatorView
from pokenux.textual.views.tcg_view import TcgView


class NewView(VerticalScroll):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("1", "open_section('pokedex_button')", "Pokédex", show=False),
        Binding("2", "open_section('tcg_button')", "Cartes TCG", show=False),
        Binding("3", "open_section('quiz_button')", "Quiz", show=False),
        Binding("4", "open_section('simulator_button')", "Boosters", show=False),
    ]

    def __init__(self, tabbed_content: TabbedContent) -> None:
        self.tabbed_content: TabbedContent = tabbed_content
        self._tab_ids: count[int] = count(1)
        super().__init__(id="new_view")

    @override
    def compose(self) -> ComposeResult:
        with Vertical(id="menu_content"):
            with Horizontal(id="menu_hero"):
                with Vertical(id="menu_intro"):
                    yield Label("LE COIN DES DRESSEURS", id="menu_eyebrow")
                    yield Label("P O K É N U X", id="menu_title")
                    yield Label(
                        "À chaque envie, une nouvelle aventure.", id="menu_subtitle"
                    )
                yield Label(
                    "[bold #f28c91]    ▄██████▄\n  ▄██████████▄[/]\n"
                    + "[#f1d6af] ━━━━━[bold] ◉ [/bold]━━━━━[/]\n"
                    + "[#a8bacf]  ▀██████████▀\n    ▀██████▀[/]",
                    id="menu_emblem",
                )
            yield Label("CHOISIS TON ACTIVITÉ", id="menu_section")
            with Grid(id="menu_grid"):
                yield Button(
                    "[bold #83b7ff]01   POKÉDEX[/]\n"
                    + "Rencontre tous les Pokémon.\n"
                    + "[#99aabd]Fiches, types et évolutions.[/]\n"
                    + "[bold #83b7ff]Explorer  →[/]",
                    id="pokedex_button",
                    classes="menu-card",
                )
                yield Button(
                    "[bold #79d7be]02   CARTES TCG[/]\n"
                    + "Trouve ta prochaine carte.\n"
                    + "[#99aabd]Séries, extensions et artistes.[/]\n"
                    + "[bold #79d7be]Parcourir les cartes  →[/]",
                    id="tcg_button",
                    classes="menu-card",
                )
                yield Button(
                    "[bold #c9a1f4]03   QUIZ[/]\n"
                    + "À toi de jouer, Dresseur.\n"
                    + "[#99aabd]Devinettes, images et défis.[/]\n"
                    + "[bold #c9a1f4]Relever un défi  →[/]",
                    id="quiz_button",
                    classes="menu-card",
                )
                yield Button(
                    "[bold #efc47d]04   BOOSTERS[/]\n"
                    + "La prochaine pépite t’attend.\n"
                    + "[#99aabd]Ouvre, collectionne et revends.[/]\n"
                    + "[bold #efc47d]Ouvrir la boutique  →[/]",
                    id="simulator_button",
                    classes="menu-card",
                )
            yield Label(
                "[bold #d5dfec]1–4[/] · accès direct    [bold #d5dfec]Tab[/] · naviguer    "
                + "[bold #d5dfec]Entrée[/] · ouvrir",
                id="menu_shortcuts",
            )
            yield Label(
                "Chaque activité s’ouvre dans son propre onglet.", id="menu_hint"
            )

    def on_resize(self, event: events.Resize) -> None:
        _ = self.set_class(event.size.width < 70, "narrow")
        _ = self.set_class(event.size.height < 32, "compact")

    def on_mount(self) -> None:
        self.watch(self.tabbed_content, "active", self._active_tab_changed, init=False)
        _ = self.query_one("#pokedex_button", Button).focus()

    def _active_tab_changed(self, active: str) -> None:
        if active == "new_tab_tab":
            _ = self.call_after_refresh(self._focus_menu)

    def _focus_menu(self) -> None:
        if self.is_attached and self.tabbed_content.active == "new_tab_tab":
            _ = self.query_one("#pokedex_button", Button).focus()

    def action_open_section(self, button_id: str) -> None:
        _ = self.query_one(f"#{button_id}", Button).press()

    @on(Button.Pressed, "#pokedex_button")
    async def on_pokedex_button_pressed(self) -> None:
        await self.open_new_tab("Pokédex", PokedexView)

    @on(Button.Pressed, "#tcg_button")
    async def on_tcg_button_pressed(self) -> None:
        await self.open_new_tab("TCG", TcgView)

    @on(Button.Pressed, "#quiz_button")
    async def on_quiz_button_pressed(self) -> None:
        await self.open_new_tab("Quiz", QuizView)

    @on(Button.Pressed, "#simulator_button")
    async def on_simulator_button_pressed(self) -> None:
        await self.open_new_tab("Boosters", SimulatorView)

    async def open_new_tab(self, label: str, tab_class: type[Widget]) -> None:
        tab_id = f"tab{next(self._tab_ids)}"
        new_pane = TabPane(
            f"{label} [bold @click=app.close_tab({tab_id!r})]×[/]",
            tab_class(),
            id=tab_id,
        )
        await self.tabbed_content.add_pane(new_pane, before="new_tab_tab")
        cast(App[None], self.app).set_focus(None)
        self.tabbed_content.active = tab_id

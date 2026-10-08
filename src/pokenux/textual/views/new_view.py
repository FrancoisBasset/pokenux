from itertools import count
from typing import ClassVar, cast, override

from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, Label, TabPane, TabbedContent

from pokenux.textual.utils import i18n
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

    @staticmethod
    def _labels() -> dict[str, str]:
        text = i18n.text
        return {
            "menu_eyebrow": text("LE COIN DES DRESSEURS", "THE TRAINER'S CORNER"),
            "menu_title": "P O K É N U X",
            "menu_subtitle": text(
                "À chaque envie, une nouvelle aventure.",
                "A new adventure for every mood.",
            ),
            "menu_section": text("CHOISIS TON ACTIVITÉ", "CHOOSE YOUR ADVENTURE"),
            "menu_shortcuts": text(
                "[bold #d5dfec]1–4[/] · accès direct    [bold #d5dfec]Tab[/] · naviguer    [bold #d5dfec]Entrée[/] · ouvrir",
                "[bold #d5dfec]1–4[/] · jump in    [bold #d5dfec]Tab[/] · navigate    [bold #d5dfec]Enter[/] · open",
            ),
            "menu_hint": text(
                "Chaque activité s’ouvre dans son propre onglet.",
                "Each activity opens in its own tab.",
            ),
        }

    @staticmethod
    def _cards() -> dict[str, str]:
        text = i18n.text
        return {
            "pokedex_button": "[bold #83b7ff]01   POKÉDEX[/]\n"
            + text("Rencontre tous les Pokémon.", "Meet every Pokémon.")
            + "\n[#99aabd]"
            + text("Fiches, types et évolutions.", "Profiles, types and evolutions.")
            + "[/]\n[bold #83b7ff]"
            + text("Explorer", "Explore")
            + "  →[/]",
            "tcg_button": "[bold #79d7be]02   "
            + text("CARTES TCG", "TCG CARDS")
            + "[/]\n"
            + text("Trouve ta prochaine carte.", "Find your next favourite card.")
            + "\n[#99aabd]"
            + text("Séries, extensions et artistes.", "Series, sets and artists.")
            + "[/]\n[bold #79d7be]"
            + text("Parcourir les cartes", "Browse cards")
            + "  →[/]",
            "quiz_button": "[bold #c9a1f4]03   QUIZ[/]\n"
            + text("À toi de jouer, Dresseur.", "Your turn, Trainer.")
            + "\n[#99aabd]"
            + text("Devinettes, images et défis.", "Riddles, pictures and challenges.")
            + "[/]\n[bold #c9a1f4]"
            + text("Relever un défi", "Take a challenge")
            + "  →[/]",
            "simulator_button": "[bold #efc47d]04   BOOSTERS[/]\n"
            + text("La prochaine pépite t’attend.", "Your next great pull awaits.")
            + "\n[#99aabd]"
            + text("Ouvre, collectionne et revends.", "Open, collect and trade.")
            + "[/]\n[bold #efc47d]"
            + text("Ouvrir la boutique", "Visit the shop")
            + "  →[/]",
        }

    @override
    def compose(self) -> ComposeResult:
        labels = self._labels()
        with Vertical(id="menu_content"):
            with Horizontal(id="menu_hero"):
                with Vertical(id="menu_intro"):
                    for key in ("menu_eyebrow", "menu_title", "menu_subtitle"):
                        yield Label(labels[key], id=key)
                yield Label(
                    "[bold #f28c91]    ▄██████▄\n  ▄██████████▄[/]\n"
                    + "[#f1d6af] ━━━━━[bold] ◉ [/bold]━━━━━[/]\n"
                    + "[#a8bacf]  ▀██████████▀\n    ▀██████▀[/]",
                    id="menu_emblem",
                )
            yield Label(labels["menu_section"], id="menu_section")
            with Grid(id="menu_grid"):
                for key, label in self._cards().items():
                    yield Button(label, id=key, classes="menu-card")
            yield Label(labels["menu_shortcuts"], id="menu_shortcuts")
            yield Label(labels["menu_hint"], id="menu_hint")

    def refresh_language(self) -> None:
        for key, label in self._labels().items():
            self.query_one(f"#{key}", Label).update(label)
        for key, label in self._cards().items():
            self.query_one(f"#{key}", Button).label = label

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
        await self.open_new_tab(i18n.text("Cartes TCG", "TCG cards"), TcgView)

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
            name={
                PokedexView: "pokedex",
                TcgView: "tcg",
                QuizView: "quiz",
                SimulatorView: "simulator",
            }.get(tab_class),
            classes="i18n",
        )
        await self.tabbed_content.add_pane(new_pane, before="new_tab_tab")
        cast(App[None], self.app).set_focus(None)
        self.tabbed_content.active = tab_id

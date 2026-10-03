from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Grid, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Checkbox, Input, Label, Select

from pokenux.services import pokedex, user_data
from pokenux.textual.utils import enums, i18n
from pokenux.textual.widgets.pokemon_details import PokemonDetails
from pokenux.textual.widgets.pokemon_list import (
    PokemonList,
    PokemonTableHeader,
    generation_label,
)


class PokedexView(Vertical):
    BINDINGS = [
        Binding("/", "focus_search", "Recherche"),
        Binding("f", "toggle_filters", "Filtres"),
        Binding("s", "focus_sort", "Trier"),
        Binding("t", "show_tcg", "TCG"),
        Binding("r", "reset_filters", "Reset"),
        Binding("escape", "focus_pokemon", "Retour"),
    ]

    def __init__(self):
        super().__init__()
        self.active_generations: list[str] = []
        self.active_types: list[str] = []
        self.active_evolutions: list[str] = []
        self.pokemon_list = pokedex.filter_pokemon([], [], [])
        self.type_names = {t["en"]: t["fr"] for t in user_data.get_all_types()}
        self._ready = False
        self._filter_state: (
            tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], str, str, bool]
            | None
        ) = None
        self._filters_expanded = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="pokedex_toolbar"):
            yield Input(
                placeholder=i18n.trans("search_pokemon"),
                id="pokemon_input",
                name="search_pokemon",
                classes="i18n",
            )
            yield Label("Trier", classes="toolbar-label")
            yield Select(
                options=enums.sort_by()
                + [("Nom", "by_name"), ("Taille", "by_height"), ("Poids", "by_weight")],
                value="by_number",
                allow_blank=False,
                id="pokemon_sort",
            )
            yield Select(
                options=[("Croissant ↑", False), ("Décroissant ↓", True)],
                value=False,
                allow_blank=False,
                id="pokemon_sort_direction",
            )

        with Horizontal(id="pokedex_content"):
            with VerticalScroll(id="pokemon_filters"):
                yield Label("FILTRES", id="filters_title")
                with Container(classes="filters_container"):
                    yield Label("Génération")
                    with Grid(id="generations_grid"):
                        for generation in user_data.get_all_generations():
                            yield Checkbox(
                                generation_label(int(generation)),
                                id=f"generation_{generation}",
                            )
                with Container(classes="filters_container"):
                    yield Label("Type")
                    with Grid(id="types_grid"):
                        for code, name in self.type_names.items():
                            yield Checkbox(name, id=f"type_{code}")
                with Container(classes="filters_container"):
                    yield Label("Évolution")
                    with Grid(id="evolutions_grid"):
                        for label, code in enums.evolutions():
                            yield Checkbox(label, id=f"evolution_{code}")

            with Vertical(id="pokemon_table_panel"):
                with Horizontal(id="pokemon_list_header"):
                    yield Label(f"{len(self.pokemon_list)} Pokémon", id="pokemon_count")
                    yield Horizontal(id="pokemon_filter_chips")
                    yield Button("↻ Réinitialiser", id="pokemon_reset")
                yield PokemonTableHeader(id="pokemon_table_header")
                yield PokemonList(self.pokemon_list)

            yield PokemonDetails()

    async def on_mount(self) -> None:
        self._ready = True
        await self.load_data()
        self.call_after_refresh(self.focus_table_on_show)

    def on_show(self) -> None:
        if self._ready:
            self.call_after_refresh(self.focus_table_on_show)

    def focus_table_on_show(self) -> None:
        if self.is_mounted and self.region.height > 0:
            if self.query_one("#pokemon_table_panel").display:
                self.query_one(PokemonList).focus()
            elif self.query_one(PokemonDetails).display:
                self.query_one(PokemonDetails).focus_details()
            else:
                self.query_one("#generations_grid Checkbox", Checkbox).focus()

    def on_resize(self, event: events.Resize) -> None:
        self.set_class(event.size.width < 175, "compact")
        self.set_class(event.size.width < 112, "narrow")
        if event.size.width >= 175:
            self.remove_class("filters-expanded")
            self._filters_expanded = False

    async def load_data(self) -> None:
        if not self._ready:
            return
        self.active_generations = [
            checkbox.id.removeprefix("generation_")
            for checkbox in self.query_one("#generations_grid", Grid).query(Checkbox)
            if checkbox.value and checkbox.id
        ]
        self.active_types = [
            self.type_names[checkbox.id.removeprefix("type_")]
            for checkbox in self.query_one("#types_grid", Grid).query(Checkbox)
            if checkbox.value and checkbox.id
        ]
        self.active_evolutions = [
            checkbox.id.removeprefix("evolution_")
            for checkbox in self.query_one("#evolutions_grid", Grid).query(Checkbox)
            if checkbox.value and checkbox.id
        ]
        search = self.query_one("#pokemon_input", Input).value
        sort_by = str(self.query_one("#pokemon_sort", Select).value)
        descending = self.query_one("#pokemon_sort_direction", Select).value is True
        state = (
            tuple(self.active_generations),
            tuple(self.active_types),
            tuple(self.active_evolutions),
            search,
            sort_by,
            descending,
        )
        if state == self._filter_state:
            return
        self._filter_state = state
        self.pokemon_list = pokedex.filter_pokemon(
            self.active_generations,
            self.active_types,
            self.active_evolutions,
            search=search,
            sort_by=sort_by,
            descending=descending,
            language="fr",
        )
        self.query_one("#pokemon_count", Label).update(
            f"{len(self.pokemon_list)} Pokémon"
        )
        await self.update_filter_chips()
        await self.query_one(PokemonList).set_pokemon(self.pokemon_list)

    async def update_filter_chips(self) -> None:
        chips = self.query_one("#pokemon_filter_chips", Horizontal)
        await chips.remove_children()
        filters = [
            (generation_label(int(code)), f"generation_{code}", "filter-generation")
            for code in self.active_generations
        ]
        filters += [
            (name, f"type_{code}", "filter-type")
            for code, name in self.type_names.items()
            if name in self.active_types
        ]
        labels = dict((code, label) for label, code in enums.evolutions())
        filters += [
            (labels[code], f"evolution_{code}", "filter-evolution")
            for code in self.active_evolutions
        ]
        if filters:
            await chips.mount(
                *(
                    Label(f"{label} ×", name=widget_id, classes=f"filter {style}")
                    for label, widget_id, style in filters
                )
            )

    @on(Checkbox.Changed)
    @on(Input.Changed, "#pokemon_input")
    @on(Select.Changed)
    async def filters_changed(self) -> None:
        await self.load_data()

    @on(events.Click, ".filter")
    def remove_filter(self, event: events.Click) -> None:
        if event.widget and event.widget.name:
            self.query_one(f"#{event.widget.name}", Checkbox).value = False
        event.stop()

    @on(Button.Pressed, "#pokemon_reset")
    async def reset_pressed(self) -> None:
        await self.action_reset_filters()

    async def action_reset_filters(self) -> None:
        for checkbox in self.query(Checkbox):
            with checkbox.prevent(Checkbox.Changed):
                checkbox.value = False
        search = self.query_one("#pokemon_input", Input)
        with search.prevent(Input.Changed):
            search.value = ""
        sort = self.query_one("#pokemon_sort", Select)
        with sort.prevent(Select.Changed):
            sort.value = "by_number"
        direction = self.query_one("#pokemon_sort_direction", Select)
        with direction.prevent(Select.Changed):
            direction.value = False
        await self.load_data()

    @on(PokemonList.Selected)
    def pokemon_selected(self, message: PokemonList.Selected) -> None:
        self.query_one(PokemonDetails).set_pokemon(message.pokemon)
        if message.activated and message.pokemon:
            self.remove_class("filters-expanded")
            self.add_class("details-open")
            self.query_one(PokemonDetails).focus_details()
        message.stop()

    def action_focus_search(self) -> None:
        self.query_one(PokemonDetails).cancel_pending_focus()
        self.query_one("#pokemon_input", Input).focus()

    def action_focus_sort(self) -> None:
        self.query_one(PokemonDetails).cancel_pending_focus()
        self.query_one("#pokemon_sort", Select).focus()

    def action_toggle_filters(self) -> None:
        self.query_one(PokemonDetails).cancel_pending_focus()
        if self.has_class("compact"):
            self._filters_expanded = not self.has_class("filters-expanded")
            self.set_class(self._filters_expanded, "filters-expanded")
            self.remove_class("details-open")
        if not self.has_class("compact") or self._filters_expanded:
            self.query_one("#generations_grid Checkbox", Checkbox).focus()
        else:
            self.query_one(PokemonList).focus()

    def action_show_tcg(self) -> None:
        self.remove_class("filters-expanded")
        self.add_class("details-open")
        self.query_one(PokemonDetails).show_tcg()

    def action_focus_pokemon(self) -> None:
        self.query_one(PokemonDetails).cancel_pending_focus()
        self.remove_class("details-open", "filters-expanded")
        self._filters_expanded = False
        self.query_one(PokemonList).focus()

from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Label

from pokenux.models.pokemon.pokemon import Pokemon
from pokenux.textual.utils.pokemon_types import type_badges
from pokenux.textual.widgets.pokemon_art import PokemonArt

GENERATIONS = ("", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX")


def generation_label(generation: int) -> str:
    return (
        GENERATIONS[generation]
        if 0 < generation < len(GENERATIONS)
        else str(generation)
    )


class PokemonTableHeader(Horizontal):
    def compose(self) -> ComposeResult:
        yield Label("N°", classes="pokemon-number")
        yield Label("", classes="pokemon-thumbnail")
        yield Label("POKÉMON", classes="pokemon-identity")
        yield Label("TYPES", classes="pokemon-types")
        yield Label("Gén.", classes="pokemon-generation")
        yield Label("Stade", classes="pokemon-stage")

    def on_resize(self, event: events.Resize) -> None:
        self.set_class(event.size.width < 72, "dense")
        self.set_class(event.size.width < 60, "slim")
        self.set_class(event.size.width < 48, "tiny")


class PokemonRow(Horizontal):
    class Clicked(Message):
        def __init__(self, row: "PokemonRow"):
            super().__init__()
            self.row = row

    def __init__(self, pokemon: Pokemon):
        super().__init__(id=f"pokemon_row_{pokemon.pokedex_id}", classes="pokemon-row")
        self.pokemon = pokemon

    def compose(self) -> ComposeResult:
        pokemon = self.pokemon
        yield Label(f"#{pokemon.pokedex_id:04d}", classes="pokemon-number")
        yield PokemonArt(pokemon.sprites.regular, classes="pokemon-thumbnail")
        with Vertical(classes="pokemon-identity"):
            yield Label(pokemon.name.fr, classes="pokemon-name", markup=False)
            yield Label(pokemon.category, classes="pokemon-category", markup=False)
        yield Label(
            type_badges(
                t["name"] if isinstance(t, dict) else t.name for t in pokemon.types
            ),
            classes="pokemon-types",
        )
        yield Label(generation_label(pokemon.generation), classes="pokemon-generation")
        yield Label(pokemon.stage, classes="pokemon-stage")

    def on_resize(self, event: events.Resize) -> None:
        self.set_class(event.size.width < 72, "dense")
        self.set_class(event.size.width < 60, "slim")
        self.set_class(event.size.width < 48, "tiny")

    def on_click(self, event: events.Click) -> None:
        self.post_message(self.Clicked(self))
        event.stop()


class PokemonList(VerticalScroll):
    """An aligned sprite table with a single keyboard cursor and lazy rows."""

    can_focus = True
    BATCH_SIZE = 20
    ROW_HEIGHT = 4
    BINDINGS = [
        Binding("up", "move_selection(-1)", "Pokémon précédent", show=False),
        Binding("down", "move_selection(1)", "Pokémon suivant", show=False),
        Binding("home", "first", "Premier Pokémon", show=False),
        Binding("end", "last", "Dernier Pokémon", show=False),
        Binding("pageup", "move_page(-1)", "Page précédente", show=False),
        Binding("pagedown", "move_page(1)", "Page suivante", show=False),
        Binding("enter", "details", "Détails"),
    ]

    class Selected(Message):
        def __init__(self, pokemon: Pokemon | None, *, activated: bool = False):
            super().__init__()
            self.pokemon = pokemon
            self.activated = activated

    def __init__(self, pokemon_list: list[Pokemon]):
        super().__init__(id="pokemon_list")
        self.pokemon_list = pokemon_list
        self.loaded_count = 0
        self.loading = False
        self.selected_index = 0

    @property
    def selected_pokemon(self) -> Pokemon | None:
        return self.pokemon_list[self.selected_index] if self.pokemon_list else None

    def compose(self) -> ComposeResult:
        if self.pokemon_list:
            yield from self.next_rows()
        else:
            yield Label(
                "[bold]Aucun Pokémon trouvé[/]\n\n"
                + "Essaie un autre nom ou retire quelques filtres.\n"
                + "[dim]Tout effacer permet de retrouver tout le Pokédex.[/]",
                id="pokemon_empty",
            )

    def next_rows(self, minimum: int = 0) -> ComposeResult:
        start = self.loaded_count
        self.loaded_count = min(
            max(start + self.BATCH_SIZE, minimum), len(self.pokemon_list)
        )
        for index in range(start, self.loaded_count):
            row = PokemonRow(self.pokemon_list[index])
            row.set_class(index == self.selected_index, "selected")
            yield row

    def on_mount(self) -> None:
        self.post_message(self.Selected(self.selected_pokemon))
        self.call_after_refresh(self.check_more)

    async def set_pokemon(self, pokemon_list: list[Pokemon]) -> None:
        previous = self.selected_pokemon
        self.pokemon_list = pokemon_list
        self.selected_index = next(
            (
                i
                for i, pokemon in enumerate(pokemon_list)
                if previous and pokemon.pokedex_id == previous.pokedex_id
            ),
            0,
        )
        self.loaded_count = 0
        await self.remove_children()
        if pokemon_list:
            await self.mount(*self.next_rows(self.selected_index + 1))
            self.call_after_refresh(self.scroll_to_selection)
        else:
            await self.mount(
                Label(
                    "[bold]Aucun Pokémon trouvé[/]\n\n"
                    + "Essaie un autre nom ou retire quelques filtres.\n"
                    + "[dim]Tout effacer permet de retrouver tout le Pokédex.[/]",
                    id="pokemon_empty",
                )
            )
        self.post_message(self.Selected(self.selected_pokemon))
        self.call_after_refresh(self.check_more)

    async def select_index(self, index: int) -> None:
        if not self.pokemon_list:
            return
        self.selected_index = max(0, min(index, len(self.pokemon_list) - 1))
        if self.selected_index >= self.loaded_count:
            await self.mount(*self.next_rows(self.selected_index + 1))
        selected = self.pokemon_list[self.selected_index]
        selected_id = f"pokemon_row_{selected.pokedex_id}"
        for row in self.query(PokemonRow):
            row.set_class(row.id == selected_id, "selected")
        self.post_message(self.Selected(self.selected_pokemon))
        self.call_after_refresh(self.scroll_to_selection)

    def scroll_to_selection(self) -> None:
        if self.selected_pokemon and self.is_attached:
            row = self.query_one(
                f"#pokemon_row_{self.selected_pokemon.pokedex_id}", PokemonRow
            )
            self.scroll_to_widget(row, animate=False)

    @on(PokemonRow.Clicked)
    async def select_row(self, message: PokemonRow.Clicked) -> None:
        self.focus()
        await self.select_index(self.pokemon_list.index(message.row.pokemon))
        message.stop()

    async def action_move_selection(self, offset: int) -> None:
        await self.select_index(self.selected_index + offset)

    async def action_move_page(self, direction: int) -> None:
        await self.action_move_selection(
            direction * max(1, self.size.height // self.ROW_HEIGHT)
        )

    async def action_first(self) -> None:
        await self.select_index(0)

    async def action_last(self) -> None:
        await self.select_index(len(self.pokemon_list) - 1)

    def action_details(self) -> None:
        self.post_message(self.Selected(self.selected_pokemon, activated=True))

    def on_resize(self) -> None:
        self.call_after_refresh(self.check_more)

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        self.call_after_refresh(self.check_more)

    def check_more(self) -> None:
        if (
            self.is_attached
            and self.size.height > 0
            and not self.loading
            and self.loaded_count < len(self.pokemon_list)
            and self.scroll_y >= self.max_scroll_y - self.ROW_HEIGHT * 2
        ):
            self.loading = True
            self.call_after_refresh(self.load_more)

    async def load_more(self) -> None:
        try:
            if (
                self.is_attached
                and self.scroll_y >= self.max_scroll_y - self.ROW_HEIGHT * 2
            ):
                await self.mount(*self.next_rows())
        finally:
            self.loading = False
        self.call_after_refresh(self.check_more)

from textual.reactive import reactive
from textual.app import ComposeResult
from textual.containers import Container, Grid, Horizontal, Vertical, VerticalScroll
from textual.widgets import Checkbox, Input, Label, Select

from pokenux.models.pokemon.pokemon import Pokemon
from pokenux.services.pokedex import Pokedex
from pokenux.services import user_data
from pokenux.textual.utils import enums, i18n


class PokedexView(Vertical):
    active_generations: list[str] = reactive([])
    active_types: list[str] = reactive([])
    active_evolutions: list[str] = reactive([])
    pokemon_list: list[Pokemon] = reactive([], recompose=True)

    def on_mount(self) -> None:
        self.load_data()

    def load_data(self):
        self.pokemon_list = Pokedex().filter_pokemon(
            self.active_generations,
            self.active_types,
            self.active_evolutions,
        )

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Input(
                placeholder=i18n.trans("search_pokemon"),
                id="pokemon_input",
                name="search_pokemon",
                classes="i18n",
            )
            yield Select(
                options=enums.sort_by(),
                prompt=i18n.trans("sort_by"),
                allow_blank=True,
                name="sort_by",
                classes="i18n",
            )

        with Horizontal(id="pokedex_content"):
            with VerticalScroll(id="pokemon_filters"):
                with Container(classes="filters_container"):
                    yield Label("⌛ Génération")
                    with Grid(id="generations_grid"):
                        for generation in user_data.get_all_generations():
                            yield Checkbox(
                                generation,
                                id=f"generation_{generation}",
                                value=generation in self.active_generations,
                            )

                with Container(classes="filters_container"):
                    yield Label("🏷  Type")
                    with Grid(id="types_grid"):
                        for pokemon_type in user_data.get_all_types():
                            yield Checkbox(
                                str(pokemon_type["fr"]),
                                id=f"type_{pokemon_type['en']}",
                                value=pokemon_type["fr"] in self.active_types,
                            )

                with Container(classes="filters_container"):
                    yield Label("↗ Évolution")
                    with Grid(id="evolutions_grid"):
                        for evolution in enums.evolutions():
                            yield Checkbox(
                                evolution[0],
                                id=f"evolution_{evolution[1]}",
                                value=evolution[1] in self.active_evolutions,
                            )

            with Vertical():
                with Horizontal():
                    yield Label(str(len(self.pokemon_list)) + " Pokémon")

            with Vertical():
                yield Label("ok")

    def on_checkbox_changed(self) -> None:
        self.active_generations = [
            checkbox.label
            for checkbox in self.query(Checkbox)
            if checkbox.id.startswith("generation_") and checkbox.value
        ]

        self.active_types = [
            str(checkbox.label)
            for checkbox in self.query(Checkbox)
            if checkbox.id.startswith("type_") and checkbox.value
        ]

        self.active_evolutions = [
            str(checkbox.label)
            for checkbox in self.query(Checkbox)
            if checkbox.id.startswith("evolution_") and checkbox.value
        ]

    def watch_active_generations(self):
        self.load_data()

    def watch_active_types(self):
        self.load_data()

    def watch_active_evolutions(self):
        self.load_data()

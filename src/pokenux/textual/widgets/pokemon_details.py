"""Pokémon information and online image previews for the Pokédex side panel."""

from collections import defaultdict
from collections.abc import Mapping
from typing import cast, override

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import (
    Grid,
    Horizontal,
    HorizontalScroll,
    Vertical,
    VerticalScroll,
)
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Label, TabbedContent, TabPane, Tabs

from pokenux.models.pokemon.pokemon import Pokemon
from pokenux.models.tcg.card import Card
from pokenux.textual.widgets.remote_image import RemoteImage


def _field(value: object, name: str, default: str | int = "") -> str | int:
    """The asset loader leaves types and evolution entries as dictionaries."""
    if isinstance(value, Mapping):
        result = cast(Mapping[str, object], value).get(name, default)
    else:
        result = cast(object, getattr(value, name, default))
    return result if isinstance(result, (str, int)) else default


def _roman(number: int) -> str:
    generations = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")
    return generations[number - 1] if 1 <= number <= len(generations) else str(number)


_TYPE_COLORS = {
    "Feu": "#ff9c3d",
    "Eau": "#65b4ff",
    "Plante": "#82c96b",
    "Électrik": "#f5d65c",
    "Poison": "#c488d5",
    "Spectre": "#a193d5",
    "Dragon": "#b198ef",
    "Glace": "#8adddf",
    "Fée": "#ef9dcb",
}


class PokemonDetails(VerticalScroll):
    """Details that follow the currently selected table row."""

    can_focus: bool = True
    pokemon: reactive[Pokemon | None] = reactive(None, recompose=True)
    DEFAULT_CSS: str = """
    PokemonDetails {
        height: 1fr;
        width: 1fr;
        border: round #334154;
        background: #09121c;
        color: #e3eaf3;
        padding: 0 1;
    }

    PokemonDetails .details-empty {
        width: 1fr;
        height: 1fr;
        content-align: center middle;
        color: #8795a8;
    }

    PokemonDetails #details_heading {
        height: 3;
        border-bottom: solid #263443;
        padding-top: 1;
    }

    PokemonDetails #details_title {
        width: 1fr;
        height: 1;
        text-style: bold;
    }

    PokemonDetails .details-star {
        width: 2;
        color: #aab3be;
    }

    PokemonDetails #details_summary {
        height: 11;
        margin-top: 1;
    }

    PokemonDetails .details-sprite {
        width: 48%;
        height: 10;
        content-align: center middle;
    }

    PokemonDetails #details_metadata {
        width: 1fr;
        height: 10;
        padding: 1 0 0 1;
        border-left: solid #263443;
    }

    PokemonDetails .metadata-row {
        height: 2;
    }

    PokemonDetails .metadata-label {
        width: 11;
        color: #aab3be;
    }

    PokemonDetails .metadata-value {
        width: 1fr;
        height: auto;
    }

    PokemonDetails #details_chain {
        height: 6;
        border-top: solid #263443;
        border-bottom: solid #263443;
    }

    PokemonDetails .details-section-title {
        color: #5897ff;
        height: 1;
        margin-top: 1;
    }

    PokemonDetails .evolution-strip {
        height: 3;
        scrollbar-size-horizontal: 1;
    }

    PokemonDetails .evolution-node {
        width: auto;
        height: 3;
        align: left middle;
    }

    PokemonDetails .evolution-sprite {
        width: 5;
        height: 3;
        margin-right: 1;
        content-align: center middle;
    }

    PokemonDetails .evolution-name {
        width: auto;
        height: 1;
    }

    PokemonDetails .evolution-current {
        color: #5897ff;
        text-style: bold;
    }

    PokemonDetails .evolution-arrow {
        width: 3;
        height: 3;
        content-align: center middle;
        color: #8795a8;
    }

    PokemonDetails #details_tabs {
        height: 1fr;
        min-height: 17;
    }

    PokemonDetails #details_tabs > ContentTabs {
        height: 3;
    }

    PokemonDetails #details_tabs Tab {
        height: 3;
        padding: 0 1;
    }

    PokemonDetails #details_tabs > ContentSwitcher {
        height: 1fr;
    }

    PokemonDetails #details_tabs TabPane {
        height: 1fr;
        padding: 0;
    }

    PokemonDetails .details-pane {
        height: 1fr;
        padding: 0 1;
    }

    PokemonDetails .cards-heading {
        height: auto;
        margin: 1 0;
        color: #5897ff;
    }

    PokemonDetails .card-preview-row {
        height: 12;
    }

    PokemonDetails .card-preview {
        width: 1fr;
        height: 12;
        margin-right: 1;
    }

    PokemonDetails .card-art {
        width: 1fr;
        height: 9;
        content-align: center middle;
        border: round #a17f40;
        background: #29241d;
        color: #d8b471;
    }

    PokemonDetails .card-name {
        height: 1;
        width: 1fr;
        text-overflow: ellipsis;
        text-wrap: nowrap;
    }

    PokemonDetails .card-id {
        height: 1;
        width: 1fr;
        color: #8795a8;
        text-overflow: ellipsis;
        text-wrap: nowrap;
    }

    PokemonDetails .show-cards {
        width: 1fr;
        height: 3;
        margin-top: 1;
        border: round #365d91;
        color: #5897ff;
        background: #0d1826;
    }

    PokemonDetails .cards-grid {
        grid-size: 3;
        grid-columns: 1fr 1fr 1fr;
        grid-rows: auto;
        height: auto;
    }

    PokemonDetails .details-note {
        height: auto;
        margin: 1 0;
        color: #8795a8;
    }

    PokemonDetails .stat-row {
        height: 2;
        align: left middle;
    }

    PokemonDetails .stat-name {
        width: 15;
    }

    PokemonDetails .stat-value {
        width: 5;
        color: #5897ff;
    }

    PokemonDetails .stat-bar {
        width: 1fr;
    }

    PokemonDetails .evolution-detail {
        height: auto;
        margin: 1 0;
    }
    """

    def __init__(self, pokemon: Pokemon | None = None) -> None:
        super().__init__(id="pokemon_details")
        self.pokemon = pokemon
        self._active_tab: str = "pokemon_infos"
        self._visible_cards: int = 24
        self._series_cache: object | None = None
        self._card_index: dict[str, list[Card]] = {}
        self._focus_request: int = 0

    def set_pokemon(self, pokemon: Pokemon | None) -> None:
        """Select a Pokémon synchronously; Textual schedules the DOM update."""
        if self.pokemon is pokemon:
            return
        self._visible_cards = 24
        self.pokemon = pokemon

    def show_tcg(self) -> None:
        self._active_tab = "pokemon_tcg"
        if self.pokemon is not None and self.is_mounted:
            self.query_one("#details_tabs", TabbedContent).active = self._active_tab
            self.focus_details()

    def action_show_tcg(self) -> None:
        self.show_tcg()

    def focus_details(self) -> None:
        self._focus_request += 1
        if self.pokemon is not None and self.is_mounted:
            # The view may have just revealed this panel after it was hidden.
            # Wait for its new layout before focusing and revealing the tabs.
            _ = self.call_after_refresh(
                self._focus_tabs, self._focus_request, self.app.focused
            )
        else:
            _ = self.focus()

    def cancel_pending_focus(self) -> None:
        self._focus_request += 1

    def _focus_tabs(self, request: int, expected_focus: Widget | None) -> None:
        if (
            request == self._focus_request
            and self.pokemon is not None
            and self.is_mounted
            and self.display
            and self.region.height > 0
            and (self.app.focused is expected_focus or self.app.focused is None)
        ):
            _ = self.query_one(Tabs).focus()
            _ = self.scroll_to_widget(
                self.query_one("#details_tabs", TabbedContent),
                animate=False,
                top=True,
                force=True,
            )

    def _cards(self, pokemon: Pokemon) -> list[Card]:
        # tcg_library holds the installed language's collection. Import lazily so
        # a missing TCG dataset does not prevent Pokémon details from opening.
        try:
            from pokenux.services import tcg_library
        except OSError, ValueError:
            return []

        if self._series_cache is not tcg_library.series:
            index: dict[str, list[Card]] = defaultdict(list)
            for serie in tcg_library.series:
                for card_set in serie.sets:
                    for card in card_set.cards:
                        index[card.name.casefold()].append(card)
            self._card_index = dict(index)
            self._series_cache = tcg_library.series

        cards: dict[str, Card] = {}
        for name in (pokemon.name.fr, pokemon.name.en):
            for card in self._card_index.get(name.casefold(), []):
                cards[card.id] = card
        return list(cards.values())

    def _sprite(self, pokedex_id: int, classes: str) -> Widget:
        pokemon = self.pokemon
        if pokemon is None or pokemon.pokedex_id != pokedex_id:
            try:
                from pokenux.services import pokedex

                pokemon = pokedex.get_pokemon_by_id(pokedex_id)
            except OSError, ValueError:
                pokemon = None
        return RemoteImage(
            pokemon.sprites.regular if pokemon is not None else None,
            classes=classes,
        )

    def _card_preview(self, card: Card) -> Widget:
        image_url = f"{card.image.rstrip('/')}/low.png" if card.image else None
        art = RemoteImage(image_url, classes="card-art", placeholder="▤")
        preview = Vertical(
            art,
            Label(card.name, classes="card-name", markup=False),
            Label(card.id, classes="card-id", markup=False),
            classes="card-preview",
        )
        preview.tooltip = f"{card.name} · {card.id}"
        return preview

    @staticmethod
    def _evolution_nodes(pokemon: Pokemon) -> list[tuple[int, str, str]]:
        nodes = [
            (
                int(_field(entry, "pokedex_id")),
                str(_field(entry, "name")),
                str(_field(entry, "condition", "")),
            )
            for entry in pokemon.evolution.pre or []
        ]
        nodes.append((pokemon.pokedex_id, pokemon.name.fr, ""))
        nodes.extend(
            (
                int(_field(entry, "pokedex_id")),
                str(_field(entry, "name")),
                str(_field(entry, "condition", "")),
            )
            for entry in pokemon.evolution.next or []
        )
        return nodes

    @staticmethod
    def _branching(pokemon: Pokemon) -> bool:
        next_entries = pokemon.evolution.next or []
        if len(next_entries) <= 1:
            return False
        try:
            from pokenux.services import pokedex
        except OSError, ValueError:
            return True
        children: dict[int, int] = defaultdict(int)
        for entry in next_entries:
            evolution = pokedex.get_pokemon_by_id(int(_field(entry, "pokedex_id")))
            pre = evolution.evolution.pre if evolution is not None else None
            parent_id = (
                int(_field(pre[-1], "pokedex_id")) if pre else pokemon.pokedex_id
            )
            children[parent_id] += 1
        return any(count > 1 for count in children.values())

    @override
    def compose(self) -> ComposeResult:
        pokemon = self.pokemon
        if pokemon is None:
            yield Label(
                "Sélectionnez un Pokémon\npour afficher ses détails.",
                classes="details-empty",
            )
            return

        cards = self._cards(pokemon)
        with Horizontal(id="details_heading"):
            title = Text(f"#{pokemon.pokedex_id:04d} ", style="#5897ff bold")
            _ = title.append(pokemon.name.fr.upper(), style="#e3eaf3 bold")
            yield Label(title, id="details_title")
            yield Label("☆", classes="details-star")

        with Horizontal(id="details_summary"):
            yield self._sprite(pokemon.pokedex_id, "details-sprite")
            with Vertical(id="details_metadata"):
                types = Text()
                for index, pokemon_type in enumerate(pokemon.types):
                    name = str(_field(pokemon_type, "name", "?"))
                    if index:
                        _ = types.append(" / ")
                    _ = types.append(name, style=_TYPE_COLORS.get(name, "#e3eaf3"))
                for label, value in (
                    ("Type", types),
                    ("Génération", Text(_roman(pokemon.generation), style="#74cf98")),
                    ("Taille", pokemon.height),
                    ("Poids", pokemon.weight),
                ):
                    with Horizontal(classes="metadata-row"):
                        yield Label(label, classes="metadata-label")
                        yield Label(value, classes="metadata-value", markup=False)

        branching = self._branching(pokemon)
        with Vertical(id="details_chain"):
            yield Label(
                "Évolutions possibles" if branching else "Chaîne d’évolution",
                classes="details-section-title",
            )
            with HorizontalScroll(classes="evolution-strip"):
                for index, (pokedex_id, name, _) in enumerate(
                    self._evolution_nodes(pokemon)
                ):
                    if index:
                        yield Label(
                            "·" if branching else "→", classes="evolution-arrow"
                        )
                    with Horizontal(classes="evolution-node"):
                        yield self._sprite(pokedex_id, "evolution-sprite")
                        classes = "evolution-name"
                        if pokedex_id == pokemon.pokedex_id:
                            classes += " evolution-current"
                        yield Label(name, classes=classes, markup=False)

        with TabbedContent(id="details_tabs", initial=self._active_tab):
            with TabPane("Infos", id="pokemon_infos"):
                with VerticalScroll(classes="details-pane"):
                    yield Label(
                        f"Cartes TCG associées · {len(cards)}", classes="cards-heading"
                    )
                    if cards:
                        with Horizontal(classes="card-preview-row"):
                            for card in cards[:4]:
                                yield self._card_preview(card)
                        yield Button(
                            "Voir toutes les cartes →",
                            id="show_all_cards",
                            classes="show-cards",
                        )
                    else:
                        yield Label(
                            "Aucune carte associée dans la collection locale.",
                            classes="details-note",
                        )

            with TabPane("Stats", id="pokemon_stats"):
                with VerticalScroll(classes="details-pane"):
                    yield Label("Statistiques de base", classes="details-section-title")
                    total = 0
                    for name, attribute in (
                        ("PV", "hp"),
                        ("Attaque", "attack"),
                        ("Défense", "defense"),
                        ("Att. spéciale", "special_attack"),
                        ("Déf. spéciale", "special_defense"),
                        ("Vitesse", "speed"),
                    ):
                        value = cast(int, getattr(pokemon.stats, attribute))
                        total += value
                        filled = max(1, min(10, round(value / 255 * 10)))
                        bar = Text("━" * filled, style="#5897ff")
                        _ = bar.append("━" * (10 - filled), style="#283749")
                        with Horizontal(classes="stat-row"):
                            yield Label(name, classes="stat-name")
                            yield Label(str(value), classes="stat-value")
                            yield Label(bar, classes="stat-bar")
                    yield Label(f"Total : {total}", classes="details-note")

            with TabPane("Évolution", id="pokemon_evolution"):
                with VerticalScroll(classes="details-pane"):
                    yield Label(
                        pokemon.category, classes="details-section-title", markup=False
                    )
                    yield Label(f"Stade : {pokemon.stage}", classes="details-note")
                    for heading, entries in (
                        ("Pré-évolutions", pokemon.evolution.pre or []),
                        ("Évolutions", pokemon.evolution.next or []),
                    ):
                        if entries:
                            yield Label(heading, classes="details-section-title")
                            for entry in entries:
                                name = str(_field(entry, "name"))
                                condition = str(_field(entry, "condition", ""))
                                yield Label(
                                    f"{name}\n{condition}",
                                    classes="evolution-detail",
                                    markup=False,
                                )
                    if not pokemon.evolution.pre and not pokemon.evolution.next:
                        yield Label(
                            "Ce Pokémon n’a pas d’évolution.", classes="details-note"
                        )

            with TabPane(f"TCG {len(cards)}", id="pokemon_tcg"):
                with VerticalScroll(classes="details-pane"):
                    yield Label(
                        f"{len(cards)} cartes associées", classes="cards-heading"
                    )
                    if cards:
                        with Grid(classes="cards-grid"):
                            for card in cards[: self._visible_cards]:
                                yield self._card_preview(card)
                        if len(cards) > self._visible_cards:
                            yield Button(
                                "Afficher les cartes suivantes",
                                id="more_cards",
                                classes="show-cards",
                            )
                    else:
                        yield Label(
                            "Aucune carte associée dans la collection locale.",
                            classes="details-note",
                        )

    @on(TabbedContent.TabActivated, "#details_tabs")
    def remember_tab(self, event: TabbedContent.TabActivated) -> None:
        self._active_tab = event.pane.id or "pokemon_infos"
        _ = event.stop()

    @on(Button.Pressed, "#show_all_cards")
    def open_all_cards(self, event: Button.Pressed) -> None:
        _ = event.stop()
        self.show_tcg()

    @on(Button.Pressed, "#more_cards")
    async def show_more_cards(self, event: Button.Pressed) -> None:
        _ = event.stop()
        self._visible_cards += 24
        await self.recompose()

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
from pokenux.services import pokedex, user_data
from pokenux.textual.utils import i18n
from pokenux.textual.utils.navigation import is_active_view
from pokenux.textual.utils.pokemon_types import TYPE_COLORS, type_badges
from pokenux.textual.widgets.pokemon_art import PokemonArt
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


class PokemonDetails(VerticalScroll):
    """Details that follow the currently selected table row."""

    can_focus: bool = True
    pokemon: reactive[Pokemon | None] = reactive(None, recompose=True)
    DEFAULT_CSS: str = """
    PokemonDetails {
        height: 1fr;
        width: 1fr;
        border: round #2c4059;
        background: #111d2d;
        color: #e4ebf5;
        padding: 0 1;
        scrollbar-size: 1 1;
        scrollbar-background: #111d2d;
        scrollbar-color: #344d6c;
        scrollbar-color-hover: #83b7ff;
    }

    PokemonDetails:focus-within {
        border: round #577aa5;
    }

    PokemonDetails .details-empty {
        width: 1fr;
        height: 1fr;
        content-align: center middle;
        color: #99aabd;
        padding: 2;
    }

    PokemonDetails #details_heading {
        height: 2;
        padding-top: 1;
    }

    PokemonDetails #details_number {
        width: 1fr;
        color: #83b7ff;
        text-style: bold;
    }

    PokemonDetails #details_generation {
        width: auto;
        color: #99aabd;
    }

    PokemonDetails #details_summary {
        height: 8;
        margin-top: 1;
    }

    PokemonDetails .details-sprite {
        width: 42%;
        height: 7;
        background: #17283c;
        content-align: center middle;
    }

    PokemonDetails #details_metadata {
        width: 1fr;
        height: 7;
        padding: 1 0 0 1;
    }

    PokemonDetails #details_title {
        width: 1fr;
        height: auto;
        text-style: bold;
    }

    PokemonDetails #details_category {
        width: 1fr;
        height: auto;
        color: #99aabd;
        margin-bottom: 1;
    }

    PokemonDetails #details_types {
        height: auto;
        width: 1fr;
    }

    PokemonDetails #details_measurements {
        height: 3;
        background: #17283c;
        padding: 0;
    }

    PokemonDetails .measurement {
        width: 1fr;
        height: 2;
        align: center middle;
    }

    PokemonDetails .measurement-divider {
        border-left: solid #304660;
    }

    PokemonDetails .measurement-label {
        width: 1fr;
        height: 1;
        color: #99aabd;
        content-align: center middle;
    }

    PokemonDetails .measurement-value {
        width: 1fr;
        height: 1;
        content-align: center middle;
        text-style: bold;
    }

    PokemonDetails #details_chain {
        height: 6;
    }

    PokemonDetails .details-section-title {
        color: #83b7ff;
        text-style: bold;
        height: 1;
        margin-top: 1;
    }

    PokemonDetails .evolution-strip {
        height: 4;
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
        color: #99aabd;
    }

    PokemonDetails .evolution-current {
        color: #e4ebf5;
        text-style: bold;
    }

    PokemonDetails .evolution-arrow {
        width: 3;
        height: 3;
        content-align: center middle;
        color: #5c7796;
    }

    PokemonDetails #details_tabs {
        height: 1fr;
        min-height: 12;
    }

    PokemonDetails #details_tabs > ContentTabs {
        height: 2;
    }

    PokemonDetails #details_tabs Tabs { height: 2; }

    PokemonDetails #details_tabs Tab {
        height: 1;
        padding: 0 1;
        color: #99aabd;
        background: #111d2d;
    }

    PokemonDetails #details_tabs Tab.-active {
        color: #e4ebf5;
        text-style: bold;
        background: #1d3450;
    }

    PokemonDetails #details_tabs Underline > .underline--bar {
        color: #83b7ff;
        background: #263b53;
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
        scrollbar-size: 1 1;
    }

    PokemonDetails .profile-value {
        height: auto;
        color: #e4ebf5;
    }

    PokemonDetails .cards-heading {
        height: auto;
        margin: 1 0;
        color: #83b7ff;
        text-style: bold;
    }

    PokemonDetails .card-preview-row {
        height: 13;
    }

    PokemonDetails .card-preview {
        width: 1fr;
        height: 13;
        padding: 0 1 0 0;
    }

    PokemonDetails .card-art {
        width: 1fr;
        height: 10;
        content-align: center middle;
        border: round #756345;
        background: #232b35;
        color: #e5c185;
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
        color: #99aabd;
        text-overflow: ellipsis;
        text-wrap: nowrap;
    }

    PokemonDetails .show-cards {
        width: 1fr;
        height: 3;
        margin-top: 1;
        border: round #436a98;
        color: #b9d8ff;
        background: #1d3450;
        text-style: bold;
    }

    PokemonDetails .show-cards:hover,
    PokemonDetails .show-cards:focus {
        background: #29476a;
        border: round #83b7ff;
    }

    PokemonDetails .cards-grid {
        grid-size: 2;
        grid-columns: 1fr 1fr;
        grid-rows: auto;
        height: auto;
    }

    PokemonDetails .details-note {
        height: auto;
        margin: 1 0;
        color: #99aabd;
    }

    PokemonDetails .stat-row {
        height: 2;
        align: left middle;
    }

    PokemonDetails .stat-name {
        width: 13;
        color: #99aabd;
    }

    PokemonDetails .stat-value {
        width: 4;
        text-style: bold;
    }

    PokemonDetails .stat-bar {
        width: 1fr;
        text-wrap: nowrap;
        overflow-x: hidden;
    }

    PokemonDetails .stat-total {
        height: 3;
        border-top: solid #263b53;
        padding-top: 1;
        text-style: bold;
        color: #e4ebf5;
    }

    PokemonDetails .evolution-detail {
        height: auto;
        margin: 1 0;
        padding: 0 1;
        border-left: thick #436a98;
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
        self._pending_focus: tuple[int, Widget | None, bool] | None = None

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

    def focus_details(self, *, overview: bool = False) -> None:
        self._focus_request += 1
        if self.pokemon is not None and self.is_mounted:
            # The view may have just revealed this panel after it was hidden.
            # Wait for its new layout before focusing and revealing the tabs.
            self._pending_focus = (self._focus_request, self.app.focused, overview)
            _ = self.call_after_refresh(self._focus_tabs, *self._pending_focus)
        else:
            _ = self.focus()

    def cancel_pending_focus(self) -> None:
        self._focus_request += 1
        self._pending_focus = None

    def on_resize(self) -> None:
        # Revealing a hidden panel can complete after the first refresh callback.
        # Its resize event gives us the actual layout without a timer or polling.
        if self._pending_focus is not None:
            _ = self.call_after_refresh(self._focus_tabs, *self._pending_focus)

    def _focus_tabs(
        self, request: int, expected_focus: Widget | None, overview: bool = False
    ) -> None:
        if (
            request == self._focus_request
            and self._pending_focus is not None
            and self.pokemon is not None
            and self.is_mounted
            and is_active_view(self)
            and self.display
            and self.region.height > 0
            and (self.app.focused is expected_focus or self.app.focused is None)
        ):
            self._pending_focus = None
            if overview:
                _ = self.focus()
                self.scroll_home(animate=False, force=True)
            else:
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

        if tcg_library.get_language_status().requested != user_data.get_tcg_lang():
            tcg_library.set_language(user_data.get_tcg_lang())
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
        return PokemonArt(
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
    def _evolution_name(entry: object) -> str:
        language = user_data.get_pokemon_lang()
        related = pokedex.get_pokemon_by_id(int(_field(entry, "pokedex_id")))
        if related is not None:
            return related.localized_name(language)
        return (
            str(_field(entry, "name_en" if language == "en" else "name"))
            or f"#{_field(entry, 'pokedex_id')}"
        )

    @staticmethod
    def _evolution_condition(entry: object) -> str:
        if user_data.get_pokemon_lang() == "fr":
            return str(_field(entry, "condition"))
        translated = str(_field(entry, "condition_en"))
        if translated or not _field(entry, "condition"):
            return translated
        return i18n.text(
            "Condition indisponible en anglais",
            "Evolution condition unavailable in English",
        )

    @classmethod
    def _evolution_nodes(cls, pokemon: Pokemon) -> list[tuple[int, str, str]]:
        return (
            [
                (
                    int(_field(entry, "pokedex_id")),
                    cls._evolution_name(entry),
                    cls._evolution_condition(entry),
                )
                for entry in pokemon.evolution.pre or []
            ]
            + [
                (
                    pokemon.pokedex_id,
                    pokemon.localized_name(user_data.get_pokemon_lang()),
                    "",
                )
            ]
            + [
                (
                    int(_field(entry, "pokedex_id")),
                    cls._evolution_name(entry),
                    cls._evolution_condition(entry),
                )
                for entry in pokemon.evolution.next or []
            ]
        )

    async def refresh_language(self) -> None:
        if self.is_mounted:
            await self.recompose()

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
                i18n.text(
                    "Sélectionnez un Pokémon\npour afficher ses détails.",
                    "Select a Pokémon\nto see its details.",
                ),
                classes="details-empty",
            )
            return

        cards = self._cards(pokemon)
        accent = TYPE_COLORS.get(
            str(_field(pokemon.types[0], "name")) if pokemon.types else "", "#83b7ff"
        )
        with Horizontal(id="details_heading"):
            yield Label(f"N° {pokemon.pokedex_id:04d}", id="details_number")
            yield Label(
                i18n.text(
                    "GÉNÉRATION {number}",
                    "GENERATION {number}",
                    number=_roman(pokemon.generation),
                ),
                id="details_generation",
            )

        with Horizontal(id="details_summary"):
            yield self._sprite(pokemon.pokedex_id, "details-sprite")
            with Vertical(id="details_metadata"):
                yield Label(
                    pokemon.localized_name(user_data.get_pokemon_lang()),
                    id="details_title",
                    markup=False,
                )
                yield Label(
                    pokemon.localized_category(user_data.get_pokemon_lang())
                    or i18n.text("Catégorie indisponible", "Category unavailable"),
                    id="details_category",
                    markup=False,
                )
                yield Label(
                    type_badges(pokedex.pokemon_types(pokemon)),
                    id="details_types",
                )

        with Horizontal(id="details_measurements"):
            for index, (label, value) in enumerate(
                (
                    (i18n.text("TAILLE", "HEIGHT"), pokemon.height),
                    (i18n.text("POIDS", "WEIGHT"), pokemon.weight),
                )
            ):
                classes = "measurement measurement-divider" if index else "measurement"
                with Vertical(classes=classes):
                    yield Label(
                        value.replace(",", ".")
                        if user_data.get_pokemon_lang() == "en"
                        else value,
                        classes="measurement-value",
                        markup=False,
                    )
                    yield Label(label, classes="measurement-label")

        with TabbedContent(id="details_tabs", initial=self._active_tab):
            with TabPane("Infos", id="pokemon_infos"):
                with VerticalScroll(classes="details-pane"):
                    yield Label(
                        i18n.text("Talents", "Abilities"),
                        classes="details-section-title",
                    )
                    talents = Text()
                    for index, talent in enumerate(pokemon.talents):
                        if index:
                            _ = talents.append(" · ", style="#5c7796")
                        _ = talents.append(
                            (
                                talent.name_en
                                or i18n.text(
                                    "Nom anglais indisponible",
                                    "English name unavailable",
                                )
                            )
                            if user_data.get_pokemon_lang() == "en"
                            else talent.name
                        )
                        if talent.hidden:
                            _ = talents.append(
                                i18n.text(" (caché)", " (hidden)"), style="#99aabd"
                            )
                    yield Label(
                        talents or i18n.text("Non renseignés", "Not recorded"),
                        classes="profile-value",
                    )
                    yield Label(
                        i18n.text("Groupes d’œufs", "Egg groups"),
                        classes="details-section-title",
                    )
                    yield Label(
                        " · ".join(
                            (
                                pokemon.egg_groups_en
                                if user_data.get_pokemon_lang() == "en"
                                else pokemon.egg_groups
                            )
                            or []
                        )
                        or i18n.text("Non renseignés", "Not recorded"),
                        classes="profile-value",
                        markup=False,
                    )
                    yield Label(
                        i18n.text(
                            "Cartes à collectionner · {count}",
                            "Trading cards · {count}",
                            count=len(cards),
                        ),
                        classes="cards-heading",
                    )
                    if cards:
                        with Horizontal(classes="card-preview-row"):
                            for card in cards[:2]:
                                yield self._card_preview(card)
                        yield Button(
                            i18n.text("Voir toutes les cartes →", "View all cards →"),
                            id="show_all_cards",
                            classes="show-cards",
                        )
                    else:
                        yield Label(
                            i18n.text(
                                "Aucune carte associée dans la collection locale.",
                                "No related cards in the local catalogue.",
                            ),
                            classes="details-note",
                        )

            with TabPane("Stats", id="pokemon_stats"):
                with VerticalScroll(classes="details-pane"):
                    yield Label(
                        i18n.text("Statistiques de base", "Base stats"),
                        classes="details-section-title",
                    )
                    total = 0
                    for name, attribute in (
                        (i18n.text("PV", "HP"), "hp"),
                        (i18n.text("Attaque", "Attack"), "attack"),
                        (i18n.text("Défense", "Defense"), "defense"),
                        (i18n.text("Att. spéciale", "Sp. Attack"), "special_attack"),
                        (i18n.text("Déf. spéciale", "Sp. Defense"), "special_defense"),
                        (i18n.text("Vitesse", "Speed"), "speed"),
                    ):
                        value = cast(int, getattr(pokemon.stats, attribute))
                        total += value
                        filled = max(1, min(10, round(value / 255 * 10)))
                        bar = Text("━" * filled, style=accent)
                        _ = bar.append("━" * (10 - filled), style="#30435a")
                        with Horizontal(classes="stat-row"):
                            yield Label(name, classes="stat-name")
                            yield Label(str(value), classes="stat-value")
                            yield Label(bar, classes="stat-bar")
                    yield Label(f"TOTAL  {total}", classes="stat-total")

            with TabPane(i18n.text("Évol.", "Evol."), id="pokemon_evolution"):
                with VerticalScroll(classes="details-pane"):
                    branching = self._branching(pokemon)
                    with Vertical(id="details_chain"):
                        yield Label(
                            i18n.text("Évolutions possibles", "Possible evolutions")
                            if branching
                            else i18n.text("Lignée évolutive", "Evolution chain"),
                            classes="details-section-title",
                        )
                        with HorizontalScroll(classes="evolution-strip"):
                            for index, (pokedex_id, name, _) in enumerate(
                                self._evolution_nodes(pokemon)
                            ):
                                if index:
                                    yield Label(
                                        "·" if branching else "→",
                                        classes="evolution-arrow",
                                    )
                                with Horizontal(classes="evolution-node"):
                                    yield self._sprite(pokedex_id, "evolution-sprite")
                                    classes = "evolution-name"
                                    if pokedex_id == pokemon.pokedex_id:
                                        classes += " evolution-current"
                                    yield Label(name, classes=classes, markup=False)
                    yield Label(
                        i18n.text(
                            "Stade : {stage}",
                            "Stage: {stage}",
                            stage=pokedex.stage_name(pokemon),
                        ),
                        classes="details-note",
                    )
                    for heading, entries in (
                        (
                            i18n.text("Pré-évolutions", "Previous evolutions"),
                            pokemon.evolution.pre or [],
                        ),
                        (
                            i18n.text("Évolutions", "Evolutions"),
                            pokemon.evolution.next or [],
                        ),
                    ):
                        if entries:
                            yield Label(heading, classes="details-section-title")
                            for entry in entries:
                                name = self._evolution_name(entry)
                                condition = self._evolution_condition(entry)
                                yield Label(
                                    f"{name}\n{condition}" if condition else name,
                                    classes="evolution-detail",
                                    markup=False,
                                )
                    if not pokemon.evolution.pre and not pokemon.evolution.next:
                        yield Label(
                            i18n.text(
                                "Ce Pokémon n’a pas d’évolution.",
                                "This Pokémon does not evolve.",
                            ),
                            classes="details-note",
                        )

            with TabPane(f"TCG {len(cards)}", id="pokemon_tcg"):
                with VerticalScroll(classes="details-pane"):
                    yield Label(
                        i18n.text(
                            "{count} cartes associées",
                            "{count} related cards",
                            count=len(cards),
                        ),
                        classes="cards-heading",
                    )
                    if cards:
                        with Grid(classes="cards-grid"):
                            for card in cards[: self._visible_cards]:
                                yield self._card_preview(card)
                        if len(cards) > self._visible_cards:
                            yield Button(
                                i18n.text(
                                    "Afficher les cartes suivantes", "Show more cards"
                                ),
                                id="more_cards",
                                classes="show-cards",
                            )
                    else:
                        yield Label(
                            i18n.text(
                                "Aucune carte associée dans la collection locale.",
                                "No related cards in the local catalogue.",
                            ),
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

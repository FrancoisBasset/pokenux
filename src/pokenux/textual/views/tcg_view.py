"""Browse the installed TCG catalogue and search card metadata."""

import re
from dataclasses import dataclass
from unicodedata import normalize
from typing import TypedDict

from rich.text import Text
from textual import events, on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.timer import Timer
from textual.widgets import Button, DataTable, Input, Label, Select, Tree
from textual.worker import get_current_worker
from textual.widgets.tree import TreeNode

from pokenux.models.tcg.card import Card
from pokenux.models.tcg.serie import Serie
from pokenux.models.tcg.set import Set
from pokenux.services import tcg_library, user_data
from pokenux.services.api.tcgdex import TCGdexError
from pokenux.textual.widgets.tcg_card_details import TcgCardDetails


def parse_hp(value: str) -> tuple[int | None, int | None]:
    """Accept an exact HP value or an inclusive range; reject partial input."""
    value = value.strip()
    if not value:
        return None, None
    match = re.fullmatch(r"([0-9]+)(?:\s*[-–]\s*([0-9]+))?", value)
    if match is None:
        raise ValueError("HP : entrez un nombre (120) ou une plage (50-100).")
    minimum = int(match[1])
    maximum = int(match[2]) if match[2] is not None else minimum
    if minimum > maximum:
        raise ValueError("HP : le minimum doit être inférieur ou égal au maximum.")
    return minimum, maximum


@dataclass(frozen=True)
class CatalogueScope:
    serie_id: str | None = None
    set_id: str | None = None


class SearchFilters(TypedDict):
    name: str
    hp_min: int | None
    hp_max: int | None
    card_type: str
    illustrator: str
    serie_id: str | None
    set_id: str | None


class TcgView(Vertical):
    PAGE_SIZE = 100
    BINDINGS = [
        Binding("/", "focus_search", "Rechercher"),
        Binding("f", "focus_catalogue", "Séries"),
        Binding("ctrl+f", "toggle_filters", "Filtres"),
        Binding("r", "reset_filters", "Réinitialiser"),
        Binding("escape", "focus_cards", "Cartes"),
    ]

    class SearchFinished(Message):
        def __init__(self, revision: int, cards: list[Card], note: str) -> None:
            super().__init__()
            self.revision, self.cards, self.note = revision, cards, note

    class SearchFailed(Message):
        def __init__(self, revision: int) -> None:
            super().__init__()
            self.revision = revision

    class DetailsFinished(Message):
        def __init__(self, revision: int, card: Card, error: str | None) -> None:
            super().__init__()
            self.revision, self.card, self.error = revision, card, error

    def __init__(self) -> None:
        super().__init__()
        self._ready = False
        self._scope = CatalogueScope()
        self._cards: list[Card] = []
        self._page = 0
        self._search_revision = 0
        self._details_revision = 0
        self._search_timer: Timer | None = None
        self._details_timer: Timer | None = None
        self._selected: Card | None = None
        self._requested_language: str | None = None
        self._language_note = ""
        self._search_note = ""
        self._series: dict[str, Serie] = {}
        self._sets: dict[str, Set] = {}
        self._catalogue_nodes: dict[CatalogueScope, TreeNode[CatalogueScope]] = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="tcg_heading"):
            yield Label("▤  CARTES TCG", id="tcg_title")
            yield Label("", id="tcg_catalogue_count", markup=False)
        with Horizontal(id="tcg_toolbar"):
            yield Button(
                "Séries",
                id="tcg_browse",
                tooltip="Parcourir les séries et extensions (f)",
            )
            yield Input(placeholder="Rechercher une carte par nom…", id="tcg_name")
            yield Button(
                "Filtres",
                id="tcg_toggle_filters",
                tooltip="Afficher les filtres (Ctrl+F)",
            )
            yield Button(
                "↻ Effacer",
                id="tcg_reset",
                tooltip="Réinitialiser tous les filtres (r)",
            )
        with Horizontal(id="tcg_filters"):
            with Vertical(classes="tcg-field", id="tcg_hp_field"):
                yield Label("HP / PV", classes="tcg-field-label")
                yield Input(placeholder="120 ou 50-100", id="tcg_hp")
            with Vertical(classes="tcg-field", id="tcg_type_field"):
                yield Label("Type de carte", classes="tcg-field-label")
                yield Select(
                    [("Tous les types", "")], value="", allow_blank=False, id="tcg_type"
                )
            with Vertical(classes="tcg-field", id="tcg_illustrator_field"):
                yield Label("Illustrateur", classes="tcg-field-label")
                yield Input(placeholder="Nom de l’artiste…", id="tcg_illustrator")
            with Vertical(classes="tcg-field", id="tcg_sort_field"):
                yield Label("Trier par", classes="tcg-field-label")
                yield Select(
                    [
                        ("Catalogue", "catalogue"),
                        ("Nom A → Z", "name"),
                        ("HP croissants", "hp_asc"),
                        ("HP décroissants", "hp_desc"),
                    ],
                    value="catalogue",
                    allow_blank=False,
                    id="tcg_sort",
                )
        with Horizontal(id="tcg_content"):
            with Vertical(id="tcg_catalogue_panel"):
                yield Label("SÉRIES & EXTENSIONS", classes="tcg-panel-title")
                yield Tree(
                    "Toutes les cartes", data=CatalogueScope(), id="tcg_catalogue"
                )
                yield Label(
                    "Entrée : choisir · Espace : développer", id="tcg_tree_hint"
                )
            with Vertical(id="tcg_results_panel"):
                yield Label("Toutes les cartes", id="tcg_scope", markup=False)
                yield Label("", id="tcg_scope_info", markup=False)
                with Horizontal(id="tcg_result_heading"):
                    yield Label("Chargement…", id="tcg_count", markup=False)
                    yield Button("Voir la fiche →", id="tcg_open_card", disabled=True)
                yield DataTable(
                    id="tcg_cards",
                    cursor_type="row",
                    zebra_stripes=True,
                    show_row_labels=False,
                )
                yield Label("", id="tcg_empty", markup=False)
                with Horizontal(id="tcg_pagination"):
                    yield Button("← Précédent", id="tcg_previous", disabled=True)
                    yield Label("Page 1 / 1", id="tcg_page")
                    yield Button("Suivant →", id="tcg_next", disabled=True)
            yield TcgCardDetails()
        with Horizontal(id="tcg_status_bar"):
            yield Label("", id="tcg_status", markup=False)
            yield Button("Réessayer", id="tcg_retry")

    def on_mount(self) -> None:
        table = self.query_one("#tcg_cards", DataTable)
        for label, key, width in (
            ("N°", "number", 13),
            ("Carte", "name", 25),
            ("HP", "hp", 5),
            ("Type", "type", 15),
            ("Extension", "set", 24),
            ("Illustrateur", "illustrator", 24),
        ):
            table.add_column(label, key=key, width=width)
        self.query_one("#tcg_retry", Button).display = False
        self._ready = True
        self._load_catalogue()
        self.call_after_refresh(table.focus)

    def on_show(self) -> None:
        if self._ready:
            if self._requested_language != user_data.get_tcg_lang():
                self._load_catalogue()
            self.call_after_refresh(self._focus_on_show)

    def _focus_on_show(self) -> None:
        if self.is_mounted and self.region.height > 0 and self.app.focused is None:
            table = self.query_one("#tcg_cards", DataTable)
            if table.display:
                table.focus()
            else:
                self.query_one("#tcg_name", Input).focus()

    def on_resize(self, event: events.Resize) -> None:
        self.set_class(event.size.width < 150, "compact")
        self.set_class(event.size.width < 95, "narrow")
        self.set_class(event.size.width < 65, "small")
        self.set_class(event.size.height < 30, "short")

    def _load_catalogue(self) -> None:
        self._requested_language = user_data.get_tcg_lang()
        if (
            tcg_library.get_language_status().requested != self._requested_language
            or not tcg_library.series
        ):
            tcg_library.set_language(self._requested_language)
        status = tcg_library.get_language_status()
        self._language_note = status.warning
        self._series = {serie.id: serie for serie in tcg_library.series}
        self._sets = {card_set.id: card_set for card_set in tcg_library.get_sets()}
        self._scope = CatalogueScope()
        tree = self.query_one("#tcg_catalogue", Tree)
        tree.clear()
        tree.root.set_label(Text("Toutes les cartes"))
        tree.root.expand()
        self._catalogue_nodes = {CatalogueScope(): tree.root}
        for serie in sorted(
            self._series.values(), key=lambda s: s.release_date or "", reverse=True
        ):
            scope = CatalogueScope(serie.id)
            node = tree.root.add(Text(f"{serie.name} ({len(serie.sets)})"), data=scope)
            self._catalogue_nodes[scope] = node
            for card_set in sorted(
                serie.sets, key=lambda s: s.release_date or "", reverse=True
            ):
                scope = CatalogueScope(serie.id, card_set.id)
                self._catalogue_nodes[scope] = node.add_leaf(
                    Text(f"{card_set.name} · {len(card_set.cards)}"), data=scope
                )
        language = {"fr": "FR", "en": "EN"}.get(status.active, status.active or "—")
        self.query_one("#tcg_catalogue_count", Label).update(
            f"{len(self._series)} séries · {len(self._sets)} extensions · {language}"
        )
        select = self.query_one("#tcg_type", Select)
        with select.prevent(Select.Changed):
            select.set_options(
                [("Tous les types", "")] + [(t, t) for t in tcg_library.get_types()]
            )
            select.value = ""
        self._update_scope()
        self._queue_search(immediate=True)

    def _update_scope(self) -> None:
        serie = self._series.get(self._scope.serie_id or "")
        card_set = self._sets.get(self._scope.set_id or "")
        title = (
            f"{serie.name} / {card_set.name}"
            if serie and card_set
            else serie.name
            if serie
            else "Toutes les cartes"
        )
        if card_set:
            info = f"{len(card_set.cards)} cartes · Sortie : {card_set.release_date or '—'}"
        elif serie:
            info = f"{len(serie.sets)} extensions · {sum(len(s.cards) for s in serie.sets)} cartes"
        else:
            info = "Explorez le catalogue ou combinez les filtres ci-dessus."
        self.query_one("#tcg_scope", Label).update(title)
        self.query_one("#tcg_scope_info", Label).update(info)

    @on(Tree.NodeSelected, "#tcg_catalogue")
    def scope_selected(self, event: Tree.NodeSelected[CatalogueScope]) -> None:
        event.stop()
        self._scope = event.node.data or CatalogueScope()
        event.node.expand()
        self._update_scope()
        self.remove_class("catalogue-open", "details-open")
        self._queue_search(immediate=True)
        self.query_one("#tcg_cards", DataTable).focus()

    @on(Input.Changed, "#tcg_name")
    @on(Input.Changed, "#tcg_hp")
    @on(Input.Changed, "#tcg_illustrator")
    @on(Select.Changed, "#tcg_type")
    def filters_changed(self) -> None:
        self._queue_search()

    @on(Input.Submitted)
    def submit_search(self) -> None:
        self.remove_class("filters-open")
        self._queue_search(immediate=True)
        self.call_after_refresh(self.action_focus_cards)

    def _queue_search(self, *, immediate: bool = False) -> None:
        if not self._ready:
            return
        self._search_revision += 1
        self.workers.cancel_group(self, "tcg-search")
        if self._search_timer is not None:
            self._search_timer.stop()
        if immediate:
            self._start_search()
        else:
            self._search_timer = self.set_timer(0.3, self._start_search)

    def _start_search(self) -> None:
        hp_input = self.query_one("#tcg_hp", Input)
        try:
            hp_min, hp_max = parse_hp(hp_input.value)
        except ValueError as error:
            hp_input.add_class("-invalid")
            self._show_status(str(error), error=True)
            self._cards = []
            self.query_one("#tcg_retry", Button).display = False
            self._render_page(
                empty_message="Corrigez le filtre HP pour rechercher des cartes."
            )
            return
        hp_input.remove_class("-invalid")
        self._show_status("Recherche en cours…")
        self.query_one("#tcg_count", Label).update("Recherche…")
        self.query_one("#tcg_retry", Button).display = False
        self._search(
            self._search_revision,
            dict(
                name=self.query_one("#tcg_name", Input).value,
                hp_min=hp_min,
                hp_max=hp_max,
                card_type=str(self.query_one("#tcg_type", Select).value or ""),
                illustrator=self.query_one("#tcg_illustrator", Input).value,
                serie_id=self._scope.serie_id,
                set_id=self._scope.set_id,
            ),
        )

    @work(thread=True, exclusive=True, group="tcg-search", exit_on_error=False)
    def _search(self, revision: int, filters: SearchFilters) -> None:
        worker = get_current_worker()
        try:
            result = tcg_library.search_cards_online(**filters)
            note = result.warning
            if result.source == "online":
                note = (
                    note or "Résultats TCGdex · Les détails se chargent à la sélection."
                )
            elif result.source == "cache":
                note = note or "Résultats enregistrés · disponibles hors connexion."
            else:
                note = (
                    note or "Catalogue local · Entrée pour ouvrir la fiche d’une carte."
                )
            if not worker.is_cancelled:
                self.post_message(self.SearchFinished(revision, result.cards, note))
        except TCGdexError, OSError, ValueError:
            if not worker.is_cancelled:
                self.post_message(self.SearchFailed(revision))

    @on(SearchFinished)
    def search_finished(self, event: SearchFinished) -> None:
        event.stop()
        if event.revision != self._search_revision:
            return
        self._cards, self._search_note, self._page = event.cards, event.note, 0
        self._sort_cards()
        self._render_page()
        self._show_status(self._search_note)

    @on(SearchFailed)
    def search_failed(self, event: SearchFailed) -> None:
        event.stop()
        if event.revision != self._search_revision:
            return
        self._cards, self._page = [], 0
        self._render_page(
            empty_message="La recherche n’a pas abouti. Réessayez ou retirez les filtres avancés."
        )
        self._show_status(
            "TCGdex indisponible. Vérifiez votre connexion puis réessayez.", error=True
        )
        self.query_one("#tcg_retry", Button).display = True

    def _show_status(self, message: str, *, error: bool = False) -> None:
        label = self.query_one("#tcg_status", Label)
        label.update(" · ".join(filter(None, (self._language_note, message))))
        label.set_class(error, "tcg-error")

    @on(Select.Changed, "#tcg_sort")
    def sort_changed(self) -> None:
        if self._ready:
            self._sort_cards()
            self._page = 0
            self._render_page()

    def _sort_cards(self) -> None:
        sort = self.query_one("#tcg_sort", Select).value
        if sort == "name":
            self._cards.sort(key=lambda card: normalize("NFKD", card.name.casefold()))
        elif sort in ("hp_asc", "hp_desc"):
            direction = -1 if sort == "hp_desc" else 1
            self._cards.sort(
                key=lambda card: (
                    card.hp is None,
                    direction * (card.hp or 0),
                    card.name.casefold(),
                )
            )
        else:
            order = {
                card.id: index
                for s in self._sets.values()
                for index, card in enumerate(s.cards)
            }
            self._cards.sort(key=lambda card: order.get(card.id, 0))
            self._cards.sort(
                key=lambda card: (
                    (self._sets[card.set_id].release_date or "")
                    if card.set_id in self._sets
                    else ""
                ),
                reverse=True,
            )

    def _render_page(
        self,
        *,
        empty_message: str = "Aucune carte ne correspond à ces filtres.\nEssayez un autre nom ou réinitialisez la recherche.",
    ) -> None:
        table = self.query_one("#tcg_cards", DataTable)
        selected_id = self._selected.id if self._selected else None
        self._page = min(self._page, max(0, (len(self._cards) - 1) // self.PAGE_SIZE))
        start = self._page * self.PAGE_SIZE
        page = self._cards[start : start + self.PAGE_SIZE]
        with table.prevent(DataTable.RowHighlighted):
            table.clear()
            for card in page:
                self._add_card_row(table, card)
            row = next((i for i, card in enumerate(page) if card.id == selected_id), 0)
            table.move_cursor(row=row, column=0, animate=False)
        empty = self.query_one("#tcg_empty", Label)
        empty.update(empty_message)
        empty.display = not page
        table.display = bool(page)
        self.query_one("#tcg_count", Label).update(
            f"{len(self._cards):,} carte{'s' if len(self._cards) != 1 else ''}".replace(
                ",", " "
            )
        )
        self.query_one("#tcg_page", Label).update(
            f"Page {self._page + 1} / {max(1, (len(self._cards) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)}"
        )
        self.query_one("#tcg_previous", Button).disabled = self._page == 0
        self.query_one("#tcg_next", Button).disabled = start + self.PAGE_SIZE >= len(
            self._cards
        )
        self.query_one("#tcg_open_card", Button).disabled = not page
        self._select_card(page[row] if page else None)
        self.call_after_refresh(self._focus_on_show)

    def _add_card_row(self, table: DataTable[Text], card: Card) -> None:
        card_set = self._sets.get(card.set_id)
        table.add_row(
            Text(card.id),
            Text(card.name),
            Text(str(card.hp) if card.hp is not None else "—"),
            Text(" / ".join(card.types) or "—"),
            Text(card_set.name if card_set else card.set_id),
            Text(card.illustrator or "—"),
            key=card.id,
        )

    @on(Button.Pressed, "#tcg_previous")
    def previous_page(self) -> None:
        self._page = max(0, self._page - 1)
        self._render_page()

    @on(Button.Pressed, "#tcg_next")
    def next_page(self) -> None:
        self._page += 1
        self._render_page()

    @on(DataTable.RowHighlighted, "#tcg_cards")
    def highlight_card(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        index = self._page * self.PAGE_SIZE + event.cursor_row
        if index < len(self._cards):
            self._select_card(self._cards[index])

    def _select_card(self, card: Card | None) -> None:
        self._details_revision += 1
        self.workers.cancel_group(self, "tcg-details")
        if self._details_timer:
            self._details_timer.stop()
        self._selected = card
        self._display_card(card, loading=bool(card and not card.details_loaded))
        if card and not card.details_loaded:
            self._details_timer = self.set_timer(
                0.2, lambda: self._load_details(self._details_revision, card)
            )

    def _display_card(
        self, card: Card | None, *, loading: bool = False, error: str | None = None
    ) -> None:
        card_set = self._sets.get(card.set_id) if card else None
        serie = self._series.get(card_set.serie_id) if card_set else None
        self.query_one(TcgCardDetails).set_card(
            card, card_set, serie, loading=loading, error=error
        )

    @work(thread=True, exclusive=True, group="tcg-details", exit_on_error=False)
    def _load_details(self, revision: int, card: Card) -> None:
        worker = get_current_worker()
        try:
            detailed = tcg_library.fetch_card_details(card.id)
            error = None
        except TCGdexError, OSError, ValueError:
            detailed, error = (
                card,
                "Détails indisponibles. Vérifiez votre connexion puis réessayez.",
            )
        if not worker.is_cancelled:
            self.post_message(self.DetailsFinished(revision, detailed, error))

    @on(DetailsFinished)
    def details_finished(self, event: DetailsFinished) -> None:
        event.stop()
        if (
            event.revision != self._details_revision
            or not self._selected
            or event.card.id != self._selected.id
        ):
            return
        self._selected = event.card
        self._display_card(event.card, error=event.error)
        for index, card in enumerate(self._cards):
            if card.id == event.card.id:
                self._cards[index] = event.card
                break
        if event.error is None and self.query_one("#tcg_sort", Select).value in (
            "hp_asc",
            "hp_desc",
        ):
            self._sort_cards()
            selected_index = next(
                index
                for index, card in enumerate(self._cards)
                if card.id == event.card.id
            )
            self._page = selected_index // self.PAGE_SIZE
            self._render_page()
            return
        table = self.query_one("#tcg_cards", DataTable)
        if event.card.id in table.rows:
            table.update_cell(
                event.card.id,
                "hp",
                Text(str(event.card.hp) if event.card.hp is not None else "—"),
            )
            table.update_cell(
                event.card.id, "type", Text(" / ".join(event.card.types) or "—")
            )
            table.update_cell(
                event.card.id, "illustrator", Text(event.card.illustrator or "—")
            )

    @on(DataTable.RowSelected, "#tcg_cards")
    @on(Button.Pressed, "#tcg_open_card")
    def open_card(self) -> None:
        if self._selected:
            self.remove_class("catalogue-open")
            self.add_class("details-open")
            self.query_one(TcgCardDetails).focus()

    @on(TcgCardDetails.BackRequested)
    def close_details(self, event: TcgCardDetails.BackRequested) -> None:
        event.stop()
        self.action_focus_cards()

    @on(TcgCardDetails.RetryRequested)
    def retry_details(self, event: TcgCardDetails.RetryRequested) -> None:
        event.stop()
        self._select_card(self._selected)

    @on(Button.Pressed, "#tcg_retry")
    def retry_search(self) -> None:
        self._queue_search(immediate=True)

    @on(Button.Pressed, "#tcg_reset")
    def action_reset_filters(self) -> None:
        for field in self.query(Input):
            with field.prevent(Input.Changed):
                field.value = ""
        for identifier, value in (("tcg_type", ""), ("tcg_sort", "catalogue")):
            select = self.query_one(f"#{identifier}", Select)
            with select.prevent(Select.Changed):
                select.value = value
        self._scope = CatalogueScope()
        self.query_one("#tcg_catalogue", Tree).move_cursor(
            self._catalogue_nodes[self._scope]
        )
        self.remove_class("details-open", "catalogue-open", "filters-open")
        self._update_scope()
        self._queue_search(immediate=True)

    @on(Button.Pressed, "#tcg_browse")
    def action_focus_catalogue(self) -> None:
        self.remove_class("details-open", "filters-open")
        self.toggle_class("catalogue-open")
        if self.has_class("narrow") and not self.has_class("catalogue-open"):
            self.action_focus_cards()
        else:
            self.query_one("#tcg_catalogue", Tree).focus()

    @on(Button.Pressed, "#tcg_toggle_filters")
    def action_toggle_filters(self) -> None:
        self.remove_class("details-open", "catalogue-open")
        if self.has_class("short"):
            self.toggle_class("filters-open")
            if not self.has_class("filters-open"):
                self.action_focus_cards()
                return
        self.query_one("#tcg_hp", Input).focus()

    def action_focus_search(self) -> None:
        self.query_one("#tcg_name", Input).focus()

    def action_focus_cards(self) -> None:
        self.remove_class("details-open", "catalogue-open", "filters-open")
        if self._cards:
            self.query_one("#tcg_cards", DataTable).focus()
        else:
            self.query_one("#tcg_name", Input).focus()

    def on_unmount(self) -> None:
        self._ready = False
        if self._search_timer:
            self._search_timer.stop()
        if self._details_timer:
            self._details_timer.stop()

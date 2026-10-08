"""Booster shop, work clicker and persistent card collection."""

import random
import sqlite3
from functools import partial
from pathlib import Path
from tempfile import gettempdir
from time import monotonic
from typing import ClassVar, cast, override

from rich.text import Text
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.worker import Worker
from textual.worker import get_current_worker  # pyright: ignore[reportUnknownVariableType]
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    Select,
    TabbedContent,
    TabPane,
)

from pokenux.services.games.booster_simulator import (
    BoosterOffer,
    BoosterOpening,
    OwnedCard,
    SimulatorError,
    SimulatorService,
    SimulatorState,
    format_euros,
)
from pokenux.models.tcg.card import Card
from pokenux.services.games.booster_catalogue import (
    BoosterCatalogueError,
    load_booster_cards,
)
from pokenux.services.games.quiz import normalize_answer
from pokenux.services.games.tcg_quiz import card_image_url
from pokenux.textual.screens.simulator_card_screen import SimulatorCardScreen
from pokenux.textual.widgets.remote_image import RemoteImage


_JOBS = (
    "Colis préparé",
    "Rayon rangé",
    "Inventaire terminé",
    "Commande emballée",
    "Client accueilli",
    "Vitrine nettoyée",
)
_STORE_ERRORS = (SimulatorError, sqlite3.Error, OSError)


def money(amount: int) -> str:
    return format_euros(amount)


class SimulatorView(Vertical):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("w", "work", "Travailler"),
        Binding("r", "refresh_account", "Actualiser"),
    ]

    class CardsPrepared(Message):
        def __init__(
            self, set_id: str, generation: int, cards: list[Card], error: str = ""
        ) -> None:
            super().__init__()
            self.set_id: str = set_id
            self.generation: int = generation
            self.cards: list[Card] = cards
            self.error: str = error

    def __init__(self, service: SimulatorService | None = None) -> None:
        super().__init__()
        self._service: SimulatorService | None = service
        self._owns_service: bool = service is None
        self._state: SimulatorState | None = None
        self._offers: dict[str, BoosterOffer] = {}
        self._owned: tuple[OwnedCard, ...] = ()
        self._visible_owned_ids: set[str] = set()
        self._selected_owned: str | None = None
        self._opening: BoosterOpening | None = None
        self._revealed: int = 0
        self._new_cards: list[bool] = []
        self._ready: bool = False
        self._updating: bool = False
        self._art_revisions: dict[str, int] = {}
        self._art_keys: dict[str, str] = {}
        self._language: str = "fr"
        self._metadata_cache_path: Path | None = None
        self._loading_set: str | None = None
        self._metadata_generation: int = 0
        self._metadata_worker: Worker[None] | None = None
        self._metadata_errors: dict[str, str] = {}
        self._work_available_at: float = 0

    @override
    def compose(self) -> ComposeResult:
        yield Label("◈  BOOSTERS & COLLECTION", id="sim_heading")
        yield Label("Chargement du portefeuille…", id="sim_wallet", markup=False)
        yield Label(
            "Euros virtuels · Prix et probabilités estimés · Raretés du catalogue.",
            id="sim_note",
        )
        with TabbedContent(initial="sim_shop_tab", id="sim_sections"):
            with TabPane("Boutique", id="sim_shop_tab"):
                with Horizontal(id="sim_shop_filters"):
                    yield Input(
                        placeholder="Chercher une extension…", id="sim_offer_search"
                    )
                    yield Select[str](
                        [], prompt="Choisis une extension", id="sim_offer"
                    )
                yield Label("", id="sim_offer_info", markup=False)
                with Horizontal(id="sim_buy_actions"):
                    yield Button(
                        "Acheter & ouvrir",
                        id="sim_buy",
                        variant="primary",
                        disabled=True,
                    )
                    yield Button(
                        "Révéler une carte", id="sim_reveal_next", disabled=True
                    )
                    yield Button("Tout révéler", id="sim_reveal_all", disabled=True)
                yield Label(
                    "Choisis une extension et ouvre ton premier booster.",
                    id="sim_opening_status",
                    markup=False,
                )
                with VerticalScroll(id="sim_opening_panel"):
                    with Horizontal(id="sim_opening_layout"):
                        with Vertical(id="sim_opened_art"):
                            yield Label(
                                "◈\nBOOSTER\n\nLes cartes apparaîtront ici.",
                                classes="sim-art-placeholder",
                                markup=False,
                            )
                        with Vertical(id="sim_opened_list"):
                            yield DataTable[str | Text](
                                id="sim_opened_cards",
                                cursor_type="row",
                                zebra_stripes=True,
                                show_row_labels=False,
                            )
                            yield Label(
                                "Révèle les cartes. Entrée sur une ligne pour agrandir.",
                                id="sim_opened_info",
                                markup=False,
                            )
            with TabPane("Travail", id="sim_work_tab"):
                with VerticalScroll(id="sim_work_panel"):
                    yield Label("TON PETIT JOB AU MAGASIN", id="sim_work_title")
                    yield Label("", id="sim_work_info", markup=False)
                    yield Button(
                        "Travailler", id="sim_work", variant="success", disabled=True
                    )
                    yield Button("Se former", id="sim_upgrade", disabled=True)
                    yield Label("", id="sim_work_stats", markup=False)
                    yield Label(
                        "Une tâche toutes les 2 secondes ; les clics supplémentaires ne rapportent rien.\n"
                        + "Les formations augmentent le gain des prochains clics.\n"
                        + "Retourne en Boutique pour acheter des boosters.",
                        id="sim_work_tip",
                    )
            with TabPane("Collection", id="sim_collection_tab"):
                with Horizontal(id="sim_collection_filters"):
                    yield Input(
                        placeholder="Chercher une carte ou une extension…",
                        id="sim_collection_search",
                    )
                    yield Select[str](
                        [
                            ("Toutes les cartes", "all"),
                            ("Seulement les doublons", "duplicates"),
                        ],
                        value="all",
                        allow_blank=False,
                        id="sim_collection_filter",
                    )
                yield Label(
                    "Ta collection est vide. Ouvre un booster !",
                    id="sim_collection_stats",
                    markup=False,
                )
                with VerticalScroll(id="sim_collection_panel"):
                    with Horizontal(id="sim_collection_layout"):
                        yield DataTable[str | Text](
                            id="sim_collection",
                            cursor_type="row",
                            zebra_stripes=True,
                            show_row_labels=False,
                        )
                        with Vertical(id="sim_collection_art"):
                            yield Label(
                                "Sélectionne une carte pour voir son image.",
                                classes="sim-art-placeholder",
                                markup=False,
                            )
                yield Label("", id="sim_sale_info", markup=False)
                with Horizontal(id="sim_sale_actions"):
                    yield Button("Vendre 1", id="sim_sell_one", disabled=True)
                    yield Button(
                        "Vendre tous les exemplaires", id="sim_sell_all", disabled=True
                    )
                    yield Button(
                        "Vendre les doublons", id="sim_sell_duplicates", disabled=True
                    )
        yield Label("", id="sim_feedback", markup=False)

    def _table(self, selector: str) -> DataTable[str | Text]:
        return cast(DataTable[str | Text], self.query_one(selector, DataTable))

    def _picker(self, selector: str) -> Select[str]:
        return cast(Select[str], self.query_one(selector, Select))

    def on_mount(self) -> None:
        opened = self._table("#sim_opened_cards")
        for label, width in (
            ("N°", 3),
            ("Carte", 25),
            ("Rareté / finition", 26),
            ("Vente", 9),
            ("Découverte", 10),
        ):
            _ = opened.add_column(label, width=width)
        collection = self._table("#sim_collection")
        collection.fixed_columns = 1
        for label, width in (
            ("Carte", 25),
            ("Extension", 25),
            ("Rareté / finition", 26),
            ("Qté", 5),
            ("Vente / carte", 12),
        ):
            _ = collection.add_column(label, width=width)
        self._ready = True
        pane: TabPane | None = None
        for ancestor in self.ancestors:
            if isinstance(ancestor, TabPane):
                pane = ancestor
            elif isinstance(ancestor, TabbedContent) and pane is not None:
                self.watch(
                    ancestor,
                    "active",
                    partial(self._ancestor_tab_changed, pane.id),
                    init=False,
                )
                pane = None
        self.refresh_data()
        _ = self.set_interval(0.2, self._update_work_status)
        _ = self.call_after_refresh(self._focus_visible)

    def on_show(self) -> None:
        if self._ready:
            self.refresh_data()
            _ = self.call_after_refresh(self._focus_visible)

    def _ancestor_tab_changed(self, pane_id: str | None, active: str) -> None:
        if self._ready and active == pane_id:
            self.refresh_data()
            _ = self.call_after_refresh(self._focus_visible)

    def on_resize(self, event: events.Resize) -> None:
        _ = self.set_class(event.size.width < 95, "narrow")
        _ = self.set_class(event.size.height < 25, "short")

    def _focus_visible(self) -> None:
        if not self.is_attached or self.region.height <= 0:
            return
        section = self.query_one("#sim_sections", TabbedContent).active
        if section == "sim_work_tab":
            _ = self.query_one("#sim_work", Button).focus()
        elif section == "sim_collection_tab":
            _ = self._table("#sim_collection").focus()
        else:
            _ = self._picker("#sim_offer").focus()

    def _ensure_service(self) -> SimulatorService:
        if self._service is None:
            from pokenux.services import tcg_library, user_data

            if tcg_library.get_language_status().requested != user_data.get_tcg_lang():
                _ = tcg_library.set_language(user_data.get_tcg_lang())
            self._service = SimulatorService(tcg_library.series)
            self._language = tcg_library.get_language_status().active
            self._metadata_cache_path = user_data.path / "cache" / "boosters"
        if self._metadata_cache_path is None:
            database = self._service.db_path
            self._metadata_cache_path = (
                database.parent / "booster-cache"
                if isinstance(database, Path)
                else Path(gettempdir()) / "pokenux-booster-cache"
            )
        return self._service

    def refresh_data(self) -> None:
        if not self._ready or not self.is_attached:
            return
        try:
            service = self._ensure_service()
            self._state = state = service.snapshot()
            offers = {offer.set_id: offer for offer in service.extensions}
            if offers != self._offers:
                self._offers = offers
                self._fill_offer_picker()
            owned = tuple(service.collection())
        except _STORE_ERRORS as error:
            self._feedback(f"Sauvegarde indisponible : {error}", error=True)
            return
        self.query_one("#sim_wallet", Label).update(
            f"Solde : {money(state.balance)}  ·  Collection : {money(state.collection_value)}  ·  Boosters : {state.boosters_opened}"
        )
        self.query_one("#sim_work_info", Label).update(
            f"Formation niveau {state.work_level} · Salaire : {money(state.work_income)} par clic"
        )
        self._work_available_at = monotonic() + state.work_ready_in
        self._update_work_status()
        upgrade = self.query_one("#sim_upgrade", Button)
        upgrade.label = f"Formation · {money(state.upgrade_cost)}"
        upgrade.disabled = state.work_level >= 10 or state.balance < state.upgrade_cost
        if state.work_level >= 10:
            upgrade.label = "Formation maximale"
        self.query_one("#sim_work_stats", Label).update(
            f"{state.clicks} tâches accomplies · {state.boosters_opened} boosters ouverts · {state.cards_sold} cartes vendues"
        )
        if owned != self._owned:
            self._owned = owned
            self._render_collection()
        self.query_one("#sim_collection_stats", Label).update(
            f"{state.cards_owned} cartes · {len(owned)} références · Valeur de revente : {money(state.collection_value)}"
            if owned
            else "Ta collection est vide. Ouvre un booster !"
        )
        self.query_one("#sim_sell_duplicates", Button).disabled = not any(
            card.quantity > 1 for card in owned
        )
        self._update_offer()
        self._update_sale()
        if state.migration_notice and not str(
            self.query_one("#sim_feedback", Label).render()
        ):
            self._feedback(state.migration_notice)

    def _update_work_status(self) -> None:
        if not self._ready or not self.is_attached or self._state is None:
            return
        remaining = max(0.0, self._work_available_at - monotonic())
        button = self.query_one("#sim_work", Button)
        button.disabled = remaining > 0
        button.label = (
            f"Prochaine tâche · {remaining:.1f} s".replace(".", ",")
            if remaining
            else f"Travailler · +{money(self._state.work_income)}"
        )

    @on(Input.Changed, "#sim_offer_search")
    def search_offers(self) -> None:
        if self._ready:
            self._fill_offer_picker()

    def _fill_offer_picker(self) -> None:
        term = normalize_answer(self.query_one("#sim_offer_search", Input).value)
        offers = [
            offer
            for offer in self._offers.values()
            if term
            in normalize_answer(f"{offer.name} {offer.serie_name} {offer.set_id}")
        ]
        picker = self._picker("#sim_offer")
        selected = picker.value
        picker.set_options(
            [(f"{offer.name} · {money(offer.price)}", offer.set_id) for offer in offers]
        )
        picker.value = (
            selected
            if selected in {offer.set_id for offer in offers}
            else offers[0].set_id
            if offers
            else Select.NULL
        )
        self._update_offer()

    @on(Select.Changed, "#sim_offer")
    def offer_changed(self) -> None:
        if self._ready:
            self._update_offer()

    def _update_offer(self) -> None:
        offer = self._offers.get(str(self._picker("#sim_offer").value))
        buy = self.query_one("#sim_buy", Button)
        if self._loading_set is not None and (
            offer is None or offer.set_id != self._loading_set
        ):
            self._cancel_preparation()
        if offer is None or self._state is None:
            buy.disabled = True
            self.query_one("#sim_offer_info", Label).update(
                "Aucune extension disponible pour cette recherche."
            )
            return
        missing = max(0, offer.price - self._state.balance)
        service = self._service
        ready = service is not None and service.metadata_ready(offer.set_id)
        if ready and self._loading_set is not None:
            self._cancel_preparation()
        error = self._metadata_errors.get(offer.set_id)
        loading = self._loading_set == offer.set_id
        info = self.query_one("#sim_offer_info", Label)
        info.tooltip = f"{offer.composition}\n{offer.price_note}"
        info.update(
            f"{offer.serie_name} · {offer.card_count} cartes · {offer.available_cards} possibles · Prix estimé"
            + (
                f" · Il manque {money(missing)} : travaille pour gagner de l’argent."
                if missing
                else ""
            )
            + (
                " · Chargement des raretés…"
                if not ready and not error
                else f" · {error}"
                if error and not ready
                else ""
            )
        )
        buy.label = (
            f"Acheter & ouvrir · {money(offer.price)}"
            if ready
            else "Réessayer les données"
            if error and not loading
            else "Chargement des cartes…"
        )
        buy.disabled = bool(missing) if ready else loading or not error
        if not ready and not loading and not error and service is not None:
            self._loading_set = offer.set_id
            self._metadata_generation += 1
            self._metadata_worker = self._prepare_cards(
                offer.set_id, self._metadata_generation
            )

    def _cancel_preparation(self) -> None:
        self._metadata_generation += 1
        self._loading_set = None
        if self._metadata_worker is not None:
            self._metadata_worker.cancel()
            self._metadata_worker = None

    @work(thread=True, group="sim_metadata", exclusive=True, exit_on_error=False)
    def _prepare_cards(self, set_id: str, generation: int) -> None:
        worker = cast(Worker[None], get_current_worker())
        service = self._service
        if service is None or self._metadata_cache_path is None:
            return
        try:
            cards = load_booster_cards(
                self._language,
                set_id,
                service.cards_for_set(set_id),
                self._metadata_cache_path,
                cancelled=lambda: worker.is_cancelled,
            )
            result = self.CardsPrepared(set_id, generation, cards)
        except (BoosterCatalogueError, SimulatorError, OSError) as error:
            result = self.CardsPrepared(set_id, generation, [], str(error))
        if not worker.is_cancelled:
            _ = self.post_message(result)

    @on(CardsPrepared)
    def cards_prepared(self, event: CardsPrepared) -> None:
        _ = event.stop()
        if (
            not self._ready
            or self._service is None
            or event.generation != self._metadata_generation
        ):
            return
        if self._loading_set == event.set_id:
            self._loading_set = None
        error = event.error
        if not error:
            try:
                self._service.set_cards(event.set_id, event.cards)
                if not self._service.metadata_ready(event.set_id):
                    raise SimulatorError(
                        "Les données chargées ne permettent pas de respecter les emplacements de ce booster."
                    )
            except _STORE_ERRORS as failure:
                error = str(failure)
        if error:
            self._metadata_errors[event.set_id] = error
        else:
            _ = self._metadata_errors.pop(event.set_id, None)
        self.refresh_data()
        if error and str(self._picker("#sim_offer").value) == event.set_id:
            self._feedback(f"Raretés indisponibles : {error}", error=True)

    @on(Button.Pressed, "#sim_work")
    def action_work(self) -> None:
        if self._service is None:
            return
        try:
            result = self._service.work()
        except _STORE_ERRORS as error:
            self.refresh_data()
            self._feedback(str(error), error=True)
            return
        self.refresh_data()
        self._feedback(f"{random.choice(_JOBS)} : +{money(result.earned)} !")

    @on(Button.Pressed, "#sim_upgrade")
    def upgrade_work(self) -> None:
        if self._service is None:
            return
        try:
            state = self._service.upgrade_work()
        except _STORE_ERRORS as error:
            self._feedback(str(error), error=True)
            return
        self.refresh_data()
        self._feedback(
            f"Formation niveau {state.work_level} ! Tes prochains clics rapportent {money(state.work_income)}."
        )

    @on(Button.Pressed, "#sim_buy")
    def buy_booster(self) -> None:
        if self._service is None:
            return
        offer_id = str(self._picker("#sim_offer").value)
        if offer_id in self._offers and not self._service.metadata_ready(offer_id):
            _ = self._metadata_errors.pop(offer_id, None)
            self._update_offer()
            return
        try:
            previous = {
                card.card_id: card.quantity for card in self._service.collection()
            }
            opening = self._service.buy_and_open(offer_id)
        except _STORE_ERRORS as error:
            self._feedback(str(error), error=True)
            self.refresh_data()
            return
        self._opening = opening
        self._revealed = 0
        self._new_cards = []
        for card in opening.cards:
            self._new_cards.append(not previous.get(card.card_id, 0))
            previous[card.card_id] = previous.get(card.card_id, 0) + 1
        self.refresh_data()
        self._render_opening()
        self._feedback(
            f"Booster {opening.offer.name} acheté pour {money(opening.offer.price)}. Les cartes sont sauvegardées dans ta collection."
        )
        _ = self.query_one("#sim_reveal_next", Button).focus()

    @on(Button.Pressed, "#sim_reveal_next")
    def reveal_next(self) -> None:
        if self._opening and self._revealed < len(self._opening.cards):
            self._revealed += 1
            self._render_opening()

    @on(Button.Pressed, "#sim_reveal_all")
    def reveal_all(self) -> None:
        if self._opening:
            self._revealed = len(self._opening.cards)
            self._render_opening()

    def _render_opening(self) -> None:
        if self._opening is None:
            return
        opening = self._opening
        table = self._table("#sim_opened_cards")
        self._updating = True
        _ = table.clear()
        for index, card in enumerate(opening.cards[: self._revealed]):
            _ = table.add_row(
                str(index + 1),
                Text(card.name),
                Text(f"{card.rarity} · {card.finish}"),
                money(card.value),
                "Nouvelle" if self._new_cards[index] else "Doublon",
                key=str(index),
            )
        if self._revealed:
            table.move_cursor(row=self._revealed - 1, animate=False)
        self._updating = False
        finished = self._revealed == len(opening.cards)
        for identifier in ("sim_reveal_next", "sim_reveal_all"):
            self.query_one(f"#{identifier}", Button).disabled = finished
        self.query_one("#sim_opening_status", Label).update(
            f"{opening.offer.name} · {self._revealed} / {len(opening.cards)} cartes révélées"
            + (
                f" · Valeur de revente : {money(sum(card.value for card in opening.cards))}"
                if finished
                else ""
            )
        )
        if self._revealed:
            self._select_opened(self._revealed - 1)
        else:
            self.query_one("#sim_opened_info", Label).update(
                "Ton booster est prêt. Révèle ta première carte !"
            )
            _ = self.call_later(self._show_art, "sim_opened_art", None)

    @on(DataTable.RowHighlighted, "#sim_opened_cards")
    def highlight_opened(self, event: DataTable.RowHighlighted) -> None:
        _ = event.stop()
        if not self._updating and self._opening and event.row_key.value is not None:
            index = int(event.row_key.value)
            if index < self._revealed:
                self._select_opened(index)

    def _select_opened(self, index: int) -> None:
        if self._opening is None:
            return
        card = self._opening.cards[index]
        self.query_one("#sim_opened_info", Label).update(
            f"{card.name} · {card.rarity} · {card.finish} · {money(card.value)}"
            + (" · Nouvelle carte !" if self._new_cards[index] else " · Doublon")
        )
        _ = self.call_later(self._show_art, "sim_opened_art", card)

    @on(DataTable.RowSelected, "#sim_opened_cards")
    def preview_opened(self, event: DataTable.RowSelected) -> None:
        _ = event.stop()
        if self._opening and event.row_key.value is not None:
            index = int(event.row_key.value)
            if 0 <= index < self._revealed:
                app = cast(App[None], self.app)
                _ = app.push_screen(SimulatorCardScreen(self._opening.cards[index]))

    @on(DataTable.RowSelected, "#sim_collection")
    def preview_owned(self, event: DataTable.RowSelected) -> None:
        _ = event.stop()
        if event.row_key.value not in self._visible_owned_ids:
            return
        card = next(
            (card for card in self._owned if card.card_id == event.row_key.value), None
        )
        if card:
            app = cast(App[None], self.app)
            _ = app.push_screen(SimulatorCardScreen(card))

    @on(Input.Changed, "#sim_collection_search")
    @on(Select.Changed, "#sim_collection_filter")
    def filter_collection(self) -> None:
        if self._ready:
            self._render_collection()

    def _render_collection(self) -> None:
        term = normalize_answer(self.query_one("#sim_collection_search", Input).value)
        only_duplicates = self._picker("#sim_collection_filter").value == "duplicates"
        cards = [
            card
            for card in self._owned
            if term
            in normalize_answer(
                f"{card.name} {card.set_name} {card.card_id} {card.finish}"
            )
            and (not only_duplicates or card.quantity > 1)
        ]
        self._visible_owned_ids = {card.card_id for card in cards}
        table = self._table("#sim_collection")
        self._updating = True
        _ = table.clear()
        for card in cards:
            _ = table.add_row(
                Text(card.name),
                Text(card.set_name),
                Text(f"{card.rarity} · {card.finish}"),
                str(card.quantity),
                money(card.value),
                key=card.card_id,
            )
        self._selected_owned = (
            self._selected_owned
            if self._selected_owned in self._visible_owned_ids
            else cards[0].card_id
            if cards
            else None
        )
        if self._selected_owned:
            table.move_cursor(
                row=next(
                    i
                    for i, card in enumerate(cards)
                    if card.card_id == self._selected_owned
                ),
                animate=False,
            )
        self._updating = False
        self._update_sale()

    @on(DataTable.RowHighlighted, "#sim_collection")
    def highlight_owned(self, event: DataTable.RowHighlighted) -> None:
        _ = event.stop()
        if not self._updating and event.row_key.value in self._visible_owned_ids:
            self._selected_owned = event.row_key.value
            self._update_sale()

    def _update_sale(self) -> None:
        card = next(
            (card for card in self._owned if card.card_id == self._selected_owned), None
        )
        one = self.query_one("#sim_sell_one", Button)
        all_copies = self.query_one("#sim_sell_all", Button)
        one.disabled = all_copies.disabled = card is None
        if card:
            one.label = f"Vendre 1 · {money(card.value)}"
            all_copies.label = (
                f"Vendre les {card.quantity} · {money(card.quantity * card.value)}"
            )
            self.query_one("#sim_sale_info", Label).update(
                f"{card.name} · {card.finish} · {card.quantity} exemplaire(s) · {money(card.value)} par carte"
            )
        else:
            one.label = "Vendre 1"
            all_copies.label = "Vendre tous"
            self.query_one("#sim_sale_info", Label).update(
                "Sélectionne une carte pour la revendre. Les doublons conservent un exemplaire par carte."
            )
        _ = self.call_later(self._show_art, "sim_collection_art", card)

    @on(Button.Pressed, "#sim_sell_one")
    def sell_one(self) -> None:
        self._sell_selected(all_copies=False)

    @on(Button.Pressed, "#sim_sell_all")
    def sell_all(self) -> None:
        self._sell_selected(all_copies=True)

    def _sell_selected(self, *, all_copies: bool) -> None:
        if self._service is None or self._selected_owned is None:
            return
        try:
            card = next(
                (
                    card
                    for card in self._service.collection()
                    if card.card_id == self._selected_owned
                ),
                None,
            )
            if card is None:
                raise SimulatorError("Cette carte n’est plus dans ta collection.")
            quantity = card.quantity if all_copies else 1
            earned = self._service.sell(card.card_id, quantity)
        except _STORE_ERRORS as error:
            self._feedback(str(error), error=True)
            self.refresh_data()
            return
        self.refresh_data()
        self._feedback(f"{quantity} × {card.name} vendu(s) : +{money(earned)}.")

    @on(Button.Pressed, "#sim_sell_duplicates")
    def sell_duplicates(self) -> None:
        if self._service is None:
            return
        try:
            earned = self._service.sell_duplicates()
        except _STORE_ERRORS as error:
            self._feedback(str(error), error=True)
            return
        self.refresh_data()
        self._feedback(
            f"Doublons vendus : +{money(earned)}. Un exemplaire de chaque carte conservé."
            if earned
            else "Tu n’as aucun doublon à vendre."
        )

    async def _show_art(self, identifier: str, card: OwnedCard | None) -> None:
        if not self.is_attached:
            return
        key = f"{card.card_id}:{card.image}" if card else "empty"
        if self._art_keys.get(identifier) == key:
            return
        self._art_keys[identifier] = key
        revision = self._art_revisions[identifier] = (
            self._art_revisions.get(identifier, 0) + 1
        )
        slot = self.query_one(f"#{identifier}", Vertical)
        await slot.remove_children()
        if not self.is_attached or self._art_revisions.get(identifier) != revision:
            return
        image_url = card_image_url(card.image) if card else None
        if image_url:
            await slot.mount(
                RemoteImage(image_url, placeholder="Chargement de l’image…")
            )
        else:
            await slot.mount(
                Label(
                    "Image indisponible\nLa carte reste disponible hors ligne."
                    if card
                    else "◈\nRévèle ou sélectionne une carte.",
                    classes="sim-art-placeholder",
                    markup=False,
                )
            )

    @on(RemoteImage.Failed)
    def artwork_failed(self, event: RemoteImage.Failed) -> None:
        _ = event.stop()
        sender = event._sender  # pyright: ignore[reportPrivateUsage]
        if isinstance(sender, RemoteImage):
            for label in sender.query(Label):
                label.update(
                    "Image indisponible\nLa carte reste disponible hors ligne."
                )

    def action_refresh_account(self) -> None:
        self.refresh_data()

    def _feedback(self, message: str, *, error: bool = False) -> None:
        label = self.query_one("#sim_feedback", Label)
        label.update(message)
        _ = label.set_class(error, "sim-error")

    def on_unmount(self) -> None:
        self._ready = False
        self._cancel_preparation()
        self._art_revisions = {
            key: revision + 1 for key, revision in self._art_revisions.items()
        }
        if self._owns_service and self._service is not None:
            self._service.close()

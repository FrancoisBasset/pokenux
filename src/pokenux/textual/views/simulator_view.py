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
    finish_label,
    rarity_label,
)
from pokenux.services.localization import text
from pokenux.textual.utils import i18n, translator
from pokenux.textual.utils.navigation import is_active_view
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
    ("Colis préparé", "Parcel prepared"),
    ("Rayon rangé", "Shelf organised"),
    ("Inventaire terminé", "Inventory completed"),
    ("Commande emballée", "Order packed"),
    ("Client accueilli", "Customer welcomed"),
    ("Vitrine nettoyée", "Display cleaned"),
)
_STORE_ERRORS = (SimulatorError, sqlite3.Error, OSError)


def money(amount: int) -> str:
    return format_euros(amount)


class SimulatorView(Vertical):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("w", "work", text("Travailler", "Work")),
        Binding("r", "refresh_account", text("Actualiser", "Refresh")),
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
        self._catalogue_series: object = None
        self._metadata_cache_path: Path | None = None
        self._loading_set: str | None = None
        self._metadata_generation: int = 0
        self._metadata_worker: Worker[None] | None = None
        self._metadata_errors: dict[str, str] = {}
        self._work_available_at: float = 0

    @override
    def compose(self) -> ComposeResult:
        yield Label(
            text("◈  BOOSTERS & COLLECTION", "◈  BOOSTERS & COLLECTION"),
            id="sim_heading",
        )
        yield Label(
            text("Chargement du portefeuille…", "Loading your wallet…"),
            id="sim_wallet",
            markup=False,
        )
        yield Label(
            text(
                "Euros virtuels · Prix et probabilités estimés · Raretés du catalogue.",
                "Virtual euros · Estimated prices and odds · Catalogue rarities.",
            ),
            id="sim_note",
        )
        with TabbedContent(initial="sim_shop_tab", id="sim_sections"):
            with TabPane(text("Boutique", "Shop"), id="sim_shop_tab"):
                with Horizontal(id="sim_shop_filters"):
                    yield Input(
                        placeholder=text("Chercher une extension…", "Search sets…"),
                        id="sim_offer_search",
                    )
                    yield Select[str](
                        [],
                        prompt=text("Choisis une extension", "Choose a set"),
                        id="sim_offer",
                    )
                yield Label("", id="sim_offer_info", markup=False)
                with Horizontal(id="sim_buy_actions"):
                    yield Button(
                        text("Acheter & ouvrir", "Buy & open"),
                        id="sim_buy",
                        variant="primary",
                        disabled=True,
                    )
                    yield Button(
                        text("Révéler une carte", "Reveal a card"),
                        id="sim_reveal_next",
                        disabled=True,
                    )
                    yield Button(
                        text("Tout révéler", "Reveal all"),
                        id="sim_reveal_all",
                        disabled=True,
                    )
                yield Label(
                    text(
                        "Choisis une extension et ouvre ton premier booster.",
                        "Choose a set and open your first booster.",
                    ),
                    id="sim_opening_status",
                    markup=False,
                )
                with VerticalScroll(id="sim_opening_panel"):
                    with Horizontal(id="sim_opening_layout"):
                        with Vertical(id="sim_opened_art"):
                            yield Label(
                                text(
                                    "◈\nBOOSTER\n\nLes cartes apparaîtront ici.",
                                    "◈\nBOOSTER\n\nYour cards will appear here.",
                                ),
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
                                text(
                                    "Révèle les cartes. Entrée sur une ligne pour agrandir.",
                                    "Reveal your cards. Press Enter on a row to enlarge.",
                                ),
                                id="sim_opened_info",
                                markup=False,
                            )
            with TabPane(text("Travail", "Work"), id="sim_work_tab"):
                with VerticalScroll(id="sim_work_panel"):
                    yield Label(
                        text("TON PETIT JOB AU MAGASIN", "YOUR PART-TIME SHOP JOB"),
                        id="sim_work_title",
                    )
                    yield Label("", id="sim_work_info", markup=False)
                    yield Button(
                        text("Travailler", "Work"),
                        id="sim_work",
                        variant="success",
                        disabled=True,
                    )
                    yield Button(
                        text("Se former", "Train"), id="sim_upgrade", disabled=True
                    )
                    yield Label("", id="sim_work_stats", markup=False)
                    yield Label(
                        text(
                            "Une tâche toutes les 2 secondes ; les clics supplémentaires ne rapportent rien.\n",
                            "One task every 2 seconds; extra clicks earn nothing.\n",
                        )
                        + text(
                            "Les formations augmentent le gain des prochains clics.\n",
                            "Training increases earnings from future clicks.\n",
                        )
                        + text(
                            "Retourne en Boutique pour acheter des boosters.",
                            "Return to the Shop to buy boosters.",
                        ),
                        id="sim_work_tip",
                    )
            with TabPane(text("Collection", "Collection"), id="sim_collection_tab"):
                with Horizontal(id="sim_collection_filters"):
                    yield Input(
                        placeholder=text(
                            "Chercher une carte ou une extension…",
                            "Search cards or sets…",
                        ),
                        id="sim_collection_search",
                    )
                    yield Select[str](
                        [
                            (text("Toutes les cartes", "All cards"), "all"),
                            (
                                text("Seulement les doublons", "Duplicates only"),
                                "duplicates",
                            ),
                        ],
                        value="all",
                        allow_blank=False,
                        id="sim_collection_filter",
                    )
                yield Label(
                    text(
                        "Ta collection est vide. Ouvre un booster !",
                        "Your collection is empty. Open a booster!",
                    ),
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
                                text(
                                    "Sélectionne une carte pour voir son image.",
                                    "Select a card to see its artwork.",
                                ),
                                classes="sim-art-placeholder",
                                markup=False,
                            )
                yield Label("", id="sim_sale_info", markup=False)
                with Horizontal(id="sim_sale_actions"):
                    yield Button(
                        text("Vendre 1", "Sell 1"), id="sim_sell_one", disabled=True
                    )
                    yield Button(
                        text("Vendre tous les exemplaires", "Sell all copies"),
                        id="sim_sell_all",
                        disabled=True,
                    )
                    yield Button(
                        text("Vendre les doublons", "Sell duplicates"),
                        id="sim_sell_duplicates",
                        disabled=True,
                    )
        yield Label("", id="sim_feedback", markup=False)

    def refresh_language(self) -> None:
        if not self._ready:
            return
        translator.refresh_bindings(
            self,
            {
                "work": ("Travailler", "Work"),
                "refresh_account": ("Actualiser", "Refresh"),
            },
        )
        for identifier, pair in {
            "sim_heading": ("◈  BOOSTERS & COLLECTION", "◈  BOOSTERS & COLLECTION"),
            "sim_note": (
                "Euros virtuels · Prix et probabilités estimés · Raretés du catalogue.",
                "Virtual euros · Estimated prices and odds · Catalogue rarities.",
            ),
            "sim_work_title": ("TON PETIT JOB AU MAGASIN", "YOUR PART-TIME SHOP JOB"),
            "sim_work_tip": (
                "Une tâche toutes les 2 secondes ; les clics supplémentaires ne rapportent rien.\nLes formations augmentent le gain des prochains clics.\nRetourne en Boutique pour acheter des boosters.",
                "One task every 2 seconds; extra clicks earn nothing.\nTraining increases earnings from future clicks.\nReturn to the Shop to buy boosters.",
            ),
        }.items():
            self.query_one(f"#{identifier}", Label).update(text(*pair))
        for identifier, pair in {
            "sim_reveal_next": ("Révéler une carte", "Reveal a card"),
            "sim_reveal_all": ("Tout révéler", "Reveal all"),
            "sim_sell_duplicates": ("Vendre les doublons", "Sell duplicates"),
        }.items():
            self.query_one(f"#{identifier}", Button).label = text(*pair)
        self.query_one("#sim_offer_search", Input).placeholder = text(
            "Chercher une extension…", "Search sets…"
        )
        self.query_one("#sim_collection_search", Input).placeholder = text(
            "Chercher une carte ou une extension…", "Search cards or sets…"
        )
        self._picker("#sim_offer").prompt = text(
            "Choisis une extension", "Choose a set"
        )
        sections = self.query_one("#sim_sections", TabbedContent)
        for identifier, pair in {
            "sim_shop_tab": ("Boutique", "Shop"),
            "sim_work_tab": ("Travail", "Work"),
            "sim_collection_tab": ("Collection", "Collection"),
        }.items():
            sections.get_tab(identifier).label = text(*pair)
        picker = self._picker("#sim_collection_filter")
        choice = picker.value
        picker.set_options(
            [
                (text("Toutes les cartes", "All cards"), "all"),
                (text("Seulement les doublons", "Duplicates only"), "duplicates"),
            ]
        )
        picker.value = choice
        previous_row = self._table("#sim_opened_cards").cursor_row
        for selector, columns in (
            (
                "#sim_opened_cards",
                [
                    (text("N°", "No."), 3),
                    (text("Carte", "Card"), 25),
                    (text("Rareté / finition", "Rarity / finish"), 26),
                    (text("Vente", "Resale"), 9),
                    (text("Découverte", "Discovery"), 10),
                ],
            ),
            (
                "#sim_collection",
                [
                    (text("Carte", "Card"), 25),
                    (text("Extension", "Set"), 25),
                    (text("Rareté / finition", "Rarity / finish"), 26),
                    (text("Qté", "Qty"), 5),
                    (text("Vente / carte", "Resale / card"), 12),
                ],
            ),
        ):
            table = self._table(selector)
            table.clear(columns=True)
            for label, width in columns:
                table.add_column(label, width=width)
        self._owned = ()
        self.query_one("#sim_feedback", Label).update("")
        self.refresh_data()
        self._render_collection()
        if self._opening is not None:
            self._render_opening()
            if self._revealed:
                index = min(previous_row, self._revealed - 1)
                self._table("#sim_opened_cards").move_cursor(row=index, animate=False)
                self._select_opened(index)
        else:
            self.query_one("#sim_opening_status", Label).update(
                text(
                    "Choisis une extension et ouvre ton premier booster.",
                    "Choose a set and open your first booster.",
                )
            )
            self.query_one("#sim_opened_info", Label).update(
                text(
                    "Révèle les cartes. Entrée sur une ligne pour agrandir.",
                    "Reveal your cards. Press Enter on a row to enlarge.",
                )
            )
            self.call_later(self._show_art, "sim_opened_art", None)

    def _table(self, selector: str) -> DataTable[str | Text]:
        return cast(DataTable[str | Text], self.query_one(selector, DataTable))

    def _picker(self, selector: str) -> Select[str]:
        return cast(Select[str], self.query_one(selector, Select))

    def on_mount(self) -> None:
        opened = self._table("#sim_opened_cards")
        for label, width in (
            (text("N°", "No."), 3),
            (text("Carte", "Card"), 25),
            (text("Rareté / finition", "Rarity / finish"), 26),
            (text("Vente", "Resale"), 9),
            (text("Découverte", "Discovery"), 10),
        ):
            _ = opened.add_column(label, width=width)
        collection = self._table("#sim_collection")
        collection.fixed_columns = 1
        for label, width in (
            (text("Carte", "Card"), 25),
            (text("Extension", "Set"), 25),
            (text("Rareté / finition", "Rarity / finish"), 26),
            (text("Qté", "Qty"), 5),
            (text("Vente / carte", "Resale / card"), 12),
        ):
            _ = collection.add_column(label, width=width)
        self._ready = True
        translator.refresh_bindings(
            self,
            {
                "work": ("Travailler", "Work"),
                "refresh_account": ("Actualiser", "Refresh"),
            },
        )
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
        if not self.is_attached or self.region.height <= 0 or not is_active_view(self):
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
            self._catalogue_series = tcg_library.series
            self._metadata_cache_path = user_data.path / "cache" / "boosters"
        if self._owns_service:
            from pokenux.services import tcg_library

            if (
                self._language != tcg_library.get_language_status().active
                or self._catalogue_series is not tcg_library.series
            ):
                self._cancel_preparation()
                self._service.set_catalogue(tcg_library.series)
                self._catalogue_series = tcg_library.series
                self._language = tcg_library.get_language_status().active
                self._metadata_errors.clear()
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
            self._feedback(
                text(
                    f"Sauvegarde indisponible : {error}", f"Save unavailable: {error}"
                ),
                error=True,
            )
            return
        note = text(
            "Euros virtuels · Prix et probabilités estimés · Raretés du catalogue.",
            "Virtual euros · Estimated prices and odds · Catalogue rarities.",
        )
        if self._owns_service:
            from pokenux.services import tcg_library

            warning = tcg_library.get_language_status().warning
            if warning:
                note += " " + warning
        self.query_one("#sim_note", Label).update(note)
        self.query_one("#sim_wallet", Label).update(
            text(
                f"Solde : {money(state.balance)}  ·  Collection : {money(state.collection_value)}  ·  Boosters : {state.boosters_opened}",
                f"Balance: {money(state.balance)}  ·  Collection: {money(state.collection_value)}  ·  Boosters: {state.boosters_opened}",
            )
        )
        self.query_one("#sim_work_info", Label).update(
            text(
                f"Formation niveau {state.work_level} · Salaire : {money(state.work_income)} par clic",
                f"Training level {state.work_level} · Pay: {money(state.work_income)} per click",
            )
        )
        self._work_available_at = monotonic() + state.work_ready_in
        self._update_work_status()
        upgrade = self.query_one("#sim_upgrade", Button)
        upgrade.label = text(
            f"Formation · {money(state.upgrade_cost)}",
            f"Training · {money(state.upgrade_cost)}",
        )
        upgrade.disabled = state.work_level >= 10 or state.balance < state.upgrade_cost
        if state.work_level >= 10:
            upgrade.label = text("Formation maximale", "Training maxed out")
        self.query_one("#sim_work_stats", Label).update(
            text(
                f"{state.clicks} tâches accomplies · {state.boosters_opened} boosters ouverts · {state.cards_sold} cartes vendues",
                f"{state.clicks} tasks completed · {state.boosters_opened} boosters opened · {state.cards_sold} cards sold",
            )
        )
        if owned != self._owned:
            self._owned = owned
            self._render_collection()
        self.query_one("#sim_collection_stats", Label).update(
            text(
                f"{state.cards_owned} cartes · {len(owned)} références · Valeur de revente : {money(state.collection_value)}",
                f"{state.cards_owned} cards · {len(owned)} entries · Resale value: {money(state.collection_value)}",
            )
            if owned
            else text(
                "Ta collection est vide. Ouvre un booster !",
                "Your collection is empty. Open a booster!",
            )
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
            text(
                f"Prochaine tâche · {remaining:.1f} s", f"Next task · {remaining:.1f} s"
            ).replace(".", "," if i18n.get_language() == "fr" else ".")
            if remaining
            else text(
                f"Travailler · +{money(self._state.work_income)}",
                f"Work · +{money(self._state.work_income)}",
            )
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
                text(
                    "Aucune extension disponible pour cette recherche.",
                    "No sets match your search.",
                )
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
            text(
                f"{offer.serie_name} · {offer.card_count} cartes · {offer.available_cards} possibles · Prix estimé",
                f"{offer.serie_name} · {offer.card_count} cards · {offer.available_cards} available · Estimated price",
            )
            + (
                text(
                    f" · Il manque {money(missing)} : travaille pour gagner de l’argent.",
                    f" · You need {money(missing)} more: work to earn money.",
                )
                if missing
                else ""
            )
            + (
                text(" · Chargement des raretés…", " · Loading rarities…")
                if not ready and not error
                else f" · {error}"
                if error and not ready
                else ""
            )
        )
        buy.label = (
            text(
                f"Acheter & ouvrir · {money(offer.price)}",
                f"Buy & open · {money(offer.price)}",
            )
            if ready
            else text("Réessayer les données", "Retry card data")
            if error and not loading
            else text("Chargement des cartes…", "Loading cards…")
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
                        text(
                            "Les données chargées ne permettent pas de respecter les emplacements de ce booster.",
                            "The loaded data cannot fill this booster’s required slots.",
                        )
                    )
            except _STORE_ERRORS as failure:
                error = str(failure)
        if error:
            self._metadata_errors[event.set_id] = error
        else:
            _ = self._metadata_errors.pop(event.set_id, None)
        self.refresh_data()
        if error and str(self._picker("#sim_offer").value) == event.set_id:
            self._feedback(
                text(
                    f"Raretés indisponibles : {error}", f"Rarities unavailable: {error}"
                ),
                error=True,
            )

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
        self._feedback(f"{text(*random.choice(_JOBS))} : +{money(result.earned)} !")

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
            text(
                f"Formation niveau {state.work_level} ! Tes prochains clics rapportent {money(state.work_income)}.",
                f"Training level {state.work_level}! Your next clicks earn {money(state.work_income)}.",
            )
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
            text(
                f"Booster {opening.offer.name} acheté pour {money(opening.offer.price)}. Les cartes sont sauvegardées dans ta collection.",
                f"Bought a {opening.offer.name} booster for {money(opening.offer.price)}. The cards are saved in your collection.",
            )
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
        opening_name = self._offers.get(opening.offer.set_id, opening.offer).name
        table = self._table("#sim_opened_cards")
        self._updating = True
        _ = table.clear()
        for index, card in enumerate(opening.cards[: self._revealed]):
            if self._service is not None:
                card = self._service.display_card(card)
            _ = table.add_row(
                str(index + 1),
                Text(card.name),
                Text(f"{rarity_label(card.rarity)} · {finish_label(card.finish)}"),
                money(card.value),
                text("Nouvelle", "New")
                if self._new_cards[index]
                else text("Doublon", "Duplicate"),
                key=str(index),
            )
        if self._revealed:
            table.move_cursor(row=self._revealed - 1, animate=False)
        self._updating = False
        finished = self._revealed == len(opening.cards)
        for identifier in ("sim_reveal_next", "sim_reveal_all"):
            self.query_one(f"#{identifier}", Button).disabled = finished
        self.query_one("#sim_opening_status", Label).update(
            text(
                f"{opening_name} · {self._revealed} / {len(opening.cards)} cartes révélées",
                f"{opening_name} · {self._revealed} / {len(opening.cards)} cards revealed",
            )
            + (
                text(
                    f" · Valeur de revente : {money(sum(card.value for card in opening.cards))}",
                    f" · Resale value: {money(sum(card.value for card in opening.cards))}",
                )
                if finished
                else ""
            )
        )
        if self._revealed:
            self._select_opened(self._revealed - 1)
        else:
            self.query_one("#sim_opened_info", Label).update(
                text(
                    "Ton booster est prêt. Révèle ta première carte !",
                    "Your booster is ready. Reveal your first card!",
                )
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
        if self._service is not None:
            card = self._service.display_card(card)
        self.query_one("#sim_opened_info", Label).update(
            f"{card.name} · {rarity_label(card.rarity)} · {finish_label(card.finish)} · {money(card.value)}"
            + (
                text(" · Nouvelle carte !", " · New card!")
                if self._new_cards[index]
                else text(" · Doublon", " · Duplicate")
            )
        )
        _ = self.call_later(self._show_art, "sim_opened_art", card)

    @on(DataTable.RowSelected, "#sim_opened_cards")
    def preview_opened(self, event: DataTable.RowSelected) -> None:
        _ = event.stop()
        if self._opening and event.row_key.value is not None:
            index = int(event.row_key.value)
            if 0 <= index < self._revealed:
                app = cast(App[None], self.app)
                _ = app.push_screen(
                    SimulatorCardScreen(
                        self._service.display_card(self._opening.cards[index])
                        if self._service is not None
                        else self._opening.cards[index]
                    )
                )

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
                f"{card.name} {card.set_name} {card.card_id} {finish_label(card.finish)}"
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
                Text(f"{rarity_label(card.rarity)} · {finish_label(card.finish)}"),
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
            one.label = text(
                f"Vendre 1 · {money(card.value)}", f"Sell 1 · {money(card.value)}"
            )
            all_copies.label = text(
                f"Vendre les {card.quantity} · {money(card.quantity * card.value)}",
                f"Sell {card.quantity} · {money(card.quantity * card.value)}",
            )
            self.query_one("#sim_sale_info", Label).update(
                text(
                    f"{card.name} · {finish_label(card.finish)} · {card.quantity} exemplaire(s) · {money(card.value)} par carte",
                    f"{card.name} · {finish_label(card.finish)} · {card.quantity} copies · {money(card.value)} per card",
                )
            )
        else:
            one.label = text("Vendre 1", "Sell 1")
            all_copies.label = text("Vendre tous", "Sell all")
            self.query_one("#sim_sale_info", Label).update(
                text(
                    "Sélectionne une carte pour la revendre. Les doublons conservent un exemplaire par carte.",
                    "Select a card to sell. Selling duplicates keeps one copy of each card.",
                )
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
                raise SimulatorError(
                    text(
                        "Cette carte n’est plus dans ta collection.",
                        "This card is no longer in your collection.",
                    )
                )
            quantity = card.quantity if all_copies else 1
            earned = self._service.sell(card.card_id, quantity)
        except _STORE_ERRORS as error:
            self._feedback(str(error), error=True)
            self.refresh_data()
            return
        self.refresh_data()
        self._feedback(
            text(
                f"{quantity} × {card.name} vendu(s) : +{money(earned)}.",
                f"Sold {quantity} × {card.name}: +{money(earned)}.",
            )
        )

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
            text(
                f"Doublons vendus : +{money(earned)}. Un exemplaire de chaque carte conservé.",
                f"Duplicates sold: +{money(earned)}. Kept one copy of each card.",
            )
            if earned
            else text(
                "Tu n’as aucun doublon à vendre.", "You have no duplicates to sell."
            )
        )

    async def _show_art(self, identifier: str, card: OwnedCard | None) -> None:
        if not self.is_attached:
            return
        key = (
            f"{card.card_id}:{card.image}:{i18n.get_language()}"
            if card
            else f"empty:{i18n.get_language()}"
        )
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
                RemoteImage(
                    image_url,
                    placeholder=text("Chargement de l’image…", "Loading artwork…"),
                )
            )
        else:
            await slot.mount(
                Label(
                    text(
                        "Image indisponible\nLa carte reste disponible hors ligne.",
                        "Image unavailable\nThe card remains available offline.",
                    )
                    if card
                    else text(
                        "◈\nRévèle ou sélectionne une carte.",
                        "◈\nReveal or select a card.",
                    ),
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
                    text(
                        "Image indisponible\nLa carte reste disponible hors ligne.",
                        "Image unavailable\nThe card remains available offline.",
                    )
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

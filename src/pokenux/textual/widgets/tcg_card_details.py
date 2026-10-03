"""A scrollable card preview whose data is supplied by the TCG browser."""

from datetime import date
from typing import ClassVar, override
from urllib.parse import urlsplit, urlunsplit

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Button, Label

from pokenux.models.tcg.card import Card
from pokenux.models.tcg.serie import Serie
from pokenux.models.tcg.set import Set
from pokenux.textual.widgets.remote_image import RemoteImage


def _artwork_url(image: str) -> str | None:
    """TCGdex stores image roots; also accept an already complete asset URL."""
    if not image:
        return None
    url = urlsplit(image)
    path = url.path.rstrip("/")
    if not path.lower().endswith((".png", ".webp", ".jpg", ".jpeg", ".gif")):
        path += "/high.png"
    return urlunsplit((url.scheme, url.netloc, path, url.query, url.fragment))


def _release_date(value: str) -> str:
    try:
        return date.fromisoformat(value).strftime("%d/%m/%Y")
    except ValueError:
        return value or "Non renseignée"


class TcgCardDetails(VerticalScroll):
    """Show artwork and metadata without fetching card details in the UI thread."""

    can_focus: bool = True
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "back", "Retour aux cartes", show=False)
    ]
    _revision: reactive[int] = reactive(0, recompose=True)

    DEFAULT_CSS: str = """
    TcgCardDetails {
        height: 1fr;
        width: 1fr;
        border: round #334154;
        background: #09121c;
        color: #e3eaf3;
        padding: 0 1;
        scrollbar-size-vertical: 1;
    }

    TcgCardDetails:focus-within {
        border: round #5897ff;
    }

    TcgCardDetails .tcg-details-actions {
        height: 3;
        margin-bottom: 1;
    }

    TcgCardDetails Button {
        min-width: 12;
        height: 3;
        border: round #365d91;
        color: #5897ff;
        background: #0d1826;
    }

    TcgCardDetails Button:hover,
    TcgCardDetails Button:focus {
        color: #e3eaf3;
        border: round #5897ff;
        background: #142640;
    }

    TcgCardDetails #tcg_details_retry {
        width: 1fr;
        margin-bottom: 1;
    }

    TcgCardDetails .tcg-details-empty {
        height: auto;
        min-height: 10;
        width: 1fr;
        content-align: center middle;
        color: #8795a8;
    }

    TcgCardDetails .tcg-details-heading {
        height: auto;
        width: 1fr;
        color: #e3eaf3;
        text-style: bold;
    }

    TcgCardDetails .tcg-details-id {
        height: auto;
        width: 1fr;
        color: #d8b471;
        margin-bottom: 1;
    }

    TcgCardDetails .tcg-details-art {
        width: 1fr;
        height: 24;
        border: round #a17f40;
        background: #171b20;
        color: #d8b471;
        margin-bottom: 1;
    }

    TcgCardDetails .tcg-details-section {
        height: auto;
        margin-bottom: 1;
    }

    TcgCardDetails .tcg-details-section-title {
        height: 2;
        color: #d8b471;
        border-bottom: solid #263443;
        margin-bottom: 1;
        text-style: bold;
    }

    TcgCardDetails .tcg-details-row {
        height: auto;
        min-height: 2;
    }

    TcgCardDetails .tcg-details-label {
        width: 13;
        color: #8795a8;
    }

    TcgCardDetails .tcg-details-value {
        width: 1fr;
        height: auto;
    }

    TcgCardDetails .tcg-details-note {
        width: 1fr;
        height: auto;
        margin-bottom: 1;
        color: #8795a8;
    }

    TcgCardDetails .tcg-details-loading {
        color: #5897ff;
    }

    TcgCardDetails .tcg-details-error {
        color: #efb58c;
    }
    """

    class BackRequested(Message):
        """Return focus to the card list."""

    class RetryRequested(Message):
        """Ask the parent to retry loading the selected card's details."""

    def __init__(self, *, id: str | None = "tcg_card_details") -> None:
        super().__init__(id=id)
        self.card: Card | None = None
        self.card_set: Set | None = None
        self.serie: Serie | None = None
        self._loading: bool = False
        self._error: str | None = None

    def set_card(
        self,
        card: Card | None,
        card_set: Set | None = None,
        serie: Serie | None = None,
        *,
        loading: bool = False,
        error: str | None = None,
    ) -> None:
        """Update all displayed state together, leaving loading to the parent."""
        previous_id = self.card.id if self.card else None
        self.card = card
        self.card_set = card_set
        self.serie = serie
        self._loading = loading
        self._error = error
        self._revision += 1
        if previous_id != (card.id if card else None):
            self.scroll_home(animate=False)

    @staticmethod
    def _metadata(label: str, value: str | Text) -> Horizontal:
        return Horizontal(
            Label(label, classes="tcg-details-label", markup=False),
            Label(value, classes="tcg-details-value", markup=False),
            classes="tcg-details-row",
        )

    @override
    def compose(self) -> ComposeResult:
        with Horizontal(classes="tcg-details-actions"):
            yield Button("← Retour aux cartes", id="tcg_details_back")

        card = self.card
        if self._loading:
            yield Label(
                "Chargement des informations de la carte…",
                classes="tcg-details-note tcg-details-loading",
            )
        if self._error:
            yield Label(
                f"Informations indisponibles. {self._error}",
                classes="tcg-details-note tcg-details-error",
                markup=False,
            )
            yield Button("Réessayer", id="tcg_details_retry", disabled=self._loading)

        if card is None:
            if not self._loading and not self._error:
                yield Label(
                    "▤\n\nSélectionnez une carte\npour découvrir son illustration\net ses informations.",
                    classes="tcg-details-empty",
                )
            return

        yield Label(card.name, classes="tcg-details-heading", markup=False)
        card_id = card.id
        if card.local_id:
            card_id += f" · N° {card.local_id}"
        yield Label(card_id, classes="tcg-details-id", markup=False)
        yield RemoteImage(
            _artwork_url(card.image),
            classes="tcg-details-art",
            placeholder="▤\nIllustration indisponible",
        )

        with Vertical(classes="tcg-details-section"):
            yield Label("CARTE", classes="tcg-details-section-title")
            yield self._metadata(
                "PV / HP",
                Text(str(card.hp), style="#5897ff bold")
                if card.hp is not None
                else "Non renseignés",
            )
            yield self._metadata("Type", " / ".join(card.types) or "Non renseigné")
            yield self._metadata("Illustrateur", card.illustrator or "Non renseigné")
            if card.category:
                yield self._metadata("Catégorie", card.category)
            if card.rarity:
                yield self._metadata("Rareté", card.rarity)

        with Vertical(classes="tcg-details-section"):
            yield Label("COLLECTION", classes="tcg-details-section-title")
            yield self._metadata(
                "Série", self.serie.name if self.serie else "Non renseignée"
            )
            yield self._metadata(
                "Extension", self.card_set.name if self.card_set else card.set_id
            )
            if self.card_set:
                yield self._metadata(
                    "Sortie", _release_date(self.card_set.release_date)
                )
                if self.card_set.abbreviation:
                    yield self._metadata("Abréviation", self.card_set.abbreviation)

        if not card.details_loaded and not self._loading and not self._error:
            yield Label(
                "Les informations détaillées de cette carte ne sont pas disponibles.",
                classes="tcg-details-note",
            )

    def action_back(self) -> None:
        _ = self.post_message(self.BackRequested())

    @on(Button.Pressed, "#tcg_details_back")
    def _back(self, event: Button.Pressed) -> None:
        _ = event.stop()
        self.action_back()

    @on(Button.Pressed, "#tcg_details_retry")
    def _retry(self, event: Button.Pressed) -> None:
        _ = event.stop()
        _ = self.post_message(self.RetryRequested())

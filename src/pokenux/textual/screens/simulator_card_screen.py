"""Full-size artwork preview for a card in the booster simulator."""

from typing import ClassVar, override

from textual import on
from textual.events import Resize
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label

from pokenux.services.localization import text
from pokenux.textual.utils import translator
from pokenux.services.games.booster_simulator import (
    OwnedCard,
    format_euros,
    finish_label,
    rarity_label,
)
from pokenux.services.games.tcg_quiz import card_image_url
from pokenux.textual.widgets.remote_image import RemoteImage


class SimulatorCardScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", text("Fermer", "Close"))
    ]

    def __init__(self, card: OwnedCard) -> None:
        super().__init__()
        self.card: OwnedCard = card

    @override
    def compose(self) -> ComposeResult:
        with Vertical(id="sim_card_dialog"):
            yield Label(self.card.name, id="sim_card_title", markup=False)
            yield Label(
                text(
                    f"{self.card.set_name} · {rarity_label(self.card.rarity)} · {finish_label(self.card.finish)} · Vente : {format_euros(self.card.value)} par carte",
                    f"{self.card.set_name} · {rarity_label(self.card.rarity)} · {finish_label(self.card.finish)} · Resale: {format_euros(self.card.value)} per card",
                ),
                id="sim_card_meta",
                markup=False,
            )
            with Vertical(id="sim_card_image"):
                url = card_image_url(self.card.image)
                if url:
                    yield RemoteImage(
                        url,
                        placeholder=text("Chargement de l’image…", "Loading artwork…"),
                    )
                else:
                    yield Label(
                        text(
                            "Image indisponible hors ligne.",
                            "Image unavailable offline.",
                        ),
                        markup=False,
                    )
            yield Button(text("Fermer · Échap", "Close · Escape"), id="sim_card_close")

    def on_mount(self) -> None:
        self.refresh_language()
        _ = self.query_one("#sim_card_close", Button).focus()

    def refresh_language(self) -> None:
        translator.refresh_bindings(self, {"close": ("Fermer", "Close")})
        self.query_one("#sim_card_close", Button).label = text(
            "Fermer · Échap", "Close · Escape"
        )
        self.query_one("#sim_card_meta", Label).update(
            text(
                f"{self.card.set_name} · {rarity_label(self.card.rarity)} · {finish_label(self.card.finish)} · Vente : {format_euros(self.card.value)} par carte",
                f"{self.card.set_name} · {rarity_label(self.card.rarity)} · {finish_label(self.card.finish)} · Resale: {format_euros(self.card.value)} per card",
            )
        )

    def on_resize(self, event: Resize) -> None:
        _ = self.set_class(event.size.height < 30, "short")

    @on(Button.Pressed, "#sim_card_close")
    def action_close(self) -> None:
        _ = self.dismiss()

    @on(RemoteImage.Failed)
    def artwork_failed(self, event: RemoteImage.Failed) -> None:
        _ = event.stop()
        sender = event._sender  # pyright: ignore[reportPrivateUsage]
        if isinstance(sender, RemoteImage):
            for label in sender.query(Label):
                label.update(
                    text(
                        "Image indisponible\nLes informations de la carte restent disponibles.",
                        "Image unavailable\nCard information remains available.",
                    )
                )

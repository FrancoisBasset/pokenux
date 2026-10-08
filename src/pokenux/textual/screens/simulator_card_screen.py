"""Full-size artwork preview for a card in the booster simulator."""

from typing import ClassVar, override

from textual import on
from textual.events import Resize
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label

from pokenux.services.games.booster_simulator import OwnedCard, format_euros
from pokenux.services.games.tcg_quiz import card_image_url
from pokenux.textual.widgets.remote_image import RemoteImage


class SimulatorCardScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "close", "Fermer")]

    def __init__(self, card: OwnedCard) -> None:
        super().__init__()
        self.card: OwnedCard = card

    @override
    def compose(self) -> ComposeResult:
        with Vertical(id="sim_card_dialog"):
            yield Label(self.card.name, id="sim_card_title", markup=False)
            yield Label(
                f"{self.card.set_name} · {self.card.rarity} · {self.card.finish} · Vente : {format_euros(self.card.value)} par carte",
                id="sim_card_meta",
                markup=False,
            )
            with Vertical(id="sim_card_image"):
                url = card_image_url(self.card.image)
                if url:
                    yield RemoteImage(url, placeholder="Chargement de l’image…")
                else:
                    yield Label("Image indisponible hors ligne.", markup=False)
            yield Button("Fermer · Échap", id="sim_card_close")

    def on_mount(self) -> None:
        _ = self.query_one("#sim_card_close", Button).focus()

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
                    "Image indisponible\nLes informations de la carte restent disponibles."
                )

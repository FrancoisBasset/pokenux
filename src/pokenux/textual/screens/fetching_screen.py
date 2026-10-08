"""First-run catalogue setup with recoverable errors and download progress."""

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.worker import Worker, get_current_worker
from textual.widgets import Button, Label, ProgressBar

from pokenux.services import user_data
from pokenux.services.assets import AssetError, AssetManager, AssetProgress
from pokenux.services.localization import text
from pokenux.textual.utils.translator import refresh_bindings


class FetchingScreen(Screen[bool]):
    BINDINGS = [("q", "cancel", "Quit")]
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    FetchingScreen { align: center middle; background: #09121c; }
    #fetch_card {
        width: 72; max-width: 95%; height: auto; padding: 1 2;
        border: round #83b7ff; background: #101d2b;
    }
    #fetch_title { color: #efc47d; text-style: bold; margin-bottom: 1; }
    #fetch_intro, #fetch_detail, #fetch_error { width: 1fr; height: auto; margin-bottom: 1; }
    #fetch_error { color: #f28c91; }
    #fetch_progress { width: 1fr; margin: 1 0; }
    #fetch_actions { height: auto; align-horizontal: right; }
    #fetch_actions Button { margin-left: 1; }
    """

    class Progress(Message):
        def __init__(self, event: AssetProgress) -> None:
            super().__init__()
            self.event = event

    class Finished(Message):
        def __init__(self, success: bool, error: str = "") -> None:
            super().__init__()
            self.success = success
            self.error = error

    def __init__(self) -> None:
        super().__init__()
        self.fetch_worker: Worker[None] | None = None
        self._leaving = False

    def compose(self) -> ComposeResult:
        with Vertical(id="fetch_card"):
            yield Label(
                text("◒  PRÉPARONS TON AVENTURE", "◒  LET’S GET YOU STARTED"),
                id="fetch_title",
            )
            yield Label(
                text(
                    "Pokénux a besoin d’un catalogue pour démarrer. Les nouvelles éditions réunissent le Pokédex et les cartes en français et en anglais.",
                    "Pokénux needs a catalogue to get started. New editions include the Pokédex and cards in both French and English.",
                ),
                id="fetch_intro",
            )
            yield Label("", id="fetch_detail", markup=False)
            yield ProgressBar(total=None, show_eta=False, id="fetch_progress")
            yield Label("", id="fetch_error", markup=False)
            with Horizontal(id="fetch_actions"):
                yield Button(text("Quitter", "Quit"), id="fetch_cancel")
                yield Button(
                    text("Réessayer", "Retry"), id="fetch_retry", variant="primary"
                )

    def on_mount(self) -> None:
        refresh_bindings(self, {"cancel": ("Quitter", "Quit")})
        self.start_fetch()

    @on(Button.Pressed, "#fetch_retry")
    def start_fetch(self) -> None:
        if self.fetch_worker and self.fetch_worker.is_running:
            return
        self.query_one("#fetch_retry", Button).display = False
        self.query_one("#fetch_error", Label).update("")
        self.query_one("#fetch_detail", Label).update(
            text("Recherche du catalogue…", "Checking for a catalogue…")
        )
        self.query_one("#fetch_progress", ProgressBar).update(total=None, progress=0)
        self.fetch_worker = self.fetch()

    @work(thread=True, exclusive=True, exit_on_error=False)
    def fetch(self) -> None:
        worker = get_current_worker()
        try:
            finished = user_data.download_assets(
                cancelled=lambda: worker.is_cancelled,
                progress=lambda event: (
                    self.post_message(self.Progress(event))
                    if not worker.is_cancelled
                    else None
                ),
            )
            if not worker.is_cancelled:
                self.post_message(self.Finished(finished))
        except (AssetError, OSError, ValueError) as error:
            if not worker.is_cancelled:
                self.post_message(self.Finished(False, str(error)))

    @on(Progress)
    def update_progress(self, message: Progress) -> None:
        message.stop()
        if self._leaving:
            return
        stages = {
            "checking": ("Recherche du catalogue…", "Checking for a catalogue…"),
            "downloading": (
                "Téléchargement du catalogue…",
                "Downloading the catalogue…",
            ),
            "extracting": ("Extraction des données…", "Extracting data…"),
            "verifying": ("Vérification des fichiers…", "Verifying files…"),
            "activating": ("Installation du catalogue…", "Installing the catalogue…"),
        }
        self.query_one("#fetch_detail", Label).update(
            text(*stages.get(message.event.stage, stages["checking"]))
        )
        self.query_one("#fetch_progress", ProgressBar).update(
            total=message.event.total, progress=message.event.completed
        )

    @on(Finished)
    def fetch_finished(self, message: Finished) -> None:
        message.stop()
        if self._leaving:
            return
        if message.success:
            status = AssetManager(user_data.path).status()
            if status.legacy:
                self.app.notify(
                    text(
                        "Catalogue historique installé. Consulte les Paramètres pour les mises à jour FR/EN.",
                        "Legacy catalogue installed. Check Settings for FR/EN updates.",
                    ),
                    timeout=10,
                )
            self.dismiss(True)
        else:
            self.query_one("#fetch_error", Label).update(
                text(
                    "Le catalogue n’a pas pu être installé. Vérifie ta connexion et réessaie.\n{error}",
                    "The catalogue could not be installed. Check your connection and try again.\n{error}",
                    error=message.error,
                )
            )
            self.query_one("#fetch_progress", ProgressBar).update(total=1, progress=0)
            self.query_one("#fetch_retry", Button).display = True
            self.query_one("#fetch_retry", Button).focus()

    @on(Button.Pressed, "#fetch_cancel")
    def action_cancel(self) -> None:
        self._leaving = True
        if self.fetch_worker:
            self.fetch_worker.cancel()
        self.dismiss(False)

    def on_unmount(self) -> None:
        self._leaving = True
        if self.fetch_worker:
            self.fetch_worker.cancel()

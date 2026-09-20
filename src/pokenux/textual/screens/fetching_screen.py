from textual import work
from textual.app import ComposeResult
from textual.screen import Screen
from textual.worker import get_current_worker
from textual.widgets import Footer, Label, LoadingIndicator

from pokenux.services import user_data


class FetchingScreen(Screen[bool]):
    BINDINGS = [
        ("q", "cancel", "Quit"),
    ]

    ENABLE_COMMAND_PALETTE = False

    CSS = """
    FetchingScreen {
        align: center middle;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label(
            "It's the first time you run Pokenux, "
            "we need to fetch some data from the internet."
        )
        yield Label("Fetching data, please wait...")
        yield LoadingIndicator()
        yield Footer()

    def on_mount(self) -> None:
        self.fetch_worker = self.fetch()

    @work(thread=True)
    def fetch(self) -> None:
        worker = get_current_worker()

        finished = user_data.download_assets(
            cancelled=lambda: worker.is_cancelled,
        )

        if not finished:
            return

        self.app.call_from_thread(
            self.dismiss,
            True,
        )

    def action_cancel(self) -> None:
        self.fetch_worker.cancel()
        self.dismiss(False)

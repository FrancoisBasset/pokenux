from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Label


class QuizView(Container):
    def compose(self) -> ComposeResult:
        yield Label("Quiz view")

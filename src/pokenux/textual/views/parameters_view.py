from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Label, Select

from pokenux.textual.utils import i18n
from pokenux.services import user_data
from pokenux.textual.utils.enums import languages
from pokenux.textual.utils.translator import Translator


class ParametersView(Vertical):
    DEFAULT_CSS = """
    ParametersView,
    ParametersView > Vertical {
        height: auto;
        padding: 1 2;
    }
    """

    def on_mount(self):
        self.app_lang: Select = self.query_one("#app_lang", Select)
        if user_data.get_app_lang():
            self.app_lang.value = user_data.get_app_lang()

        self.tcg_lang: Select = self.query_one("#tcg_lang", Select)
        if user_data.get_tcg_lang():
            self.tcg_lang.value = user_data.get_tcg_lang()

        self.pokemon_lang: Select = self.query_one("#pokemon_lang", Select)
        if user_data.get_pokemon_lang():
            self.pokemon_lang.value = user_data.get_pokemon_lang()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(
                i18n.trans("application_language"),
                name="application_language",
                classes="i18n",
            )
            yield Select(languages, id="app_lang", allow_blank=True)

        with Vertical():
            yield Label(i18n.trans("tcg_language"), name="tcg_language", classes="i18n")
            yield Select(languages, id="tcg_lang", allow_blank=True)

        with Vertical():
            yield Label(
                i18n.trans("pokemon_language"), name="pokemon_language", classes="i18n"
            )
            yield Select(languages, id="pokemon_lang", allow_blank=True)
        yield Button(i18n.trans("save"), id="save_button", name="save", classes="i18n")

    @on(Button.Pressed, "#save_button")
    def on_save_button_pressed(self):
        user_data.set_app_lang(self.app_lang.value)
        user_data.set_tcg_lang(self.tcg_lang.value)
        user_data.set_pokemon_lang(self.pokemon_lang.value)
        user_data.save_config()

        i18n.set_language(self.app_lang.value)
        Translator(self.app).translate_app()

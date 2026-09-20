from textual.app import ComposeResult
from textual.widget import Widget
from textual_image.widget import Image

from pokenux.models.pokemon.pokemon import Pokemon
from pokenux.services.pokedex import Pokedex
from pokenux.services import user_data


class RandomPokemonWidget(Widget):
    DEFAULT_CSS = """
    RandomPokemonWidget {
        width: 100%;
        height: 5;
    }

    RandomPokemonWidget > Image {
        width: auto;
        height: 5;
    }
    """

    def compose(self) -> ComposeResult:
        pokemon: Pokemon = Pokedex().get_random_pokemon()

        yield Image(f"{user_data.path}/assets/images/pokemon/{pokemon.pokedex_id}.png")

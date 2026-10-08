"""Pokémon sprites with a dark backdrop for terminal image renderers."""

from typing import override

from PIL import Image as PILImage

from pokenux.textual.widgets.remote_image import RemoteImage


class PokemonArt(RemoteImage):
    @override
    def _prepare_image(self, image: PILImage.Image) -> PILImage.Image:
        # Half-cell renderers discard alpha. Composite it first so transparent
        # sprite margins do not turn into bright white rectangles in dark mode.
        background = PILImage.new("RGBA", image.size, "#111d2d")
        return PILImage.alpha_composite(background, image.convert("RGBA")).convert(
            "RGB"
        )

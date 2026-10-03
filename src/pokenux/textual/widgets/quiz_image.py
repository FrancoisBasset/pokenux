"""Quiz artwork, transformed in the downloader's worker before it is shown."""

from typing import override

from PIL import Image as PILImage
from PIL import ImageChops, ImageDraw, ImageFilter, ImageOps
from textual import on
from textual.app import ComposeResult
from textual.containers import Container
from textual.message import Message
from textual.widgets import Label
from textual_image.widget import Image

from pokenux.textual.widgets.remote_image import RemoteImage


_EFFECTS = frozenset({"normal", "blur", "pixelate", "shadow", "crop"})


def _silhouette(source: PILImage.Image) -> PILImage.Image:
    """Preserve transparency, removing a connected white background if needed."""
    image = source.convert("RGBA")
    alpha = image.getchannel("A")
    if alpha.getextrema() == (255, 255):
        # Some sprites have a white background. Only remove light pixels that
        # connect to an edge, keeping white details inside the Pokémon intact.
        red, green, blue, _ = image.split()
        light_pixels = [255 if value >= 245 else 0 for value in range(256)]
        # Pillow's point() overloads include an untyped transform parameter.
        red = red.point(light_pixels)  # pyright: ignore[reportUnknownMemberType]
        green = green.point(light_pixels)  # pyright: ignore[reportUnknownMemberType]
        blue = blue.point(light_pixels)  # pyright: ignore[reportUnknownMemberType]
        background = ImageChops.darker(ImageChops.darker(red, green), blue)
        width, height = image.size
        for x in range(width):
            for y in (0, height - 1):
                if background.getpixel((x, y)) == 255:
                    ImageDraw.floodfill(background, (x, y), 128)
        for y in range(height):
            for x in (0, width - 1):
                if background.getpixel((x, y)) == 255:
                    ImageDraw.floodfill(background, (x, y), 128)
        foreground = [0 if value == 128 else 255 for value in range(256)]
        alpha = background.point(foreground)  # pyright: ignore[reportUnknownMemberType]
    silhouette = PILImage.new("RGBA", image.size, (0, 0, 0, 0))
    silhouette.putalpha(alpha)
    return silhouette


def transform_quiz_image(source: PILImage.Image, effect: str) -> PILImage.Image:
    """Return a transformed copy; the shared download cache keeps the original."""
    if effect not in _EFFECTS:
        raise ValueError(f"Effet d’image inconnu : {effect}")
    image = ImageOps.exif_transpose(source).copy()
    if effect == "normal":
        return image
    if effect == "shadow":
        return _silhouette(image)
    if effect == "crop":
        width, height = image.size
        # A standard portrait card has its illustration below the name and HP.
        # Keep a central rectangle inside it, above attacks and descriptions.
        return image.crop(
            (
                round(width * 0.08),
                round(height * 0.18),
                max(round(width * 0.08) + 1, round(width * 0.92)),
                max(round(height * 0.18) + 1, round(height * 0.50)),
            )
        )
    if effect == "blur":
        # Blurring alpha as well as colors hides the outline of transparent art.
        return image.convert("RGBA").filter(
            ImageFilter.GaussianBlur(radius=max(2.0, min(image.size) / 18))
        )
    block_size = max(1, round(max(image.size) / 20))
    # The Pillow resize() stubs also permit an untyped size parameter.
    reduced = image.convert("RGBA").resize(  # pyright: ignore[reportUnknownMemberType]
        (max(1, image.width // block_size), max(1, image.height // block_size)),
        resample=PILImage.Resampling.BOX,
    )
    return reduced.resize(  # pyright: ignore[reportUnknownMemberType]
        image.size, resample=PILImage.Resampling.NEAREST
    )


class _ArtworkReady(Message):
    """Private artwork widget finished mounting its transformed image."""


class _QuizArtwork(RemoteImage):
    """Download and transform original artwork without emitting original pixels."""

    def __init__(self, url: str | None, effect: str, placeholder: str) -> None:
        super().__init__(url, placeholder=placeholder)
        self.effect: str = effect

    @override
    def _prepare_image(self, image: PILImage.Image) -> PILImage.Image:
        return transform_quiz_image(image, self.effect)

    @on(RemoteImage.Loaded)
    async def _show_quiz_image(self, message: RemoteImage.Loaded) -> None:
        _ = message.stop()
        _ = message.prevent_default()
        if self._unmounted or not self.is_attached:
            return
        await super()._show_image(message)
        if not self._unmounted and self.is_attached and self.query(Image):
            _ = self.post_message(_ArtworkReady())


class QuizImage(Container):
    """Display hidden artwork with success/failure signals safe for a quiz view."""

    DEFAULT_CSS: str = """
    QuizImage {
        align: center middle;
        overflow: hidden hidden;
    }

    QuizImage > RemoteImage {
        width: 1fr;
        height: 1fr;
    }
    """

    class Loaded(Message):
        """The transformed artwork is visible; no original image is exposed."""

    class Failed(Message):
        """The required artwork could not be downloaded, decoded, or displayed."""

    def __init__(
        self,
        url: str | None,
        effect: str = "normal",
        *,
        classes: str | None = None,
        placeholder: str = "Chargement de l’image…",
    ) -> None:
        if effect not in _EFFECTS:
            raise ValueError(f"Effet d’image inconnu : {effect}")
        super().__init__(classes=classes)
        self.url: str | None = url
        self.effect: str = effect
        self.placeholder: str = placeholder

    @override
    def compose(self) -> ComposeResult:
        yield _QuizArtwork(self.url, self.effect, self.placeholder)

    @on(_ArtworkReady)
    def _artwork_ready(self, message: _ArtworkReady) -> None:
        _ = message.stop()
        if self.is_attached:
            _ = self.post_message(self.Loaded())

    @on(RemoteImage.Failed)
    def _image_failed(self, message: RemoteImage.Failed) -> None:
        _ = message.stop()
        _ = message.prevent_default()
        self._report_failure()

    def _report_failure(self) -> None:
        if not self.is_attached:
            return
        for label in self.query(Label):
            label.update("Image indisponible")
        _ = self.post_message(self.Failed())

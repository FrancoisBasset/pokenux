"""Download remote artwork without blocking Textual's UI thread."""

from collections import OrderedDict
from io import BytesIO
from threading import BoundedSemaphore, Lock

import requests
from PIL import Image as PILImage
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Container
from textual.message import Message
from textual.worker import Worker, get_current_worker
from textual_image.widget import Image
from textual.widgets import Label


_CACHE: OrderedDict[str, bytes] = OrderedDict()
_CACHE_LOCK = Lock()
_DOWNLOAD_SLOTS = BoundedSemaphore(8)
_CACHE_ENTRIES = 128
_CACHE_BYTES = 64 * 1024 * 1024
_MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _cached(url: str) -> bytes | None:
    with _CACHE_LOCK:
        data = _CACHE.get(url)
        if data is not None:
            _CACHE.move_to_end(url)
        return data


def _remember(url: str, data: bytes) -> None:
    with _CACHE_LOCK:
        _CACHE[url] = data
        _CACHE.move_to_end(url)
        while (
            len(_CACHE) > _CACHE_ENTRIES
            or sum(map(len, _CACHE.values())) > _CACHE_BYTES
        ):
            _CACHE.popitem(last=False)


class RemoteImage(Container):
    """Display online artwork, keeping a placeholder when it is unavailable."""

    DEFAULT_CSS = """
    RemoteImage {
        align: center middle;
        overflow: hidden hidden;
    }

    RemoteImage > Image {
        width: auto;
        height: auto;
        max-width: 100%;
        max-height: 100%;
    }

    RemoteImage > Label {
        width: 1fr;
        height: 1fr;
        content-align: center middle;
    }
    """

    class Loaded(Message):
        """Carry a decoded image back to the widget's message loop."""

        def __init__(self, image: PILImage.Image) -> None:
            super().__init__()
            self.image = image

    class Failed(Message):
        """The image could not be displayed; the placeholder remains visible."""

    def _prepare_image(self, image: PILImage.Image) -> PILImage.Image:
        """Prepare decoded pixels in the download thread before rendering."""
        return image

    def __init__(
        self,
        url: str | None,
        *,
        classes: str | None = None,
        placeholder: str = "◒",
    ) -> None:
        super().__init__(classes=classes)
        self.url = url
        self.placeholder = placeholder
        self._download_worker: Worker[None] | None = None
        self._unmounted = False

    def compose(self) -> ComposeResult:
        yield Label(self.placeholder, markup=False)

    def on_mount(self) -> None:
        self._unmounted = False
        if self.url:
            self._download_worker = self._download(self.url)
        else:
            self.post_message(RemoteImage.Failed())

    def on_unmount(self) -> None:
        self._unmounted = True
        if self._download_worker is not None:
            self._download_worker.cancel()

    @work(thread=True, exit_on_error=False)
    def _download(self, url: str) -> None:
        worker = get_current_worker()
        data = _cached(url)
        try:
            if data is None:
                while not _DOWNLOAD_SLOTS.acquire(timeout=0.1):
                    if worker.is_cancelled:
                        return
                try:
                    if worker.is_cancelled:
                        return
                    # Another widget may have downloaded this URL while we waited.
                    data = _cached(url)
                    if data is None:
                        with requests.get(
                            url, timeout=(3, 10), stream=True
                        ) as response:
                            response.raise_for_status()
                            chunks = bytearray()
                            for chunk in response.iter_content(chunk_size=64 * 1024):
                                if worker.is_cancelled:
                                    return
                                chunks.extend(chunk)
                                if len(chunks) > _MAX_IMAGE_BYTES:
                                    self.post_message(RemoteImage.Failed())
                                    return
                            data = bytes(chunks)
                finally:
                    _DOWNLOAD_SLOTS.release()
            if worker.is_cancelled:
                return
            with PILImage.open(BytesIO(data)) as source:
                source.load()
                image = source.copy()
            if worker.is_cancelled or self._unmounted:
                return
            _remember(url, data)
            image = self._prepare_image(image)
            if not worker.is_cancelled and not self._unmounted:
                self.post_message(RemoteImage.Loaded(image))
        except (
            requests.RequestException,
            OSError,
            ValueError,
            PILImage.DecompressionBombError,
        ):
            if not worker.is_cancelled and not self._unmounted:
                self.post_message(RemoteImage.Failed())
            return

    @on(Loaded)
    async def _show_image(self, message: Loaded) -> None:
        message.stop()
        if self._unmounted or not self.is_attached:
            return
        try:
            image = Image(message.image)
        except OSError, ValueError:
            self.post_message(RemoteImage.Failed())
            return
        await self.remove_children()
        if not self._unmounted and self.is_attached:
            await self.mount(image)

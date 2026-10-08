"""Versioned catalogue installation, independent of the application release.

Network and hashing methods are synchronous: run them in a worker. ``status``
only inspects the manifest and required paths, making it suitable for the UI.
"""

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

from pokenux.services.localization import text

SCHEMA_VERSION = 1
REQUIRED_FILES = (
    "data/pokemon.json",
    "data/generations.json",
    "data/types.json",
    "data/tcg_fr.json",
    "data/tcg_en.json",
)
MANIFEST_NAME = "assets-manifest.json"
MANIFEST_URL = (
    "https://github.com/FrancoisBasset/pokenux/releases/download/"
    "assets-v1/assets-manifest.json"
)
LEGACY_URL = (
    "https://github.com/FrancoisBasset/pokenux/releases/download/1.0.0/pokenux-data.zip"
)
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_EXPANDED_BYTES = 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
CHUNK_SIZE = 1024 * 1024


class AssetError(RuntimeError):
    """An asset download or validation failed; existing data remains available."""


class _Cancelled(Exception):
    pass


@dataclass(frozen=True)
class AssetProgress:
    stage: str
    completed: int = 0
    total: int | None = None


@dataclass(frozen=True)
class AssetStatus:
    version: str | None = None
    schema_version: int | None = None
    languages: tuple[str, ...] = ()
    legacy: bool = False
    installed: bool = False


@dataclass(frozen=True)
class AssetFile:
    sha256: str
    size: int


@dataclass(frozen=True)
class AssetArchive:
    name: str
    url: str
    sha256: str
    size: int


@dataclass(frozen=True)
class AssetManifest:
    version: str
    schema_version: int
    languages: tuple[str, ...]
    archive: AssetArchive
    files: dict[str, AssetFile]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AssetManifest":
        try:
            if (
                type(data["schema_version"]) is not int
                or data["schema_version"] != SCHEMA_VERSION
            ):
                raise AssetError("This catalogue requires a newer application.")
            version_tuple(data["version"])
            if not isinstance(data["languages"], list) or sorted(data["languages"]) != [
                "en",
                "fr",
            ]:
                raise AssetError(
                    "A versioned catalogue must contain French and English."
                )
            archive = AssetArchive(**data["archive"])
            if (
                "/" in archive.name
                or "\\" in archive.name
                or not archive.name.endswith(".zip")
            ):
                raise AssetError("Invalid archive name.")
            _https_url(archive.url)
            _digest_and_size(archive.sha256, archive.size, MAX_ARCHIVE_BYTES)
            files = {}
            for name, metadata in data["files"].items():
                _safe_path(name)
                if not name.startswith("data/") or not name.endswith(".json"):
                    raise AssetError(
                        "Only catalogue JSON files belong in a versioned bundle."
                    )
                item = AssetFile(**metadata)
                _digest_and_size(item.sha256, item.size, MAX_EXPANDED_BYTES)
                files[name] = item
            if not set(REQUIRED_FILES).issubset(files):
                raise AssetError("The manifest is missing required catalogues.")
            if sum(item.size for item in files.values()) > MAX_EXPANDED_BYTES:
                raise AssetError("The catalogue is too large.")
            return cls(data["version"], SCHEMA_VERSION, ("fr", "en"), archive, files)
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise AssetError("Invalid asset manifest.") from error

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "version": self.version,
            "languages": list(self.languages),
            "archive": vars(self.archive),
            "files": {name: vars(item) for name, item in self.files.items()},
        }


def version_tuple(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not re.fullmatch(
        r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value
    ):
        raise AssetError("Asset versions must use MAJOR.MINOR.PATCH.")
    major, minor, patch = (int(part) for part in value.split("."))
    return major, minor, patch


def _https_url(url: str) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        raise AssetError("Asset downloads require an HTTPS URL.")


def _digest_and_size(digest: str, size: int, limit: int) -> None:
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise AssetError("Invalid SHA-256 digest.")
    if type(size) is not int or size <= 0 or size > limit:
        raise AssetError("Invalid catalogue size.")


def _safe_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or "\x00" in name
        or path.is_absolute()
        or ".." in path.parts
        or ":" in name
        or str(path) != name
    ):
        raise AssetError("Unsafe path in asset archive.")
    return path


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_catalogues(root: Path, *, bilingual: bool = True) -> tuple[str, ...]:
    """Validate JSON and model compatibility before promoting an installation."""
    from pokenux.models.pokemon.pokemon import Pokemon
    from pokenux.models.tcg.serie import Serie

    try:

        def read(name):
            value = json.loads((root / "data" / name).read_text(encoding="utf-8"))
            if not isinstance(value, list) or not value:
                raise AssetError(f"Empty or invalid catalogue: {name}")
            return value

        pokemon = read("pokemon.json")
        for entry in pokemon:
            if not isinstance(entry.get("types"), list):
                raise AssetError(
                    "Pokémon types must retain their model-compatible list format."
                )
            if bilingual and not all(
                entry.get("name", {}).get(lang) for lang in ("fr", "en")
            ):
                raise AssetError("Missing French or English Pokémon names.")
            Pokemon.from_dict(entry)
        if any(not str(value).isdigit() for value in read("generations.json")):
            raise AssetError("Invalid generation catalogue.")
        if any(not item.get("fr") or not item.get("en") for item in read("types.json")):
            raise AssetError("Missing French or English Pokémon types.")
        languages = tuple(
            lang
            for lang in ("fr", "en")
            if (root / "data" / f"tcg_{lang}.json").is_file()
        )
        if not languages or (bilingual and len(languages) != 2):
            raise AssetError("Missing French or English TCG catalogue.")
        for lang in languages:
            for entry in read(f"tcg_{lang}.json"):
                Serie.from_dict(entry)
        return languages
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        raise AssetError(
            "The catalogue contains invalid or incompatible data."
        ) from error


class AssetManager:
    def __init__(
        self, data_root: Path, *, manifest_url: str = MANIFEST_URL, opener=None
    ):
        self.data_root = Path(data_root)
        self.manifest_url = manifest_url
        self._opener = opener or urlopen

    @property
    def active_path(self) -> Path:
        return self.data_root / "assets"

    @property
    def _previous_path(self) -> Path:
        return self.data_root / ".assets-previous"

    def status(self) -> AssetStatus:
        root = self.active_path
        installed = all((root / name).is_file() for name in REQUIRED_FILES[:3])
        languages = tuple(
            lang
            for lang in ("fr", "en")
            if (root / "data" / f"tcg_{lang}.json").is_file()
        )
        metadata = root / MANIFEST_NAME
        if metadata.is_file():
            try:
                manifest = AssetManifest.from_dict(
                    json.loads(metadata.read_text(encoding="utf-8"))
                )
                complete = all((root / name).is_file() for name in manifest.files)
                return AssetStatus(
                    manifest.version,
                    manifest.schema_version,
                    languages,
                    False,
                    complete,
                )
            except AssetError, OSError, ValueError:
                return AssetStatus(languages=languages)
        return AssetStatus(
            languages=languages,
            legacy=installed and bool(languages),
            installed=installed and bool(languages),
        )

    def _open(self, url: str):
        _https_url(url)
        response = self._opener(
            Request(url, headers={"User-Agent": "Pokenux-assets/1"}), timeout=20
        )
        # urllib follows redirects: a HTTPS origin must not redirect to plaintext.
        if hasattr(response, "geturl"):
            _https_url(response.geturl())
        return response

    @staticmethod
    def _checkpoint(cancelled):
        if cancelled():
            raise _Cancelled

    def _manifest(self, cancelled) -> AssetManifest | None:
        self._checkpoint(cancelled)
        try:
            with self._open(self.manifest_url) as response:
                raw = response.read(MAX_MANIFEST_BYTES + 1)
            self._checkpoint(cancelled)
            if len(raw) > MAX_MANIFEST_BYTES:
                raise AssetError("Asset manifest is too large.")
            return AssetManifest.from_dict(json.loads(raw))
        except HTTPError as error:
            if error.code == 404:
                return None
            raise

    def check_update(
        self, cancelled: Callable[[], bool] = lambda: False
    ) -> AssetManifest | None:
        try:
            manifest = self._manifest(cancelled)
            current = self.status()
            if manifest and current.version and current.installed:
                if version_tuple(manifest.version) <= version_tuple(current.version):
                    return None
            return manifest
        except _Cancelled:
            return None
        except (OSError, URLError, ValueError) as error:
            raise AssetError(
                text(
                    "Impossible de rechercher les mises à jour du catalogue.",
                    "Unable to check for catalogue updates.",
                )
            ) from error

    @contextmanager
    def _lock(self):
        import fcntl

        self.data_root.mkdir(parents=True, exist_ok=True)
        with (self.data_root / ".assets-update.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise AssetError(
                    text(
                        "Une mise à jour du catalogue est déjà en cours.",
                        "Another catalogue update is already running.",
                    )
                ) from error
            try:
                # Recover an interrupted promotion, before starting another one.
                if not self.active_path.exists() and self._previous_path.exists():
                    self._previous_path.rename(self.active_path)
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _download(
        self, url, target, cancelled, progress, expected: AssetArchive | None = None
    ):
        self._checkpoint(cancelled)
        digest = hashlib.sha256()
        completed = 0
        with self._open(url) as response, target.open("wb") as output:
            header = response.headers.get("Content-Length")
            total = (
                expected.size
                if expected
                else (int(header) if header and header.isdigit() else None)
            )
            if total and total > MAX_ARCHIVE_BYTES:
                raise AssetError("Asset archive is too large.")
            progress(AssetProgress("downloading", 0, total))
            while chunk := response.read(CHUNK_SIZE):
                self._checkpoint(cancelled)
                completed += len(chunk)
                if completed > MAX_ARCHIVE_BYTES or (
                    expected and completed > expected.size
                ):
                    raise AssetError("The archive size does not match its manifest.")
                output.write(chunk)
                digest.update(chunk)
                progress(AssetProgress("downloading", completed, total))
        self._checkpoint(cancelled)
        if expected and (
            completed != expected.size or digest.hexdigest() != expected.sha256
        ):
            raise AssetError("The downloaded archive failed SHA-256 verification.")

    def _extract(self, archive_path, destination, cancelled, progress, manifest=None):
        with ZipFile(archive_path) as archive:
            members = archive.infolist()
            if (
                len(members) > 20000
                or sum(item.file_size for item in members) > MAX_EXPANDED_BYTES
            ):
                raise AssetError("Asset archive exceeds extraction limits.")
            # The legacy URL has served both data/ and assets/data/ bundles.
            # Select one layout for the entire archive so mixed roots cannot
            # overwrite the same destination after removing the wrapper.
            legacy_prefix = ""
            if manifest is None:
                if all(item.filename.startswith("assets/") for item in members):
                    legacy_prefix = "assets/"
                elif not all(item.filename.startswith("data/") for item in members):
                    raise AssetError(
                        text(
                            "L’archive historique doit contenir un dossier data/ ou assets/.",
                            "The legacy archive must contain a data/ or assets/ directory.",
                        )
                    )
            seen = set()
            for index, item in enumerate(members):
                self._checkpoint(cancelled)
                raw = item.filename[:-1] if item.is_dir() else item.filename
                _safe_path(raw)
                mode = item.external_attr >> 16
                if stat.S_ISLNK(mode) or (
                    stat.S_IFMT(mode) and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode))
                ):
                    raise AssetError(
                        "Links and special files are forbidden in asset archives."
                    )
                if raw in seen:
                    raise AssetError("Duplicate file in asset archive.")
                seen.add(raw)
                name = raw
                if manifest is None and legacy_prefix:
                    if raw == "assets" and item.is_dir():
                        continue
                    name = raw.removeprefix(legacy_prefix)
                if item.is_dir():
                    continue
                if manifest and (
                    name not in manifest.files
                    or item.file_size != manifest.files[name].size
                ):
                    raise AssetError("Unexpected file or size in the asset archive.")
                target = destination / _safe_path(name)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, target.open("xb") as output:
                    while chunk := source.read(CHUNK_SIZE):
                        self._checkpoint(cancelled)
                        output.write(chunk)
                progress(AssetProgress("extracting", index + 1, len(members)))

    def _verify(self, destination, manifest, cancelled, progress):
        if manifest:
            for index, (name, expected) in enumerate(manifest.files.items()):
                self._checkpoint(cancelled)
                candidate = destination / name
                if (
                    not candidate.is_file()
                    or candidate.stat().st_size != expected.size
                    or file_sha256(candidate) != expected.sha256
                ):
                    raise AssetError(f"Catalogue checksum mismatch: {name}")
                progress(AssetProgress("verifying", index + 1, len(manifest.files)))
        validate_catalogues(destination, bilingual=manifest is not None)
        self._checkpoint(cancelled)

    def _activate(self, staged):
        previous = self._previous_path
        if previous.exists():
            shutil.rmtree(previous)
        moved = self.active_path.exists()
        if moved:
            self.active_path.rename(previous)
        try:
            staged.rename(self.active_path)
        except BaseException:
            if moved:
                previous.rename(self.active_path)
            raise

    def _install(self, manifest, cancelled, progress):
        with (
            self._lock(),
            tempfile.TemporaryDirectory(
                prefix=".assets-staging-", dir=self.data_root
            ) as temporary,
        ):
            scratch = Path(temporary)
            archive = scratch / "download.zip"
            staged = scratch / "assets"
            staged.mkdir()
            self._download(
                manifest.archive.url if manifest else LEGACY_URL,
                archive,
                cancelled,
                progress,
                manifest.archive if manifest else None,
            )
            self._extract(archive, staged, cancelled, progress, manifest)
            self._verify(staged, manifest, cancelled, progress)
            if manifest:
                (staged / MANIFEST_NAME).write_text(
                    json.dumps(manifest.to_dict(), indent=2) + "\n", encoding="utf-8"
                )
            self._checkpoint(cancelled)
            progress(AssetProgress("activating", 0, 1))
            self._checkpoint(cancelled)
            self._activate(staged)
            progress(AssetProgress("activating", 1, 1))
        return True

    def install(
        self,
        manifest: AssetManifest,
        *,
        cancelled: Callable[[], bool] = lambda: False,
        progress: Callable[[AssetProgress], None] = lambda _event: None,
    ) -> bool:
        try:
            # Validate callers constructing dataclasses directly, too.
            manifest = AssetManifest.from_dict(manifest.to_dict())
            return self._install(manifest, cancelled, progress)
        except _Cancelled:
            return False
        except (OSError, URLError, BadZipFile, ValueError) as error:
            raise AssetError(
                text(
                    "Impossible d’installer le catalogue ; les données existantes sont conservées.",
                    "Unable to install the catalogue; existing data was preserved.",
                )
            ) from error

    def bootstrap(
        self,
        *,
        cancelled: Callable[[], bool] = lambda: False,
        progress: Callable[[AssetProgress], None] = lambda _event: None,
    ) -> bool:
        """Use the legacy archive only while the versioned channel is unpublished."""
        try:
            with self._lock():
                if self.status().installed:
                    return True
            progress(AssetProgress("checking"))
            manifest = self._manifest(cancelled)
            return self._install(manifest, cancelled, progress)
        except _Cancelled:
            return False
        except (OSError, URLError, BadZipFile, ValueError) as error:
            raise AssetError(
                text(
                    "Impossible de télécharger le catalogue ; veuillez réessayer.",
                    "Unable to download the catalogue; please retry.",
                )
            ) from error

    def rollback(self) -> bool:
        """Restore the previous installation; preserve the current one as backup."""
        try:
            with self._lock():
                previous = self._previous_path
                if not previous.exists():
                    return False
                metadata = previous / MANIFEST_NAME
                manifest = (
                    AssetManifest.from_dict(json.loads(metadata.read_text()))
                    if metadata.is_file()
                    else None
                )
                self._verify(previous, manifest, lambda: False, lambda _event: None)
                displaced = self.data_root / ".assets-rollback"
                if displaced.exists():
                    shutil.rmtree(displaced)
                self.active_path.rename(displaced)
                try:
                    previous.rename(self.active_path)
                except BaseException:
                    displaced.rename(self.active_path)
                    raise
                displaced.rename(previous)
            return True
        except (OSError, ValueError) as error:
            raise AssetError(
                text(
                    "Impossible de restaurer le catalogue précédent.",
                    "Unable to restore the previous catalogue.",
                )
            ) from error

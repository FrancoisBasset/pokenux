"""Check that Python distributions include the UI resources and exclude game data."""

from pathlib import Path
import sys
import tarfile
import zipfile

CSS = {
    f"pokenux/textual/css/{name}.css"
    for name in (
        "style",
        "new_view",
        "pokedex_view",
        "tcg_view",
        "quiz_view",
        "simulator_view",
    )
}
REQUIRED = CSS | {
    "pokenux/__main__.py",
    "pokenux/locales/en/LC_MESSAGES/pokenux.mo",
    "pokenux/locales/fr/LC_MESSAGES/pokenux.mo",
}


def check(path: Path) -> None:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
    elif path.name.endswith(".tar.gz"):
        with tarfile.open(path) as archive:
            names = {
                name.split("/", 1)[1] for name in archive.getnames() if "/" in name
            }
        required_sources = {
            "PKGBUILD",
            "packaging",
            "scripts",
            "uv.lock",
            "CHANGELOG.md",
            ".python-version",
        }
        present_roots = {name.split("/", 1)[0] for name in names}
        missing = required_sources - present_roots
        if missing:
            raise ValueError(f"{path.name}: missing source files: {sorted(missing)}")
        names = {name.removeprefix("src/") for name in names}
    else:
        raise ValueError(f"Not a Python distribution: {path}")
    missing = REQUIRED - names
    if missing:
        raise ValueError(f"{path.name}: missing runtime resources: {sorted(missing)}")
    if any(name.startswith("pokenux/assets/") for name in names):
        raise ValueError(f"{path.name}: downloaded game data must not be bundled")
    print(f"{path.name}: resources and distribution contents OK")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(
            "Usage: python scripts/check_dist.py dist/*.whl dist/pokenux-VERSION.tar.gz"
        )
    try:
        for argument in sys.argv[1:]:
            check(Path(argument))
    except (OSError, ValueError, zipfile.BadZipFile, tarfile.TarError) as error:
        raise SystemExit(str(error)) from error

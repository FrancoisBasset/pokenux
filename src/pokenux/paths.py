"""User-data paths and catalogue checks without filesystem mutations."""

import os
from pathlib import Path


def data_directory() -> Path:
    """Honor an absolute XDG data root, keeping existing default installations."""
    configured = os.environ.get("XDG_DATA_HOME")
    if configured and Path(configured).is_absolute():
        return Path(configured) / "pokenux"
    return Path.home() / ".local" / "share" / "pokenux"


def assets_are_missing(assets_path: Path) -> bool:
    data_path = assets_path / "data"
    required_files = ("pokemon.json", "generations.json", "types.json")
    if not all((data_path / filename).is_file() for filename in required_files):
        return True
    # The published archive may only contain FR; TCG supports language fallback.
    return not any(file.is_file() for file in data_path.glob("tcg_*.json"))

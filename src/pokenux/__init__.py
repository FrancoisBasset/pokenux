"""Pokénux: Pokémon adventures in your terminal."""

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("pokenux")
except PackageNotFoundError:
    # The authoritative version is package metadata, not a duplicated constant.
    __version__ = "0+unknown"

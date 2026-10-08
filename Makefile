.PHONY: setup run check build packages deb arch clean

setup:
	uv sync --locked --dev

run:
	uv run --frozen pokenux

check:
	uv run --frozen ruff check .
	uv run --frozen python -m unittest discover -s tests -v
	uv run --frozen python scripts/release.py check --allow-unreleased

build:
	uv build --out-dir dist/python
	uv run --frozen python scripts/check_dist.py dist/python/*

packages:
	uv run --frozen python scripts/build_linux.py --formats tar deb arch --output dist

deb:
	uv run --frozen python scripts/build_linux.py --formats tar deb --output dist

arch:
	uv run --frozen python scripts/build_linux.py --formats tar arch --output dist

clean:
	rm -rf build dist

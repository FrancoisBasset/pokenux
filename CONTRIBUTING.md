# Contributing to Pokénux

Small, focused contributions are welcome: clearer controls, bug fixes, tests,
translations, documentation, and packaging improvements all help. Read our
[code of conduct](CODE_OF_CONDUCT.md), then pick an existing issue or describe
your idea in a [new issue](https://github.com/FrancoisBasset/pokenux/issues/new/choose).
For a large feature, discuss the approach before investing in a full implementation.

## Development setup

Install [uv](https://docs.astral.sh/uv/), then:

```sh
git clone https://github.com/FrancoisBasset/pokenux.git
cd pokenux
uv sync --locked --dev
uv run pokenux
```

The project requires Python 3.14+. `uv` can provision a compatible interpreter.
The first interactive launch downloads the catalogue; automated tests should
use fixtures and mocks rather than depend on a live service or a personal save.

## Before opening a pull request

Run the checks from the repository root:

```sh
uv run ruff check .
uv run python -m unittest discover -s tests -v
```

Explain the problem, the resulting behaviour, and how you verified the change.
For a visible interface change, include a screenshot or short recording and
check keyboard navigation at both a normal and a narrow terminal width.
Add a regression test when fixing logic, persistence, or a packaging failure.
Update [the changelog](CHANGELOG.md) for user-visible changes.

Keep unrelated changes separate. Preserve existing user data, avoid network
work on the UI thread, and make failures recoverable where possible. Do not
commit generated data catalogues, downloaded artwork, databases, credentials,
or build output. Changes to dependencies should update `uv.lock` with `uv lock`.

## Finding your way around

| Path | Purpose |
| --- | --- |
| `src/pokenux/textual/` | Screens, activity views, widgets, styling, and UI translations |
| `src/pokenux/services/` | Catalogues, data access, quizzes, and booster logic |
| `src/pokenux/models/` | Pokémon and card data models |
| `src/pokenux/locales/` | Gettext translation catalogues |
| `tests/` | Automated regression and smoke tests |
| `scripts/` | Data preparation and release tooling |
| `docs/` | User and maintainer documentation |

Translation work should preserve placeholders and keyboard hints. For new UI
text, follow the surrounding translation conventions; do not assume every
screen is already translated.

See [the release guide](docs/releases.md) for building Linux packages and
[data and attribution](docs/data-and-attribution.md) before modifying catalogue
generation. Contributors retain copyright in their work; contributions are
provided under the project's [MIT license](LICENSE).

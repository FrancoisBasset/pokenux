# Getting help

Start with [installation](docs/installation.md) and [the playing guide](docs/usage.md).
If something still fails, open a
[bug report](https://github.com/FrancoisBasset/pokenux/issues/new?template=bug_report.yml).
Feature ideas are welcome in the issue tracker too. Please use
[private security reporting](SECURITY.md) for vulnerabilities.

## Useful troubleshooting steps

- **The application will not start:** check `pokenux --version` and
  `pokenux --check`. A source install needs Python 3.14+; distribution bundles
  supply their own Python runtime.
- **The first launch cannot load data:** a connection is needed to download
  the initial catalogue from GitHub. Check connectivity and try launching again.
- **A card or quiz image does not load:** the image or metadata service may be
  unavailable. Use the in-app retry or skip action. Rendering also depends on
  your terminal's capabilities.
- **Keyboard controls seem unresponsive:** move focus out of a search field
  with Tab or Escape. Home-screen number shortcuts apply on the home screen.
- **The layout is cramped:** enlarge the terminal or use the list/profile
  navigation offered by the narrow layout.

Avoid deleting your data folder as a troubleshooting shortcut: it includes
your saved collection. Close Pokénux and back it up first if you need to
experiment with a clean profile.

## Make a report easy to reproduce

Include the Pokénux version, installation method, Linux distribution and
architecture, terminal application, terminal size, exact steps, and what you
expected to happen. A screenshot or traceback helps. Review diagnostics before
posting: file paths may identify your local account.

Support is provided by volunteers; there is no guaranteed response time.

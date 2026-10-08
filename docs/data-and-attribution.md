# Data, local files, and attribution

Pokénux is an unofficial fan project. Its application code is licensed under
the [MIT license](../LICENSE). That license does not grant rights to Pokémon
names, trademarks, artwork, or third-party data.

## Sources

- [Tyradex](https://tyradex.vercel.app/) supplies the Pokémon catalogue used by
  the data preparation script.
- [TCGdex](https://tcgdex.net/) supplies card, set, series, and rarity metadata.
- Artwork is fetched from the image URLs provided by those catalogues.
- [Textual](https://textual.textualize.io/) powers the terminal interface;
  `textual-image` provides image rendering.

Pokémon and Pokémon TCG names, images, and trademarks belong to their
respective rights holders. Pokénux is not affiliated with Nintendo, Game
Freak, Creatures, or The Pokémon Company. Consult the upstream providers and
rights holders before redistributing their content. Bundled Python and
dependency licenses remain applicable to those components.

## Downloads and offline use

The first launch fetches the game catalogue from a project release hosted on
GitHub. Missing card details and artwork are retrieved as needed. Text games
and catalogue browsing work locally after the catalogue is installed; image
games and advanced card searches may need data that has not yet been cached.
Availability and completeness depend on the upstream providers.

Preferences, game data, caches, and the booster save are local to your computer
under `~/.local/share/pokenux/`. No Pokénux account is required. Network requests
to external providers are still subject to those providers' practices.

## Preparing a catalogue

The data preparation script is a maintainer tool. Its outputs go to
`src/pokenux/assets/data/`; generating files there does not automatically replace
the catalogue in an existing user's data directory.

To prepare card summaries:

```sh
uv run python scripts/prepare_assets.py --tcg-only
```

For an offline card metadata index, opt in explicitly:

```sh
uv run python scripts/prepare_assets.py --tcg-only --tcg-card-details
```

The second command makes an extra request for every card, potentially tens of
thousands. Avoid running it repeatedly; respect the providers' service limits.
Generated catalogues, downloaded artwork, and personal databases should not be
committed to the source repository.

## Game estimates

Booster prices, resale values, and special-hit probabilities are gameplay
estimates. Virtual euros cannot be exchanged for money. The simulator is not
a source of live card valuations or a guarantee of physical booster contents.
See [the playing guide](usage.md#boosters) for the modelled pack rules and their
reference links.

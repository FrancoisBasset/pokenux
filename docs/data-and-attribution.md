# Data, local files, and attribution

Pokénux is an unofficial fan project. Its application code is licensed under
the [MIT license](../LICENSE). That license does not grant rights to Pokémon
names, trademarks, artwork, or third-party data.

## Sources

- [Tyradex](https://tyradex.vercel.app/) supplies the Pokémon catalogue used by
  the data preparation script.
- [TCGdex](https://tcgdex.net/) supplies card, set, series, and rarity metadata.
- [PokeAPI's data repository](https://github.com/PokeAPI/pokeapi) supplies English
  Pokémon categories, ability names and egg-group names from a pinned CSV snapshot.
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
GitHub. New catalogues contain both French and English; Settings shows the
installed version and provides explicit update checks. An archive and its
files are verified before an atomic replacement of the installed data.
Missing card details and artwork are retrieved as needed. Text games
and catalogue browsing work locally after the catalogue is installed; image
games and advanced card searches may need data that has not yet been cached.
Availability and completeness depend on the upstream providers.

Preferences, game data, caches, and the booster save are local to your computer
under `$XDG_DATA_HOME/pokenux/`, or `~/.local/share/pokenux/` by default.
No Pokénux account is required. Network requests
to external providers are still subject to those providers' practices.

## Preparing a catalogue

The data preparation script is a maintainer tool. It produces a versioned ZIP,
a manifest and checksums in `dist/assets/`, without replacing a player's
installed catalogue. Both FR and EN are required for a new asset edition.

To prepare card summaries:

```sh
uv run python scripts/prepare_assets.py --version 1.0.0 --output dist/assets
```

For an offline card metadata index, opt in explicitly:

```sh
uv run python scripts/prepare_assets.py --version 1.0.0 --output dist/assets --tcg-card-details
```

The second command makes an extra request for every card, potentially tens of
thousands. Avoid running it repeatedly; respect the providers' service limits.
Generated catalogues, downloaded artwork, and personal databases should not be
committed to the source repository.
See [versioned assets](assets.md) for reuse of existing data, schema compatibility,
rollback, checksums and publication of the update channel.

## Game estimates

Booster prices, resale values, and special-hit probabilities are gameplay
estimates. Virtual euros cannot be exchanged for money. The simulator is not
a source of live card valuations or a guarantee of physical booster contents.
See [the playing guide](usage.md#boosters) for the modelled pack rules and their
reference links.

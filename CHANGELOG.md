# Changelog

User-visible changes are recorded here. Versions follow `MAJOR.MINOR.PATCH`;
dates use `YYYY-MM-DD`. Items marked **Unreleased** are not yet a published release.

## [1.1.0] - Unreleased

### Added

- Independent French/English preferences for the interface, Pokédex and TCG,
  with live updates of open views and a redesigned Settings page.
- Versioned bilingual catalogues, an independent asset release workflow,
  integrity checks, atomic installation, cancellation and recovery.
- English Pokémon categories, abilities and egg groups from pinned PokeAPI
  metadata, with explicit unavailable values for untranslated legacy data.

- Surprise quiz challenges, generation filters, hints, scoring, combos,
  session summaries, and answer review.
- Image quizzes with blur, pixelation, silhouettes, and answer reveals;
  interactive height and weight rankings.
- A persistent booster collection and virtual economy, training, duplicate
  resale, pack reveals, and era-specific pack composition.
- A responsive Pokédex profile with evolution browsing and links to TCG cards.
- Prepared Debian/Ubuntu packages, Arch packages, and portable Linux archives
  with a bundled Python runtime and dependencies.
- Automated checks and a tagged release workflow that assembles a draft release.
- Command-line help, version reporting, offline installation diagnostics, and
  support for launching with `python -m pokenux`.
- Contributor, support, security, installation, and release documentation.

### Changed

- Redesigned the home menu and theme, with clearer navigation and layouts for
  narrow terminals.
- Improved TCG browsing, filters, background metadata loading, and local caching.
- Documented Python 3.14 as the minimum version for source installations.
- Clarified the MIT license for code and separate rights for third-party content.

### Fixed

- First-launch installation accepts legacy archives with either `data/` or
  `assets/data/` layouts, including the archive currently published on GitHub.
- Setup failures show an explicit error state instead of a stalled download or
  a misleading connection warning.
- TCG requests keep their original language when preferences change, and
  metadata caches are separated by catalogue version.
- Deferred focus updates no longer pull players away from Settings.

- Activity tabs now close safely and retain unique identifiers.
- Booster purchases and sales persist atomically; opening a pack cannot lose
  cards if its tab closes before all cards are revealed.
- Unavailable quiz images can be retried or skipped without a score penalty.

## [1.0.0] - 2026-08-11

### Added

- Initial tagged Textual interface and project foundation.

[1.1.0]: https://github.com/FrancoisBasset/pokenux/compare/1.0.0...HEAD
[1.0.0]: https://github.com/FrancoisBasset/pokenux/tree/1.0.0

# Versioned French and English catalogues

Pokénux distributes its code and its catalogues separately. A new catalogue does
not require a new application release. The application, Pokémon names and TCG
cards each have their own French/English preference in **Settings**.

## Versions and update channel

- **Application version**: for example `1.1.0`, released as `v1.1.0`.
- **Asset content version**: for example `1.0.0`, released as `assets-v1.0.0`.
  Increase this version whenever published catalogue bytes change. Published
  content versions are immutable.
- **Schema version**: currently `1`. This describes the manifest and data format
  understood by the application. Incompatible format changes require a new
  schema and application support; content refreshes do not.

The schema-1 update channel is
[`assets-v1/assets-manifest.json`](https://github.com/FrancoisBasset/pokenux/releases/download/assets-v1/assets-manifest.json).
This small file points to an immutable ZIP on a numbered asset release. It is
independent of GitHub's global “Latest release”, so an application release never
accidentally becomes an asset update.

**The new channel is not published by these code changes.** Until a maintainer
publishes it, fresh installations can download the existing `1.0.0/pokenux-data.zip`
archive. Settings labels such data **legacy** and shows the languages actually
present. Existing legacy installations remain usable. A 404 for the unpublished
channel permits this fallback; a timeout, invalid manifest or failed checksum
never silently downgrades a versioned download to an unchecked legacy archive.
The legacy installer accepts either `data/` at the ZIP root or an `assets/`
wrapper, including directory entries. Mixed layouts, unsafe paths, links and
duplicate files are rejected before activation; all catalogues are validated.

## Bundle format

The ZIP contains JSON catalogues only:

```text
data/pokemon.json
data/generations.json
data/types.json
data/tcg_fr.json
data/tcg_en.json
```

Both TCG catalogues and French/English Pokémon names and types are required for
new bundles. Pokémon types retain their list of `{name, image}` objects, as
expected by `Pokemon.from_dict`. The type catalogue maps French and English names.
Optional English category, ability, egg-group and evolution metadata extends the
existing model without invalidating installed legacy data. Unavailable English
complex evolution conditions remain explicitly unavailable; simple level,
trade and friendship conditions are translated. French prose is not presented
as an English translation.

`assets-manifest.json` records `schema_version`, content `version`, `languages`,
archive filename/HTTPS URL/size/SHA-256, and the size/SHA-256 of every catalogue.
`SHA256SUMS` covers the manifest and ZIP. The manifest is external to the ZIP,
avoiding a self-referential archive hash. The application copies it into the active
installation after verification.

Artwork is not bundled. Images are fetched and cached on demand, keeping the
catalogue download small. No generated game data is committed to the source
repository or included in Python/Linux application packages.

## Prepare an asset release

Use the project's locked Python environment:

```sh
uv sync --locked --dev
uv run --frozen python scripts/prepare_assets.py --version 1.0.0 --output dist/assets
```

Fresh preparation fetches Pokémon data from [Tyradex](https://tyradex.app/), TCG
series/sets in both languages from [TCGdex](https://tcgdex.dev/), and English
metadata from four CSV files in an immutable
[PokeAPI data snapshot](https://github.com/PokeAPI/pokeapi/tree/2fe95532d27a9bf340575253aff50868319d8182/data/v2/csv).
Using bulk CSV files avoids one metadata request per Pokémon. TCG set responses
provide card summaries. `--tcg-card-details` explicitly opts into fetching each
card's full metadata; this adds tens of thousands of requests and is not used by
the default workflow. The application can fetch card details on demand.

To package an existing **bilingual** catalogue entirely offline:

```sh
uv run --frozen python scripts/prepare_assets.py \
  --version 1.0.0 --output dist/assets \
  --from-directory /path/to/assets
```

The source can be an `assets/` or `data/` directory. To enrich legacy local data
with English metadata, add `--enrich-english`; this makes four small CSV requests
and modifies only the staged copy. It does not download a missing TCG catalogue:
use fresh preparation if `tcg_fr.json` or `tcg_en.json` is absent. Source files and
the user's active installation are never modified by the preparer.

Packaging validates JSON against application models before writing the ZIP.
Member order and ZIP timestamps are fixed, so identical source bytes produce
identical archives. Fresh API responses can change between builds; retain the
reviewed output and increment the content version for later snapshots.

Outputs are `pokenux-assets-VERSION.zip`, `assets-manifest.json` and `SHA256SUMS`.
`--archive-url https://…` can override the immutable download URL when using a
separate distribution host. Verify the files before uploading:

```sh
(cd dist/assets && sha256sum --check SHA256SUMS)
uv run --frozen python -m unittest discover -s tests -p test_assets.py -v
```

## Draft, review and publish

The **Prepare bilingual assets** workflow supports:

- A manual run with a content version: builds a downloadable Actions artifact.
- A pushed tag such as `assets-v1.0.0`: builds and creates a **draft** release with
  the ZIP, manifest and checksum file. It refuses to replace published versions.

Asset tags do not run the application release workflow. The workflow never
publishes a draft and never updates the live channel automatically.

After reviewing the draft and its data, publish the numbered asset release with
“Set as latest release” disabled. Promote **that exact reviewed manifest** to the
schema-1 channel. This promotion is an explicit maintainer publishing action:

```sh
# Download the manifest of the reviewed, now-public numbered release.
gh release download assets-v1.0.0 --repo FrancoisBasset/pokenux \
  --pattern assets-manifest.json --dir /tmp/pokenux-assets-channel

# Only for first channel creation; do not recreate an existing channel.
gh release create assets-v1 --repo FrancoisBasset/pokenux \
  --target master --latest=false --title 'Pokénux assets — schema 1' \
  --notes 'Update manifest for schema-1 catalogues. Numbered asset releases are immutable.'

# Update the existing channel pointer with the reviewed manifest.
gh release upload assets-v1 --repo FrancoisBasset/pokenux \
  /tmp/pokenux-assets-channel/assets-manifest.json --clobber
```

The numbered ZIP must already be publicly downloadable when its manifest is
promoted. Never point the live channel at an unpublished draft. Changing the
PokeAPI snapshot or preparation rules requires reviewing the new output and
publishing a new content version.

## Installation guarantees and recovery

Downloads have timeouts, cancellation and progress. The application verifies the
archive size and SHA-256, extracts into a staging directory on the same filesystem,
rejects traversal paths, symlinks, duplicate members and oversized archives, then
checks every catalogue hash and model schema. Only a complete valid bundle is
promoted to `assets/`.

An installation lock prevents concurrent writers. Promotion retains the previous
installation as `.assets-previous`; a failed rename restores it. A restart can
recover a promotion interrupted between directory renames. Cancellation or
verification failures leave the active catalogue untouched. `AssetManager.rollback()`
can restore the retained installation after validating it. The previous copy may
include old artwork, so allow disk space for the active data, previous data and
staged download during an update.

`AssetManager.status()` is deliberately cheap: it reads version metadata and
checks required paths, without hashing every file on each Settings repaint.
Installation and rollback perform the full integrity check in a worker. SHA-256
checks detect corruption; manifest authenticity relies on the HTTPS GitHub
release channel and the maintainers controlling it.

Data sources and Pokémon rights are described in
[data-and-attribution.md](data-and-attribution.md). The repository's MIT licence
applies to its code; it does not transfer rights to Pokémon names or artwork.

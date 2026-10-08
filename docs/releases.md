# Building and releasing Pokénux

[Installation](installation.md) · [Contributing](../CONTRIBUTING.md) · [Changelog](../CHANGELOG.md)

The repository prepares version **1.1.0**. A successful version-tag workflow
creates a **draft** GitHub release; publishing that draft remains a maintainer
action. There is no automatic PyPI upload, AUR submission, or Debian repository.

## Build locally

Install [uv](https://docs.astral.sh/uv/) **0.11.23**, then run from a checkout:

```sh
uv sync --locked --dev
make check
make build
```

`make build` creates the wheel and source archive in `dist/python/`, and checks
that they contain the stylesheets and translations without downloaded game
data. The source archive includes the packaging tools and lockfile.

On Linux, build the portable archive and Debian package with:

```sh
make deb
```

On Arch Linux, `make packages` also builds the pacman package. Run as an
unprivileged user with `base-devel` installed. Alternatively, the checkout's
`PKGBUILD` supports `makepkg --syncdeps` with the required uv version available.
That recipe is intended for a complete checkout, not for submission to the AUR.

The builder itself accepts Python 3.11 or newer. Without a project environment:

```sh
python3 scripts/build_linux.py --formats tar deb --output dist
```

It downloads a private CPython 3.14.6 runtime, builds the wheel, and installs
the runtime dependencies from `uv.lock` with hash verification. Downloads are
needed while building. End-user package installation needs no Python package
downloads. When `dpkg-deb` is unavailable, the builder writes the Debian archive
format directly; the packaging tests cover its container structure.

Build each architecture on a matching Linux machine. Supported targets are
`x86_64` (`amd64` in Debian filenames) and `aarch64` (`arm64`). There is no cross
compiler. `--runtime /path/to/standalone/python` can reuse an existing matching
CPython installation; a virtual environment cannot be used as the runtime.
`--skip-build` is for local iteration with an existing wheel of this version.

## Artifacts and layout

| Artifact | Purpose |
| --- | --- |
| `pokenux-VERSION-py3-none-any.whl` | Python package; requires Python 3.14+ |
| `pokenux-VERSION.tar.gz` | Source distribution, including build tooling |
| `pokenux-VERSION-linux-ARCH.tar.gz` | Portable application and private runtime |
| `pokenux_VERSION-1_DEBARCH.deb` | Debian/Ubuntu package |
| `pokenux-VERSION-1-x86_64.pkg.tar.zst` | Arch Linux package |
| `pokenux-VERSION-arch-recipe-ARCH.tar.gz` | Release `PKGBUILD` and `.SRCINFO` with actual source checksums |
| `SHA256SUMS` | Hashes of the release's downloadable artifacts |

System packages put the application in `/opt/pokenux`, a launcher in
`/usr/bin/pokenux`, and the desktop entry, icon and man page in `/usr/share`.
They use their own Python runtime. Personal files live in the user's data
directory and survive removal. See [installation](installation.md).

The portable bundle contains `BUILD-INFO.json`, `DEPENDENCIES.json`, the locked
requirements, and third-party license notices. Game data and artwork are
downloaded separately and are not part of these packages. The desktop entry
opens a terminal; image rendering still depends on the terminal's capabilities.

Linux bundles require glibc 2.28+ and the native libraries declared in the
package metadata. Archive ordering, ownership, timestamps and gzip headers are
normalized; `SOURCE_DATE_EPOCH` overrides the last Git commit's timestamp.
This is not a claim of complete byte-for-byte reproducibility across hosts.

## What CI verifies

The [CI workflow](../.github/workflows/ci.yml) runs on pull requests and pushes
to `master` or `main`, and can also be started manually:

- Ruff, offline unit tests, and version/changelog consistency.
- Wheel and source contents, followed by wheel installation outside the checkout.
- Native x86-64 and AArch64 portable archives and Debian packages.
- Installation, `--version`, `--check`, and removal in Debian 12, Debian 13,
  and Ubuntu 22.04 containers on each architecture.
- An x86-64 Arch build from the generated recipe, followed by installation,
  diagnostics, and removal with pacman.

CI artifacts are available independently of a release. A local build alone
does not establish that every CI target passed; check the successful workflow
run before publishing. The package checks exercise startup and resources, not
every terminal's graphics protocol or the external Pokémon data services.

## Prepare a version

1. Choose a numeric `MAJOR.MINOR.PATCH` version. Update `pyproject.toml` and
   the checkout's `PKGBUILD`, then run `uv lock`.
2. Add a matching `## [VERSION] - YYYY-MM-DD` section to `CHANGELOG.md` with
   meaningful release notes. An `Unreleased` date is accepted during
   development but deliberately rejected by the release workflow.
3. Update version examples and release availability in the README and
   installation guide. Run `make check` and `make build`.
4. Validate the intended tag before committing:

   ```sh
   uv run --frozen python scripts/release.py check --tag v1.1.0
   ```

5. Commit the release preparation, then create and push the matching tag when
   ready to start release builds:

   ```sh
   git tag -a v1.1.0 -m "Pokénux 1.1.0"
   git push origin v1.1.0
   ```

The [release workflow](../.github/workflows/release.yml) checks the tag and
dated changelog, runs the full CI build, assembles the artifacts and checksums,
then creates an unpublished draft. Rerunning it can update that draft; it
refuses to replace assets of an already published release. Only the final
draft job receives repository write permission. GitHub Actions must be enabled
and repository policies must allow the workflow's token to create releases.

Review the draft notes, expected architecture files and successful container
checks, then publish the draft in GitHub. Do not move an existing published tag
or replace its artifacts; ship a new version for corrections.

Catalogues have an independent content version and `assets-vVERSION` release
tags. The application checks the `assets-v1` channel manifest for schema 1.
Until that channel is published, first-run setup can use the historical
`1.0.0` release's `pokenux-data.zip`; keep that asset available during migration.
Application tags use the `v` prefix. See [asset releases](assets.md) for building
bilingual catalogues and promoting a reviewed manifest to the update channel.

## Manual assembly and maintenance

To assemble local outputs into one release directory and verify them:

```sh
mkdir -p dist/release
cp dist/python/*.whl dist/python/*.tar.gz dist/release/
cp dist/*-linux-*.tar.gz dist/*.deb dist/*-arch-recipe-*.tar.gz dist/release/
# After an Arch build, also copy dist/*.pkg.tar.zst into dist/release/.
python3 scripts/release.py checksums dist/release
python3 scripts/release.py verify dist/release
```

Checksums detect damage or mismatched files, and are not cryptographic release
signatures. No signing key or package repository is provisioned by these tools.

Review dependency updates, regenerate `uv.lock`, and rerun the complete CI
before shipping. The self-contained packages need rebuilding to receive
security fixes in bundled Python libraries. For a runtime update, keep
`.python-version`, `PYTHON_VERSION` and `RUNTIME_BUILD` in
`scripts/build_linux.py`, the CI smoke-test interpreter, and runtime license
notices in `packaging/licenses/python-build-standalone/` in sync. Update `UV_VERSION`, workflow
setup versions and the root `PKGBUILD` together when changing the builder's uv
version. The runtime validation intentionally rejects an unexpected Python
build. Build-backend and GitHub Action versions are pinned as well; review
their updates rather than bypassing the pins.

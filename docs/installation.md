# Installing Pokénux

[Back to the project](../README.md) · [How to play](usage.md)

Version **1.1.0 is being prepared**. The formats below describe the release
artifacts built by this repository. Download links become available only when
the maintainer publishes a release on
[GitHub Releases](https://github.com/FrancoisBasset/pokenux/releases).
You can install the current source today.

## From source with uv

Use [uv](https://docs.astral.sh/uv/) to install the application in an isolated
environment with Python 3.14:

```sh
uv tool install --python 3.14 git+https://github.com/FrancoisBasset/pokenux.git
pokenux
```

If the command is not found after installation, run `uv tool update-shell` and
restart your shell. To update or remove the source installation:

```sh
uv tool upgrade pokenux
uv tool uninstall pokenux
```

Developers should instead follow [the contribution guide](../CONTRIBUTING.md).
There is no claim of a published PyPI package; the command above installs from
this Git repository.

## Linux packages

The release builder prepares self-contained packages for **64-bit glibc Linux**,
requiring **glibc 2.28 or newer**. Portable archives and Debian packages target
x86-64 and AArch64; the Arch release package targets x86-64. They include CPython
3.14 and the locked Python dependencies. Installation does not run `pip` or
fetch Python dependencies; the system package manager may install required
native libraries. The initial game catalogue and uncached artwork still
require network access when you play.

Choose the asset matching your architecture and check the release notes for
the distributions used to validate that build. These packages are not native
musl/Alpine, Windows, or macOS bundles.

After downloading the package and `SHA256SUMS` from the same release, verify
the files in the download directory:

```sh
sha256sum --check --ignore-missing SHA256SUMS
```

Checksums detect corrupted or mismatched files; they do not independently
authenticate a release downloaded from the same source.

### Debian and Ubuntu

Substitute the downloaded `.deb` filename:

```sh
sudo apt install ./pokenux_VERSION-1_ARCH.deb
pokenux
```

Install a newer `.deb` the same way to update. Remove the application with
`sudo apt remove pokenux`. This does not remove your home-directory game save.

### Arch Linux

Substitute the downloaded `.pkg.tar.zst` filename:

```sh
sudo pacman -U ./pokenux-VERSION-1-ARCH.pkg.tar.zst
pokenux
```

Install a newer package with `pacman -U` to update; remove it with
`sudo pacman -R pokenux`. The repository also includes a `PKGBUILD` for source
builds. These are project-provided packages, not a claim of an official Arch
repository package or an AUR listing.

### Portable archive

Extract the matching Linux archive into a directory you own and run its
`pokenux` launcher. Keep the extracted directory together: the launcher
needs the bundled runtime and libraries. No root privileges are required.

For example, for the prepared x86-64 release:

```sh
tar -xzf pokenux-1.1.0-linux-x86_64.tar.gz
./pokenux-1.1.0-linux-x86_64/pokenux
```

To update, extract the new archive into a separate directory and switch to its
launcher. To remove it, delete the extracted application directory. Personal
settings and saves live outside that directory and are retained.

## First launch and personal files

Run `pokenux --help` for command-line options, `pokenux --version` for the
installed version, or `pokenux --check` for diagnostics. A source environment
can also start the application with `python -m pokenux`.

The first interactive launch downloads a data catalogue. After that, local
Pokédex browsing and text quizzes are available offline. Advanced card details,
rarities, and artwork may still need a connection the first time they are used.

The locations below use the default data directory. If `XDG_DATA_HOME` is set
to an absolute path, Pokénux uses `$XDG_DATA_HOME/pokenux/` instead. An unset,
empty, or relative value keeps the historical `~/.local/share/pokenux/` default.
`pokenux --check` displays the directory actually in use.

| Location | Contents |
| --- | --- |
| `~/.local/share/pokenux/config.toml` | Language preferences |
| `~/.local/share/pokenux/assets/` | Installed game catalogue |
| `~/.local/share/pokenux/cache/` | Cached card metadata and search results |
| `~/.local/share/pokenux/simulator.sqlite3` | Virtual money, training, and collection |

Close the application before copying your active data directory to back up
your progress: `~/.local/share/pokenux/` by default, or `$XDG_DATA_HOME/pokenux/`
when configured with an absolute XDG path. Package removal intentionally
retains these personal files.

For build instructions, see [the release guide](releases.md). For startup or
rendering problems, see [support](../SUPPORT.md).

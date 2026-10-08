#!/usr/bin/env python3
"""Build standalone Linux releases without modifying the system Python.

Bootstrap: Python >=3.11 and uv 0.11.23. Native Linux x86_64/aarch64 only.
Debian packages use dpkg-deb when available, otherwise the documented ar format.
Arch packages require makepkg and must be built as an unprivileged user.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from collections.abc import Mapping

ROOT = Path(__file__).resolve().parents[1]
UV_VERSION = "0.11.23"
PYTHON_VERSION = "3.14.6"
RUNTIME_BUILD = "20260610"
PROJECT_URL = "https://github.com/FrancoisBasset/pokenux"
ARCHITECTURES = {"x86_64": "amd64", "aarch64": "arm64"}
DOCUMENTS = (
    "LICENSE",
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "SUPPORT.md",
    "CODE_OF_CONDUCT.md",
    "pyproject.toml",
)


def run(
    command: list[str | Path],
    *,
    cwd: Path | None = None,
    capture_output: bool = False,
    stdout: int | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a checked command, preserving its diagnostics on failure."""
    print("+ " + shlex.join(str(part) for part in command), flush=True)
    return subprocess.run(
        [str(part) for part in command],
        check=True,
        text=True,
        cwd=cwd,
        capture_output=capture_output,
        stdout=stdout,
        env=env,
    )


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path: Path, content: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(mode)


def normalize_permissions(root: Path) -> None:
    """Packages must remain usable when the build user's umask is restrictive."""
    for path in [root, *root.rglob("*")]:
        if not path.is_symlink():
            mode = 0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644
            path.chmod(mode)


def source_epoch() -> int:
    if "SOURCE_DATE_EPOCH" in os.environ:
        value = int(os.environ["SOURCE_DATE_EPOCH"])
        if value < 0:
            raise ValueError("SOURCE_DATE_EPOCH must be nonnegative")
        return value
    try:
        return int(
            subprocess.check_output(
                ["git", "log", "-1", "--format=%ct"],
                cwd=ROOT,
                stderr=subprocess.DEVNULL,
            )
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return 0


def tar_gz(source: Path, destination: Path, epoch: int, prefix: str = ".") -> None:
    """Stable order, timestamps, ownership and gzip headers."""

    def normalize(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.uid = info.gid = 0
        info.uname = info.gname = "root"
        info.mtime = epoch
        info.pax_headers = {}
        return info

    with destination.open("wb") as output:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=output, mtime=epoch
        ) as zipped:
            with tarfile.open(
                fileobj=zipped, mode="w", format=tarfile.GNU_FORMAT
            ) as archive:
                archive.add(source, arcname=prefix, recursive=False, filter=normalize)
                for path in sorted(source.rglob("*")):
                    archive.add(
                        path,
                        arcname=f"{prefix}/{path.relative_to(source)}",
                        recursive=False,
                        filter=normalize,
                    )


def validate_runtime(runtime: Path, architecture: str) -> None:
    interpreter = runtime / "bin/python3"
    if not interpreter.is_file() or (runtime / "pyvenv.cfg").exists():
        raise ValueError(
            "--runtime must name a standalone CPython installation, not a venv"
        )
    result = run(
        [
            interpreter,
            "-I",
            "-c",
            "import platform; "
            "print(platform.python_version()); print(platform.machine())",
        ],
        capture_output=True,
    ).stdout.splitlines()
    if result != [PYTHON_VERSION, architecture]:
        raise ValueError(
            f"Runtime must be CPython {PYTHON_VERSION} for {architecture}: {result}"
        )
    if (runtime / "BUILD").read_text().strip() != RUNTIME_BUILD:
        raise ValueError(
            f"Runtime must be python-build-standalone build {RUNTIME_BUILD}"
        )
    for path in runtime.rglob("*"):
        if path.is_symlink() and not path.resolve().is_relative_to(runtime.resolve()):
            raise ValueError(f"Runtime contains a nonportable symlink: {path}")


def build_bundle(
    work: Path,
    output: Path,
    version: str,
    architecture: str,
    runtime_source: Path | None,
    skip_build: bool,
) -> Path:
    bundle = work / f"pokenux-{version}-linux-{architecture}"
    runtime = bundle / "runtime"
    if runtime_source is None:
        installs = work / "python-download"
        run(
            [
                "uv",
                "python",
                "install",
                "--install-dir",
                installs,
                "--no-bin",
                PYTHON_VERSION,
            ]
        )
        runtime_source = installs / f"cpython-{PYTHON_VERSION}-linux-{architecture}-gnu"
    validate_runtime(runtime_source, architecture)
    shutil.copytree(
        runtime_source,
        runtime,
        symlinks=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    interpreter = runtime / "bin/python3"
    # Discard bootstrap packages, including pip: all release dependencies come from uv.lock.
    site = (
        runtime
        / "lib"
        / f"python{'.'.join(PYTHON_VERSION.split('.')[:2])}"
        / "site-packages"
    )
    shutil.rmtree(site)
    site.mkdir()
    if not skip_build:
        run(
            ["uv", "build", "--wheel", "--python", interpreter, "--out-dir", output],
            cwd=ROOT,
        )
    wheel = output / f"pokenux-{version}-py3-none-any.whl"
    if not wheel.is_file():
        raise ValueError(f"Expected wheel does not exist: {wheel}")
    requirements = bundle / "requirements.lock.txt"
    run(
        [
            "uv",
            "export",
            "--frozen",
            "--no-dev",
            "--no-emit-project",
            "--no-header",
            "--output-file",
            requirements,
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
    )
    # The platform ceiling avoids pulling wheels tied to the build host's newer glibc.
    run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            interpreter,
            "--target",
            site,
            "--python-platform",
            f"{architecture}-manylinux_2_28",
            "--only-binary",
            ":all:",
            "--require-hashes",
            "--link-mode",
            "copy",
            "--requirements",
            requirements,
        ]
    )
    run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            interpreter,
            "--target",
            site,
            "--no-deps",
            "--link-mode",
            "copy",
            wheel,
        ]
    )
    # Entry point shebangs embed the temporary build path. Only expose the relocatable launcher.
    for path in (runtime / "bin").iterdir():
        if not path.name.startswith("python"):
            path.unlink()
    if (site / "bin").exists():
        shutil.rmtree(site / "bin")
    write(
        bundle / "pokenux",
        "#!/bin/sh\nset -eu\n"
        'base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
        'exec "$base/runtime/bin/python3" -I -B -m pokenux "$@"\n',
        0o755,
    )
    for name in DOCUMENTS:
        shutil.copy2(ROOT / name, bundle / name)
    shutil.copytree(ROOT / "docs", bundle / "docs")
    # Retain the relative workflow links in the release guide.
    shutil.copytree(ROOT / ".github/workflows", bundle / ".github/workflows")
    shutil.copy2(ROOT / "packaging/THIRD_PARTY_NOTICES.txt", bundle)
    shutil.copytree(ROOT / "packaging/licenses", bundle / "licenses")
    share = bundle / "share"
    for source, target in (
        ("pokenux.desktop", "applications/pokenux.desktop"),
        ("pokenux.svg", "icons/hicolor/scalable/apps/pokenux.svg"),
        ("pokenux.1", "man/man1/pokenux.1"),
    ):
        (share / target).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "packaging" / source, share / target)
    manifest = run(
        [
            interpreter,
            "-I",
            "-B",
            "-c",
            "import importlib.metadata as m, json; "
            "print(json.dumps(sorted([{'name': d.metadata['Name'], 'version': d.version, "
            "'license': d.metadata.get('License-Expression') or d.metadata.get('License')} "
            "for d in m.distributions()], key=lambda d: d['name'].lower()), indent=2))",
        ],
        capture_output=True,
    ).stdout
    write(bundle / "DEPENDENCIES.json", manifest)
    write(
        bundle / "BUILD-INFO.json",
        json.dumps(
            {
                "version": version,
                "architecture": architecture,
                "python": PYTHON_VERSION,
                "python_build_standalone": RUNTIME_BUILD,
                "uv": UV_VERSION,
                "source_date_epoch": int(os.environ["SOURCE_DATE_EPOCH"]),
                "glibc_minimum": "2.28",
                "lock_sha256": sha256(ROOT / "uv.lock"),
                "wheel_sha256": sha256(wheel),
            },
            indent=2,
        )
        + "\n",
    )
    clean_runtime(runtime, site)
    normalize_permissions(bundle)
    run([bundle / "pokenux", "--version"], cwd=work)
    run([bundle / "pokenux", "--check"], cwd=work)
    # Validate after a real move as well, away from the source checkout.
    relocated = work / "relocated bundle"
    bundle.rename(relocated)
    run([relocated / "pokenux", "--check"], cwd=work)
    relocated.rename(bundle)
    return bundle


def clean_runtime(runtime: Path, site: Path) -> None:
    """Remove build-local metadata and the unused graphical Python shell."""
    standard_library = site.parent
    (site / ".lock").unlink(missing_ok=True)
    for name in ("tkinter", "idlelib", "ensurepip"):
        shutil.rmtree(standard_library / name, ignore_errors=True)
    for path in (standard_library / "lib-dynload").glob("_tkinter.*"):
        path.unlink()
    for path in runtime.rglob("__pycache__"):
        shutil.rmtree(path)
    for name in ("direct_url.json", "uv_cache.json"):
        for path in site.glob(f"*.dist-info/{name}"):
            path.unlink()
    # Keep installed-wheel inventories consistent after dropping private entry points.
    for record in site.glob("*.dist-info/RECORD"):
        with record.open(newline="") as stream:
            rows = [row for row in csv.reader(stream) if (site / row[0]).exists()]
        with record.open("w", newline="") as stream:
            csv.writer(stream).writerows(rows)


def install_tree(bundle: Path, root: Path) -> None:
    shutil.copytree(bundle, root / "opt/pokenux", symlinks=True)
    write(
        root / "usr/bin/pokenux", '#!/bin/sh\nexec /opt/pokenux/pokenux "$@"\n', 0o755
    )
    shutil.copytree(bundle / "share", root / "usr/share", dirs_exist_ok=True)
    documentation = root / "usr/share/doc/pokenux"
    documentation.mkdir(parents=True)
    for name in (*DOCUMENTS, "THIRD_PARTY_NOTICES.txt"):
        shutil.copy2(bundle / name, documentation / name)
    shutil.copytree(bundle / "docs", documentation / "docs")
    shutil.copytree(bundle / ".github", documentation / ".github")
    (root / "usr/share/licenses/pokenux").mkdir(parents=True)
    shutil.copy2(bundle / "LICENSE", root / "usr/share/licenses/pokenux/LICENSE")
    normalize_permissions(root)


def write_ar(destination: Path, members: list[Path], epoch: int) -> None:
    """Write Debian's simple Unix ar container; members are smaller than 10 GB."""
    with destination.open("wb") as output:
        output.write(b"!<arch>\n")
        for member in members:
            size = member.stat().st_size
            header = f"{member.name + '/':<16}{epoch:<12}{0:<6}{0:<6}{'100644':<8}{size:<10}`\n"
            if len(header) != 60:
                raise ValueError(f"Invalid ar member header: {member.name}")
            output.write(header.encode("ascii"))
            with member.open("rb") as stream:
                shutil.copyfileobj(stream, output)
            if size % 2:
                output.write(b"\n")


def build_deb(
    bundle: Path, work: Path, output: Path, version: str, architecture: str, epoch: int
) -> Path:
    root = work / "debian-root"
    install_tree(bundle, root)
    installed_size = sum(
        (p.lstat().st_size + 1023) // 1024 if p.is_file() or p.is_symlink() else 1
        for p in root.rglob("*")
    )
    control = root / "DEBIAN"
    write(
        control / "control",
        f"""Package: pokenux
Version: {version}-1
Section: games
Priority: optional
Architecture: {ARCHITECTURES[architecture]}
Maintainer: François Basset <mrfrancoisbasset@gmail.com>
Installed-Size: {installed_size}
Depends: libc6 (>= 2.28), libgcc-s1, libstdc++6, zlib1g, ca-certificates
Homepage: {PROJECT_URL}
Description: Pokémon terminal companion with quizzes and virtual cards
 Explore the Pokedex, challenge yourself with quizzes and collect virtual cards.
 Includes a private Python runtime; no system Python packages are modified.
 An Internet connection is required for Pokemon and trading card data.
""",
    )
    checksums = []
    for path in sorted(root.rglob("*")):
        if (
            path.is_file()
            and not path.is_symlink()
            and not path.is_relative_to(control)
        ):
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "md5").hexdigest()
            checksums.append(f"{digest}  {path.relative_to(root)}\n")
    write(control / "md5sums", "".join(checksums))
    # dpkg-deb otherwise inherits checkout/copy timestamps for older source files.
    for path in [root, *root.rglob("*")]:
        os.utime(path, (epoch, epoch), follow_symlinks=False)
    destination = output / f"pokenux_{version}-1_{ARCHITECTURES[architecture]}.deb"
    if shutil.which("dpkg-deb"):
        run(["dpkg-deb", "--root-owner-group", "--build", root, destination])
    else:
        print(
            "dpkg-deb unavailable; writing equivalent Debian 2.0 ar archive.",
            flush=True,
        )
        control_archive = work / "control.tar.gz"
        tar_gz(control, control_archive, epoch)
        shutil.rmtree(control)
        data_archive = work / "data.tar.gz"
        tar_gz(root, data_archive, epoch)
        binary = work / "debian-binary"
        write(binary, "2.0\n")
        write_ar(destination, [binary, control_archive, data_archive], epoch)
    return destination


def arch_recipe(archive: Path, output: Path, version: str, architecture: str) -> Path:
    directory = output / "arch" / architecture
    directory.mkdir(parents=True, exist_ok=True)
    checksum = sha256(archive)
    recipe = f'''# Generated from the actual release archive; do not replace hashes with SKIP.
pkgname=pokenux
pkgver={version}
pkgrel=1
pkgdesc='Pokémon terminal companion with quizzes and virtual cards'
arch=('{architecture}')
url='{PROJECT_URL}'
license=('MIT' 'PSF-2.0')
depends=('glibc>=2.28' 'gcc-libs' 'zlib' 'ca-certificates')
options=('!strip' '!debug')
source=("{archive.name}::$url/releases/download/v$pkgver/{archive.name}")
sha256sums=('{checksum}')

package() {{
  local bundle="$srcdir/pokenux-$pkgver-linux-{architecture}"
  install -d "$pkgdir/opt" "$pkgdir/usr/bin" "$pkgdir/usr/share/doc/pokenux" \\
    "$pkgdir/usr/share/licenses/pokenux"
  cp -a "$bundle" "$pkgdir/opt/pokenux"
  printf '#!/bin/sh\\nexec /opt/pokenux/pokenux "$@"\\n' > "$pkgdir/usr/bin/pokenux"
  chmod 755 "$pkgdir/usr/bin/pokenux"
  cp -a "$bundle/share/." "$pkgdir/usr/share/"
  install -m644 "$bundle/LICENSE" "$pkgdir/usr/share/licenses/pokenux/LICENSE"
  install -m644 "$bundle/"*.md "$bundle/LICENSE" "$bundle/pyproject.toml" "$bundle/THIRD_PARTY_NOTICES.txt" \\
    "$pkgdir/usr/share/doc/pokenux/"
  cp -a "$bundle/docs" "$bundle/.github" "$pkgdir/usr/share/doc/pokenux/"
}}
'''
    write(directory / "PKGBUILD", recipe)
    write(
        directory / ".SRCINFO",
        f"""pkgbase = pokenux
\tpkgdesc = Pokémon terminal companion with quizzes and virtual cards
\tpkgver = {version}
\tpkgrel = 1
\turl = {PROJECT_URL}
\tarch = {architecture}
\tlicense = MIT
\tlicense = PSF-2.0
\tdepends = glibc>=2.28
\tdepends = gcc-libs
\tdepends = zlib
\tdepends = ca-certificates
\toptions = !strip
\toptions = !debug
\tsource = {archive.name}::{PROJECT_URL}/releases/download/v{version}/{archive.name}
\tsha256sums = {checksum}

pkgname = pokenux
""",
    )
    return directory


def build_arch(recipe: Path, archive: Path, output: Path, work: Path) -> list[Path]:
    build = work / "arch-build"
    shutil.copytree(recipe, build)
    shutil.copy2(archive, build / archive.name)
    environment = {**os.environ, "PKGDEST": str(output), "PKGEXT": ".pkg.tar.zst"}
    run(
        ["makepkg", "--nodeps", "--cleanbuild", "--noconfirm", "--force"],
        cwd=build,
        env=environment,
    )
    result = run(
        ["makepkg", "--packagelist"], cwd=build, env=environment, capture_output=True
    )
    return [Path(name) for name in result.stdout.splitlines()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--formats",
        nargs="+",
        choices=("tar", "deb", "arch"),
        default=("tar", "deb", "arch"),
    )
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument(
        "--runtime", type=Path, help="Existing standalone CPython installation to copy"
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Reuse the versioned wheel in --output",
    )
    args = parser.parse_args()
    architecture = platform.machine()
    if sys.platform != "linux" or architecture not in ARCHITECTURES:
        parser.error(
            "Build natively on Linux x86_64 or aarch64 (cross compilation is unsupported)"
        )
    if not shutil.which("uv"):
        parser.error(f"Install uv {UV_VERSION} before building")
    uv_version = subprocess.check_output(["uv", "--version"], text=True).split()[1]
    if uv_version != UV_VERSION:
        parser.error(f"Release builds require uv {UV_VERSION}; found {uv_version}")
    if "arch" in args.formats and (not shutil.which("makepkg") or os.geteuid() == 0):
        parser.error(
            "Arch builds require makepkg and a non-root user; use --formats tar deb elsewhere"
        )
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        parser.error(
            "Linux releases require a stable MAJOR.MINOR.PATCH project version"
        )
    if (ROOT / ".python-version").read_text().strip() != PYTHON_VERSION:
        parser.error(
            "Update the runtime pin, notices and builder when changing .python-version"
        )
    epoch = source_epoch()
    os.environ["SOURCE_DATE_EPOCH"] = str(epoch)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    artifacts = []
    with tempfile.TemporaryDirectory(prefix="pokenux-build-") as temporary:
        work = Path(temporary)
        bundle = build_bundle(
            work,
            output,
            version,
            architecture,
            args.runtime.resolve() if args.runtime else None,
            args.skip_build,
        )
        archive = output / f"{bundle.name}.tar.gz"
        tar_gz(bundle, archive, epoch, prefix=bundle.name)
        artifacts.append(archive)
        recipe = arch_recipe(archive, output, version, architecture)
        recipe_archive = output / f"pokenux-{version}-arch-recipe-{architecture}.tar.gz"
        tar_gz(
            recipe,
            recipe_archive,
            epoch,
            prefix=f"pokenux-{version}-arch-{architecture}",
        )
        artifacts.append(recipe_archive)
        if "deb" in args.formats:
            artifacts.append(
                build_deb(bundle, work, output, version, architecture, epoch)
            )
        if "arch" in args.formats:
            artifacts.extend(build_arch(recipe, archive, output, work))
    checksum_file = output / f"SHA256SUMS-linux-{architecture}.txt"
    write(
        checksum_file, "".join(f"{sha256(path)}  {path.name}\n" for path in artifacts)
    )
    print(
        "\nBuilt artifacts:\n" + "\n".join(str(p) for p in [*artifacts, checksum_file])
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Build failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error

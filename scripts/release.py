"""Validate release metadata and produce notes/checksums without publishing."""

import argparse
from datetime import date
import hashlib
from pathlib import Path
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"\d+\.\d+\.\d+")


def release_info(
    root: Path = ROOT, tag: str | None = None, *, allow_unreleased: bool = False
) -> tuple[str, str]:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    if not VERSION.fullmatch(version):
        raise ValueError("Use a numeric major.minor.patch project version.")
    if tag is not None and tag != f"v{version}":
        raise ValueError(f"Tag {tag!r} does not match project version v{version}.")
    locked = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    package = next((p for p in locked["package"] if p["name"] == "pokenux"), None)
    if package is None or package["version"] != version:
        raise ValueError("Refresh uv.lock after updating the project version.")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = re.search(
        rf"^## \[{re.escape(version)}\] - ([^\n]+)$", changelog, re.MULTILINE
    )
    if heading is None:
        raise ValueError(f"CHANGELOG.md needs a '## [{version}] - YYYY-MM-DD' section.")
    stamp = heading.group(1).strip()
    if stamp.lower() == "unreleased":
        if not allow_unreleased:
            raise ValueError("Date the changelog section before tagging a release.")
    else:
        date.fromisoformat(stamp)
    body = re.split(
        r"^## \[", changelog[heading.end() :], maxsplit=1, flags=re.MULTILINE
    )[0].strip()
    if not body:
        raise ValueError("Release notes must describe the changes.")
    return version, body


def checksums(directory: Path) -> Path:
    """Hash only release assets, never a previous manifest or intermediate tree."""
    suffixes = (".whl", ".tar.gz", ".deb", ".pkg.tar.zst")
    files = sorted(
        p for p in directory.iterdir() if p.is_file() and p.name.endswith(suffixes)
    )
    if not files:
        raise ValueError(f"No release assets in {directory}.")
    lines = []
    for path in files:
        if "\n" in path.name or "\r" in path.name or "\\" in path.name:
            raise ValueError(f"Unsupported asset filename: {path.name!r}")
        with path.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        lines.append(f"{digest}  {path.name}\n")
    manifest = directory / "SHA256SUMS"
    manifest.write_text("".join(lines), encoding="utf-8")
    return manifest


def verify_checksums(directory: Path) -> None:
    lines = (directory / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError("Empty checksum manifest.")
    seen = set()
    for line in lines:
        match = re.fullmatch(r"([a-f0-9]{64})  ([^/\\\r\n]+)", line)
        if match is None or match.group(2) in (".", ".."):
            raise ValueError("Invalid checksum entry or unsafe filename.")
        digest, filename = match.groups()
        if filename in seen:
            raise ValueError(f"Duplicate checksum entry: {filename}")
        seen.add(filename)
        path = directory / filename
        if path.is_symlink():
            raise ValueError(f"Release assets must be regular files: {filename}")
        with path.open("rb") as source:
            actual = hashlib.file_digest(source, "sha256").hexdigest()
        if actual != digest:
            raise ValueError(f"Checksum mismatch: {filename}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Check version, lockfile and changelog.")
    check.add_argument("--tag")
    check.add_argument("--allow-unreleased", action="store_true")
    notes = commands.add_parser("notes", help="Extract the dated changelog section.")
    notes.add_argument("--tag", required=True)
    notes.add_argument("--output", type=Path, required=True)
    for name in ("checksums", "verify"):
        command = commands.add_parser(name)
        command.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            version, _ = release_info(
                tag=args.tag, allow_unreleased=args.allow_unreleased
            )
            print(f"Release metadata OK: {version}")
        elif args.command == "notes":
            version, body = release_info(tag=args.tag)
            args.output.write_text(f"# Pokénux {version}\n\n{body}\n", encoding="utf-8")
        elif args.command == "checksums":
            print(checksums(args.directory))
        else:
            verify_checksums(args.directory)
            print("All release checksums match.")
    except (OSError, ValueError, KeyError) as error:
        print(f"Release check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

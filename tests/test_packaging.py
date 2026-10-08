"""Portable archive guarantees checked by independent parsers and system ar."""

import ast
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

from scripts.build_linux import ROOT, tar_gz, write_ar


class PortableArchiveTests(unittest.TestCase):
    def test_builder_can_bootstrap_on_python_311(self):
        # Debian's system interpreter must parse the builder before it downloads
        # the private Python 3.14 runtime. This catches accidental newer syntax.
        ast.parse(
            (ROOT / "scripts" / "build_linux.py").read_text(encoding="utf-8"),
            feature_version=(3, 11),
        )

    def test_tar_is_reproducible_and_preserves_launcher_and_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outputs = []
            for index in range(2):
                source = root / f"source-{index}"
                source.mkdir()
                launcher = source / "pokenux"
                launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                launcher.chmod(0o755)
                (source / "README.md").write_text("Example\n", encoding="utf-8")
                (source / "command").symlink_to("pokenux")
                for path in (source, launcher, source / "README.md"):
                    os.utime(path, (100 + index, 100 + index))
                output = root / f"different-name-{index}.tar.gz"
                tar_gz(source, output, epoch=12345, prefix="pokenux")
                outputs.append(output.read_bytes())
                with tarfile.open(output) as archive:
                    entries = archive.getmembers()
                    self.assertTrue(
                        all(entry.uid == entry.gid == 0 for entry in entries)
                    )
                    self.assertTrue(all(entry.mtime == 12345 for entry in entries))
                    self.assertEqual(archive.getmember("pokenux/pokenux").mode, 0o755)
                    link = archive.getmember("pokenux/command")
                    self.assertTrue(link.issym())
                    self.assertEqual(link.linkname, "pokenux")
                    content = archive.extractfile("pokenux/README.md")
                    self.assertIsNotNone(content)
                    with content:
                        self.assertEqual(content.read(), b"Example\n")
            self.assertEqual(outputs[0], outputs[1])

    @unittest.skipUnless(
        shutil.which("ar"), "system ar is needed to verify Debian's outer container"
    )
    def test_ar_member_order_and_odd_byte_padding_are_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = {
                "debian-binary": b"2.0\n",
                "control.tar.gz": b"odd",
                "data.tar.gz": b"even",
            }
            members = []
            for name, payload in payloads.items():
                member = root / name
                member.write_bytes(payload)
                members.append(member)
            destination = root / "example.deb"
            write_ar(destination, members, epoch=12345)
            listing = subprocess.check_output(["ar", "t", str(destination)], text=True)
            self.assertEqual(listing.splitlines(), list(payloads))
            for name, expected in payloads.items():
                with self.subTest(member=name):
                    actual = subprocess.check_output(
                        ["ar", "p", str(destination), name]
                    )
                    self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()

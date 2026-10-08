# Security policy

## Reporting a vulnerability

Please send security reports privately to **mrfrancoisbasset@gmail.com**.
If this repository offers **Security → Report a vulnerability**, that private
GitHub channel is also suitable. Do not put an unpatched vulnerability or a
credential into a public issue.

Include the affected version, installation method, operating system, steps to
reproduce, and the likely impact. A minimal reproducer is useful. Remove
personal data, credentials, and unrelated files from examples.

This is a volunteer project. There is no guaranteed response time or paid
security programme. The maintainer will assess reports and coordinate a fix
and disclosure where appropriate.

## Supported versions

Security fixes target the current development branch and the latest released
version. There are no long-term support branches or promised backports. Version
1.1.0 is currently in preparation; an entry in the changelog is not a release.

## Relevant boundaries

Pokénux downloads catalogue data, card metadata, and artwork from external
services. Linux bundles include a Python runtime and third-party dependencies,
which need updates along with the application. Use project release assets or
build from source, and verify the published checksums when installing an archive.

Local settings, caches, and game saves are stored under
`~/.local/share/pokenux/`. Do not attach that entire directory to a report;
share only the smallest relevant example after reviewing its contents.

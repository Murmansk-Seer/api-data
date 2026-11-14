"""Fail closed with explicit source filename, actual and expected version values."""

import argparse
from pathlib import Path
import re


def verify_unity_snapshot(root: Path, parser_revision: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", parser_revision):
        raise ValueError("Unity source gate: expected parser must be a full Git SHA")

    def read(name):
        path = root / name
        try:
            return path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as error:
            raise ValueError(
                f"Unity source gate: {path}: actual=unreadable, expected=required marker: {error}"
            ) from error

    version = read(".version")
    if not re.fullmatch(r"\d{14}", version):
        raise ValueError(
            f"Unity source gate: {root / '.version'}: actual={version!r}, expected=14-digit official version"
        )
    for name, expected in (
        (".parser-revision", parser_revision),
        (".somua-version", version),
    ):
        actual = read(name)
        if actual != expected:
            raise ValueError(
                f"Unity source gate: {root / name}: actual={actual!r}, expected={expected!r}; refusing mixed snapshots"
            )
    return version


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    cli.add_argument("--parser", required=True)
    args = cli.parse_args()
    print(verify_unity_snapshot(args.root, args.parser))

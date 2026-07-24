#!/usr/bin/env python3
"""Verify that all public version declarations match VERSION."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path


class VersionMismatchError(RuntimeError):
    """Raised when a version declaration does not match VERSION."""


def _read_expected_version(root: Path) -> str:
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not version:
        raise VersionMismatchError("VERSION is empty")
    return version


def _read_package_version(root: Path) -> str:
    with (root / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def _read_module_version(root: Path) -> str:
    text = (root / "src/division_overtime/__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"$', text, re.MULTILINE)
    if match is None:
        raise VersionMismatchError("__version__ was not found")
    return match.group(1)


def _read_json_version(path: Path) -> str:
    return str(json.loads(path.read_text(encoding="utf-8"))["version"])


def collect_versions(root: Path) -> dict[str, str]:
    """Return all version declarations keyed by their source file."""

    return {
        "VERSION": _read_expected_version(root),
        "pyproject.toml": _read_package_version(root),
        "src/division_overtime/__init__.py": _read_module_version(root),
        "frontend/package.json": _read_json_version(root / "frontend/package.json"),
        "frontend/package-lock.json": _read_json_version(root / "frontend/package-lock.json"),
    }


def verify_versions(root: Path) -> str:
    """Return the common version or raise when declarations differ."""

    versions = collect_versions(root)
    expected = versions["VERSION"]
    mismatches = {name: value for name, value in versions.items() if value != expected}
    if mismatches:
        details = ", ".join(f"{name}={value}" for name, value in mismatches.items())
        raise VersionMismatchError(f"version mismatch: expected {expected}; {details}")
    return expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    try:
        version = verify_versions(args.root.resolve())
    except (KeyError, OSError, ValueError, VersionMismatchError) as exc:
        print(f"version_check=failed: {exc}")
        return 1

    print(f"version_check=ok version={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

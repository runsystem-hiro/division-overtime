from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

from dotenv import dotenv_values


def build_environment(env_file: Path, base_environment: Mapping[str, str]) -> dict[str, str]:
    child_environment = dict(base_environment)
    for key, value in dotenv_values(env_file, interpolate=False).items():
        if value is not None and key not in child_environment:
            child_environment[key] = value
    return child_environment


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: run_with_env.py <env-file> <command> [args...]", file=sys.stderr)
        return 2

    env_file = Path(sys.argv[1])
    command = sys.argv[2:]

    if not env_file.is_file():
        print(f"Environment file was not found: {env_file}", file=sys.stderr)
        return 2

    child_environment = build_environment(env_file, os.environ)
    os.execvpe(command[0], command, child_environment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

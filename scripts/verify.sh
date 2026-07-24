#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_BIN="$PROJECT_ROOT/.venv/bin"

cd "$PROJECT_ROOT"

"$VENV_BIN/python" scripts/check_version.py --root "$PROJECT_ROOT"
"$VENV_BIN/ruff" check .
"$VENV_BIN/ruff" format --check .
"$VENV_BIN/pytest" -q
"$VENV_BIN/division-overtime" --root "$PROJECT_ROOT" validate-config
"$VENV_BIN/division-overtime" --root "$PROJECT_ROOT" database status
"$VENV_BIN/division-overtime" --root "$PROJECT_ROOT" health

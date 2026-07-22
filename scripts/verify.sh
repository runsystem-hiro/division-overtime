#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m compileall -q src tests
if command -v ruff >/dev/null 2>&1; then
  ruff check .
fi
pytest -q

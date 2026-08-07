#!/usr/bin/env bash
set -euo pipefail
ROOT=${1:-/home/pi/division-overtime}
cd "$ROOT"
command -v uv >/dev/null || { echo "Required command was not found: uv" >&2; exit 2; }
uv sync --frozen --extra web --extra dev
mkdir -p var data
sudo install -m 0644 systemd/division-overtime-*.service systemd/division-overtime-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
echo "Installed. Configure .env, config/production.toml and data/employeeKey.csv before enabling timers."

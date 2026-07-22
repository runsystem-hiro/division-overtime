#!/usr/bin/env bash
set -euo pipefail
ROOT=${1:-/home/pi/division-overtime}
cd "$ROOT"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e '.[web,dev]'
mkdir -p var data
sudo install -m 0644 systemd/division-overtime-*.service systemd/division-overtime-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
echo "Installed. Configure .env, config/production.toml and data/employeeKey.csv before enabling timers."

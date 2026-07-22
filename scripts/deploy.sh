#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
WEB_SERVICE="division-overtime-web.service"
HEALTH_URL="http://127.0.0.1:8000/api/system/health"

cd "$PROJECT_ROOT"

require_command() {
    local command_name=$1
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "ERROR: required command is not installed: $command_name" >&2
        return 1
    fi
}

echo "==> Preflight"
require_command git
require_command npm
require_command curl
require_command sudo

if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "ERROR: Python virtual environment is missing: $VENV_PYTHON" >&2
    echo "Run: bash ./scripts/install.sh" >&2
    exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
    echo "ERROR: working tree is not clean. Commit, stash, or discard changes before deployment." >&2
    git status --short >&2
    exit 1
fi

echo "==> Update source"
git pull --ff-only

echo "==> Update Python dependencies"
"$VENV_PYTHON" -m pip install -e '.[web,dev]'

echo "==> Install frontend dependencies"
npm --prefix frontend ci

echo "==> Build frontend"
npm --prefix frontend run build

echo "==> Verify application"
./scripts/verify.sh

echo "==> Restart Web service"
sudo systemctl restart "$WEB_SERVICE"

echo "==> Wait for Web service"
for attempt in {1..15}; do
    if curl -fsS "$HEALTH_URL" >/tmp/division-overtime-web-health.json; then
        cat /tmp/division-overtime-web-health.json
        echo
        rm -f /tmp/division-overtime-web-health.json
        echo "Deployment completed."
        exit 0
    fi
    sleep 1
done

rm -f /tmp/division-overtime-web-health.json
systemctl status "$WEB_SERVICE" --no-pager || true
journalctl -u "$WEB_SERVICE" -n 50 --no-pager || true
echo "ERROR: Web health check failed: $HEALTH_URL" >&2
exit 1

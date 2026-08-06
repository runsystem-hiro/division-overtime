#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_BIN="$PROJECT_ROOT/.venv/bin"
ENVIRONMENT="production"

usage() {
    echo "Usage: $0 [--environment development]" >&2
}

while (($# > 0)); do
    case "$1" in
        --environment)
            if (($# < 2)); then
                usage
                exit 2
            fi
            ENVIRONMENT="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage
            exit 2
            ;;
    esac
done

if [[ "$ENVIRONMENT" != "production" && "$ENVIRONMENT" != "development" ]]; then
    echo "Unsupported environment: $ENVIRONMENT" >&2
    usage
    exit 2
fi

cd "$PROJECT_ROOT"

if [[ "$ENVIRONMENT" == "development" ]]; then
    command -v uv >/dev/null || { echo "Required command was not found: uv" >&2; exit 2; }
    command -v npm >/dev/null || { echo "Required command was not found: npm" >&2; exit 2; }
    command -v git >/dev/null || { echo "Required command was not found: git" >&2; exit 2; }

    uv sync --frozen --extra web --extra dev
    uv run python scripts/check_version.py --root "$PROJECT_ROOT"
    uv run ruff check .
    uv run ruff format --check .
    env -u DIVISION_OVERTIME_ENV uv run pytest -q

    DIVISION_OVERTIME_ENV=development uv run division-overtime --root "$PROJECT_ROOT" validate-config
    DIVISION_OVERTIME_ENV=development uv run division-overtime --root "$PROJECT_ROOT" database status
    DIVISION_OVERTIME_ENV=development uv run division-overtime --root "$PROJECT_ROOT" employees check-consistency
    DIVISION_OVERTIME_ENV=development uv run division-overtime --root "$PROJECT_ROOT" health

    (
        cd frontend
        npm ci
        npm run lint
        npm run test
        npm run build
    )
    git diff --check
    echo "Development verification completed successfully."
    exit 0
fi

"$VENV_BIN/python" scripts/check_version.py --root "$PROJECT_ROOT"
"$VENV_BIN/ruff" check .
"$VENV_BIN/ruff" format --check .
env -u DIVISION_OVERTIME_ENV "$VENV_BIN/pytest" -q
DIVISION_OVERTIME_ENV=production "$VENV_BIN/division-overtime" --root "$PROJECT_ROOT" validate-config
DIVISION_OVERTIME_ENV=production "$VENV_BIN/division-overtime" --root "$PROJECT_ROOT" database status
DIVISION_OVERTIME_ENV=production "$VENV_BIN/division-overtime" --root "$PROJECT_ROOT" employees check-consistency
DIVISION_OVERTIME_ENV=production "$VENV_BIN/division-overtime" --root "$PROJECT_ROOT" health

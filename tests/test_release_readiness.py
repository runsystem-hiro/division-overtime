from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_public_versions_match_version_file() -> None:
    expected = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()

    with (PROJECT_ROOT / "pyproject.toml").open("rb") as handle:
        python_version = tomllib.load(handle)["project"]["version"]

    with (PROJECT_ROOT / "uv.lock").open("rb") as handle:
        uv_lock = tomllib.load(handle)

    locked_project = next(
        package for package in uv_lock["package"] if package["name"] == "division-overtime"
    )

    frontend = json.loads((PROJECT_ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    lock = json.loads((PROJECT_ROOT / "frontend/package-lock.json").read_text(encoding="utf-8"))
    module_text = (PROJECT_ROOT / "src/division_overtime/__init__.py").read_text(encoding="utf-8")

    assert python_version == expected
    assert locked_project["version"] == expected
    assert frontend["version"] == expected
    assert lock["version"] == expected
    assert lock["packages"][""]["version"] == expected
    assert f'__version__ = "{expected}"' in module_text

    changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{expected}] - " in changelog


def test_version_check_script_succeeds() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_version.py", "--root", str(PROJECT_ROOT)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    expected = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert result.stdout.strip() == f"version_check=ok version={expected}"


def test_verify_and_deploy_enforce_version_checks() -> None:
    verify = (PROJECT_ROOT / "scripts/verify.sh").read_text(encoding="utf-8")
    deploy = (PROJECT_ROOT / "scripts/deploy.sh").read_text(encoding="utf-8")

    assert 'scripts/check_version.py --root "$PROJECT_ROOT"' in verify
    pull_position = deploy.index("git pull --ff-only")
    version_position = deploy.index('EXPECTED_VERSION="$(<"$PROJECT_ROOT/VERSION")"')

    assert version_position > pull_position
    assert 'if [[ "$ACTUAL_VERSION" != "$EXPECTED_VERSION" ]]' in deploy
    assert "Deployment completed. version=$ACTUAL_VERSION" in deploy


def test_deploy_suppresses_transient_health_errors_but_reports_final_failure() -> None:
    deploy = (PROJECT_ROOT / "scripts/deploy.sh").read_text(encoding="utf-8")

    quiet_check = 'curl -fsS "$HEALTH_URL" >/tmp/division-overtime-web-health.json 2>/dev/null'
    final_check = 'curl -fsS "$HEALTH_URL" >/tmp/division-overtime-web-health.json || true'

    assert "for attempt in {1..15}" in deploy
    assert "sleep 1" in deploy
    assert quiet_check in deploy
    assert final_check in deploy
    assert deploy.index(final_check) > deploy.index("done")


def test_web_service_is_independent_from_notification_units() -> None:
    web = (PROJECT_ROOT / "systemd/division-overtime-web.service").read_text(encoding="utf-8")

    assert "ExecStart=/home/pi/division-overtime/.venv/bin/division-overtime-web" in web
    assert "division-overtime-threshold" not in web
    assert "division-overtime-weekly" not in web
    assert "division-overtime-health" not in web


def test_release_checklist_documents_required_production_checks() -> None:
    checklist = (PROJECT_ROOT / "docs/release-checklist.md").read_text(encoding="utf-8")

    required = [
        ".\\scripts\\verify.ps1",
        "git diff --check",
        "./scripts/deploy.sh",
        "/api/system/health",
        "database status",
        "employees check-consistency",
        "git tag -a vX.Y.Z",
        "gh release create vX.Y.Z",
    ]
    for text in required:
        assert text in checklist

    assert "npm依存インストール成功" in checklist
    assert "npm auditの警告がある場合" in checklist
    assert "npm auditで既知の脆弱性なし" not in checklist


def test_frontend_initial_auth_check_uses_status_endpoint() -> None:
    app = (PROJECT_ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")

    assert 'fetch("/api/auth/status"' in app
    assert 'fetch("/api/auth/me"' not in app


def test_legacy_health_endpoint_is_not_documented_or_scripted() -> None:
    targets = [
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "docs/release-checklist.md",
        PROJECT_ROOT / "docs/operations.md",
        PROJECT_ROOT / "scripts/deploy.sh",
        PROJECT_ROOT / "scripts/verify.sh",
    ]

    for path in targets:
        text = path.read_text(encoding="utf-8")
        assert "/api/health" not in text, path

    for path in targets[:4]:
        assert "/api/system/health" in path.read_text(encoding="utf-8"), path


def test_ci_runs_required_checks_without_production_actions() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    required = [
        "pull_request:",
        "workflow_dispatch:",
        "concurrency:",
        "cancel-in-progress: true",
        'python-version: "3.13"',
        "astral-sh/setup-uv@",
        'version: "0.11.32"',
        "enable-cache: true",
        "cache-dependency-glob: uv.lock",
        "uv sync --locked --extra web --extra dev",
        "uv run python scripts/check_version.py --root .",
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run pytest -q",
        "cache: npm",
        "cache-dependency-path: frontend/package-lock.json",
        "npm ci",
        "npm run build",
    ]
    for text in required:
        assert text in workflow

    forbidden = [
        "push:",
        "scripts/deploy.sh",
        "KOT_TOKEN",
        "SLACK_BOT_TOKEN",
        "gh release",
        "git tag",
    ]
    for text in forbidden:
        assert text not in workflow


def test_documentation_matches_ci_and_main_protection_rules() -> None:
    deployment = (PROJECT_ROOT / "docs/deployment.md").read_text(encoding="utf-8")
    checklist = (PROJECT_ROOT / "docs/release-checklist.md").read_text(encoding="utf-8")

    for text in [
        "PR",
        "squash merge",
        "mainへ直接commitしない",
    ]:
        assert text in deployment

    for text in [
        "CI結果を確認",
        "squash merge",
        "force push",
        "Closes #Issue番号",
        "CIはmergeの必須条件ではなく",
        "必須ステータスチェックには設定せず",
    ]:
        assert text in checklist


def test_windows_uv_development_environment_is_documented() -> None:
    development = (PROJECT_ROOT / "docs/development.md").read_text(encoding="utf-8")
    python_version = (PROJECT_ROOT / ".python-version").read_text(encoding="utf-8").strip()

    assert python_version == "3.13"
    for text in [
        "uv sync --frozen --extra web --extra dev",
        "uv run python .\\scripts\\check_version.py --root .",
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run pytest -q",
        "Python 3.13",
        "Node.js 22",
    ]:
        assert text in development


def test_windows_local_verify_script_is_safe_and_documented() -> None:
    script = (PROJECT_ROOT / "scripts/verify.ps1").read_text(encoding="utf-8")
    development = (PROJECT_ROOT / "docs/development.md").read_text(encoding="utf-8")
    deployment = (PROJECT_ROOT / "docs/deployment.md").read_text(encoding="utf-8")
    checklist = (PROJECT_ROOT / "docs/release-checklist.md").read_text(encoding="utf-8")

    required = [
        '$ErrorActionPreference = "Stop"',
        'Assert-Command -Name "uv"',
        'Assert-Command -Name "npm"',
        'Assert-Command -Name "git"',
        '"sync", "--frozen", "--extra", "web", "--extra", "dev"',
        '"run", "python", ".\\scripts\\check_version.py", "--root", "."',
        '"run", "ruff", "check", "."',
        '"run", "ruff", "format", "--check", "."',
        '"run", "pytest", "-q"',
        '"ci"',
        '"run", "build"',
        '"diff", "--check"',
        "Set-Location $InitialLocation",
        "Local verification completed successfully.",
    ]
    for text in required:
        assert text in script

    forbidden = ["git push", "git commit", "scripts/deploy.sh", "/api/system/health"]
    for text in forbidden:
        assert text not in script

    for document in [development, deployment, checklist]:
        assert ".\\scripts\\verify.ps1" in document


def test_frontend_deployment_script_is_limited_and_safe() -> None:
    script = (PROJECT_ROOT / "scripts/deploy-frontend.ps1").read_text(encoding="utf-8")
    development = (PROJECT_ROOT / "docs/development.md").read_text(encoding="utf-8")
    deployment = (PROJECT_ROOT / "docs/deployment.md").read_text(encoding="utf-8")
    frontend = json.loads((PROJECT_ROOT / "frontend/package.json").read_text(encoding="utf-8"))

    for text in [
        "[Parameter(Mandatory)]",
        "[string]$Target",
        "git status --porcelain",
        "npm",
        '@("ci")',
        '@("run", "build")',
        "frontend/dist/index.html",
        "var/backups/frontend-dist",
        "frontendBuilt",
        "/api/system/health",
        "Version mismatch",
        "Restoring the previous dist",
    ]:
        assert text in script

    for forbidden in [
        "pip install",
        "division-overtime-threshold",
        "division-overtime-weekly",
        "division-overtime-health.timer",
        "data/employeeKey.csv",
        "var/division_overtime.sqlite3",
    ]:
        assert forbidden not in script

    assert ".\\scripts\\deploy-frontend.ps1" in development
    assert "正式リリース" in development
    assert "./scripts/deploy.sh" in development
    assert "正式デプロイ" in deployment
    assert "./scripts/deploy.sh" in deployment

    assert frontend["engines"]["node"] == ">=20.19.0 <25"
    assert frontend["engines"]["npm"] == ">=9.2.0"


def test_frontend_quality_checks_are_configured() -> None:
    frontend = json.loads((PROJECT_ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    verify_script = (PROJECT_ROOT / "scripts/verify.ps1").read_text(encoding="utf-8")
    ci = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    development = (PROJECT_ROOT / "docs/development.md").read_text(encoding="utf-8")

    assert frontend["scripts"]["lint"].startswith("oxlint ")
    assert frontend["scripts"]["test"] == "vitest run"
    assert frontend["scripts"]["test:watch"] == "vitest"

    for dependency in [
        "oxlint",
        "vitest",
        "@testing-library/react",
        "@testing-library/jest-dom",
        "jsdom",
    ]:
        assert dependency in frontend["devDependencies"]

    for path in [
        "frontend/vitest.config.ts",
        "frontend/tests/setup.ts",
        "frontend/tests/App.test.tsx",
    ]:
        assert (PROJECT_ROOT / path).is_file()

    for text in [
        '"run", "lint"',
        '"run", "test"',
        '"run", "build"',
    ]:
        assert text in verify_script

    for text in ["npm run lint", "npm run test", "npm run build"]:
        assert text in ci
        assert text in development


def test_frontend_uses_react_19() -> None:
    frontend = json.loads((PROJECT_ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    development = (PROJECT_ROOT / "docs/development.md").read_text(encoding="utf-8")

    assert frontend["dependencies"]["react"].startswith("^19.2.")
    assert frontend["dependencies"]["react-dom"].startswith("^19.2.")
    assert frontend["devDependencies"]["@types/react"].startswith("^19.2.")
    assert frontend["devDependencies"]["@types/react-dom"].startswith("^19.2.")
    assert "React 19.2系" in development


def test_frontend_uses_vite_8() -> None:
    frontend = json.loads((PROJECT_ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    development = (PROJECT_ROOT / "docs/development.md").read_text(encoding="utf-8")

    assert frontend["devDependencies"]["vite"].startswith("^8.1.")
    assert frontend["devDependencies"]["@vitejs/plugin-react"].startswith("^6.")
    assert "Vite 8.1系" in development


def test_frontend_uses_typescript_6() -> None:
    frontend = json.loads((PROJECT_ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    development = (PROJECT_ROOT / "docs/development.md").read_text(encoding="utf-8")

    assert frontend["devDependencies"]["typescript"].startswith("^6.0.")
    assert "TypeScript 6.0系" in development
    assert "ignoreDeprecations" not in json.dumps(
        [
            json.loads((PROJECT_ROOT / "frontend/tsconfig.json").read_text(encoding="utf-8")),
            json.loads((PROJECT_ROOT / "frontend/tsconfig.app.json").read_text(encoding="utf-8")),
            json.loads((PROJECT_ROOT / "frontend/tsconfig.node.json").read_text(encoding="utf-8")),
        ]
    )


def test_verify_reports_employee_count_breakdown_and_consistency() -> None:
    verify = (PROJECT_ROOT / "scripts/verify.sh").read_text(encoding="utf-8")

    assert "database status" in verify
    assert "employees check-consistency" in verify
    assert verify.index("database status") < verify.index("employees check-consistency")
    assert verify.index("employees check-consistency") < verify.index(" health")

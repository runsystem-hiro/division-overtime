from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_public_versions_are_2_0_3_and_consistent() -> None:
    expected = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as handle:
        python_version = tomllib.load(handle)["project"]["version"]
    frontend = json.loads((PROJECT_ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    lock = json.loads((PROJECT_ROOT / "frontend/package-lock.json").read_text(encoding="utf-8"))
    module_text = (PROJECT_ROOT / "src/division_overtime/__init__.py").read_text(encoding="utf-8")

    assert expected == "2.0.3"
    assert python_version == expected
    assert frontend["version"] == expected
    assert lock["version"] == expected
    assert lock["packages"][""]["version"] == expected
    assert f'__version__ = "{expected}"' in module_text


def test_version_check_script_succeeds() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_version.py", "--root", str(PROJECT_ROOT)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "version_check=ok version=2.0.3"


def test_verify_and_deploy_enforce_version_checks() -> None:
    verify = (PROJECT_ROOT / "scripts/verify.sh").read_text(encoding="utf-8")
    deploy = (PROJECT_ROOT / "scripts/deploy.sh").read_text(encoding="utf-8")

    assert 'scripts/check_version.py --root "$PROJECT_ROOT"' in verify
    pull_position = deploy.index("git pull --ff-only")
    version_position = deploy.index('EXPECTED_VERSION="$(<"$PROJECT_ROOT/VERSION")"')

    assert version_position > pull_position
    assert 'if [[ "$ACTUAL_VERSION" != "$EXPECTED_VERSION" ]]' in deploy
    assert "Deployment completed. version=$ACTUAL_VERSION" in deploy


def test_web_service_is_independent_from_notification_units() -> None:
    web = (PROJECT_ROOT / "systemd/division-overtime-web.service").read_text(encoding="utf-8")

    assert "ExecStart=/home/pi/division-overtime/.venv/bin/division-overtime-web" in web
    assert "division-overtime-threshold" not in web
    assert "division-overtime-weekly" not in web
    assert "division-overtime-health" not in web


def test_release_checklist_documents_required_production_checks() -> None:
    checklist = (PROJECT_ROOT / "docs/release-checklist.md").read_text(encoding="utf-8")

    required = [
        "python .\\scripts\\check_version.py --root .",
        "ruff check .",
        "pytest -q",
        "npm run build",
        "./scripts/deploy.sh",
        "/api/system/health",
        "sudo systemctl stop division-overtime-web.service",
        "employees check-consistency",
        "git tag -a v2.0.3",
        "gh release create v2.0.3",
    ]
    for text in required:
        assert text in checklist

    for text in [
        "本番Slack表示確認を伴う通知テスト",
        ".backup '$BACKUP'",
        "TEST_RUN_ID='<テスト実行のrun_id>'",
        "BEGIN IMMEDIATE;",
        "notification_type = 'weekly'",
        "PRAGMA integrity_check;",
    ]:
        assert text in checklist


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
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    operations = (PROJECT_ROOT / "docs/operations.md").read_text(encoding="utf-8")
    checklist = (PROJECT_ROOT / "docs/release-checklist.md").read_text(encoding="utf-8")

    for text in [
        "squash merge",
        "force push",
        "Pull Request",
        "必須ステータスチェックには設定せず",
    ]:
        assert text in readme

    for text in [
        "squash merge",
        "force push",
        "必須ゲートではなく補助確認",
    ]:
        assert text in operations

    for text in [
        "CI結果を確認",
        "squash merge",
        "Closes #Issue番号",
        "CIはmergeの必須条件ではない",
    ]:
        assert text in checklist


def test_windows_uv_development_environment_is_documented() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    python_version = (PROJECT_ROOT / ".python-version").read_text(encoding="utf-8").strip()

    assert python_version == "3.13"
    for text in [
        "uv sync --frozen --extra web --extra dev",
        "uv run python .\\scripts\\check_version.py --root .",
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run pytest -q",
        "既存のvenv / pip手順も当面利用できます",
        "Raspberry Piでは従来どおり",
    ]:
        assert text in readme


def test_windows_local_verify_script_is_safe_and_documented() -> None:
    script = (PROJECT_ROOT / "scripts/verify.ps1").read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    operations = (PROJECT_ROOT / "docs/operations.md").read_text(encoding="utf-8")
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

    for document in [readme, operations, checklist]:
        assert ".\\scripts\\verify.ps1" in document


def test_frontend_deployment_script_is_limited_and_safe() -> None:
    script = (PROJECT_ROOT / "scripts/deploy-frontend.ps1").read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    operations = (PROJECT_ROOT / "docs/operations.md").read_text(encoding="utf-8")
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

    for document in [readme, operations]:
        assert ".\\scripts\\deploy-frontend.ps1" in document
        assert "正式リリース" in document
        assert "scripts/deploy.sh" in document

    assert frontend["engines"]["node"] == ">=20.19.0 <25"
    assert frontend["engines"]["npm"] == ">=9.2.0"

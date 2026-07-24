from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_public_versions_are_2_0_2_and_consistent() -> None:
    expected = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as handle:
        python_version = tomllib.load(handle)["project"]["version"]
    frontend = json.loads((PROJECT_ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    lock = json.loads((PROJECT_ROOT / "frontend/package-lock.json").read_text(encoding="utf-8"))
    module_text = (PROJECT_ROOT / "src/division_overtime/__init__.py").read_text(encoding="utf-8")

    assert expected == "2.0.2"
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
    assert result.stdout.strip() == "version_check=ok version=2.0.2"


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
        "git tag -a v2.0.2",
        "gh release create v2.0.2",
    ]
    for text in required:
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
        "branches:",
        'python-version: "3.13"',
        "python scripts/check_version.py --root .",
        "ruff check .",
        "ruff format --check .",
        "pytest -q",
        "npm ci",
        "npm run build",
    ]
    for text in required:
        assert text in workflow

    forbidden = [
        "scripts/deploy.sh",
        "KOT_TOKEN",
        "SLACK_BOT_TOKEN",
        "gh release",
        "git tag",
    ]
    for text in forbidden:
        assert text not in workflow

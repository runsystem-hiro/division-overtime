import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_verify_sh_supports_development_without_leaking_environment_to_pytest():
    script = (ROOT / "scripts/verify.sh").read_text(encoding="utf-8")

    assert "--environment" in script
    assert 'ENVIRONMENT="production"' in script
    assert "env -u DIVISION_OVERTIME_ENV uv run pytest -q" in script
    assert (
        'DIVISION_OVERTIME_ENV=development uv run division-overtime --root "$PROJECT_ROOT" '
        "validate-config"
    ) in script
    assert (
        'DIVISION_OVERTIME_ENV=production "$VENV_BIN/division-overtime" '
        '--root "$PROJECT_ROOT" validate-config'
    ) in script


def test_verify_sh_rejects_unsupported_environment_before_running_checks():
    result = subprocess.run(
        [str(ROOT / "scripts/verify.sh"), "--environment", "staging"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Unsupported environment: staging" in result.stderr


def test_verify_ps1_runs_environment_checks_after_pytest():
    script = (ROOT / "scripts/verify.ps1").read_text(encoding="utf-8")

    clear_index = script.index("Remove-Item Env:DIVISION_OVERTIME_ENV")
    pytest_index = script.index('-Label "Run pytest"')
    environment_index = script.index('$env:DIVISION_OVERTIME_ENV = "development"')
    validate_index = script.index('-Label "Validate development configuration"')

    assert clear_index < pytest_index < environment_index < validate_index
    assert '-Label "Check development database"' in script
    assert '-Label "Check development employee consistency"' in script
    assert '-Label "Check development health"' in script

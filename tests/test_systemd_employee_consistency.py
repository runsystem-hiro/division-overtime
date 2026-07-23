from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SYSTEMD_DIR = PROJECT_ROOT / "systemd"


def test_employee_consistency_service_limits_writes_to_data_and_var() -> None:
    service = (SYSTEMD_DIR / "division-overtime-employee-consistency.service").read_text(
        encoding="utf-8"
    )

    assert "Type=oneshot" in service
    assert "User=pi" in service
    assert "WorkingDirectory=/home/pi/division-overtime" in service
    assert (
        "ExecStart=/home/pi/division-overtime/.venv/bin/division-overtime "
        "--root /home/pi/division-overtime employees record-consistency"
    ) in service
    assert "ProtectSystem=strict" in service
    assert "ProtectHome=read-only" in service
    assert (
        "ReadWritePaths=/home/pi/division-overtime/data /home/pi/division-overtime/var"
    ) in service


def test_employee_consistency_timer_runs_daily_and_is_persistent() -> None:
    timer = (SYSTEMD_DIR / "division-overtime-employee-consistency.timer").read_text(
        encoding="utf-8"
    )

    assert "OnCalendar=*-*-* 03:15:00" in timer
    assert "Persistent=true" in timer
    assert "Unit=division-overtime-employee-consistency.service" in timer
    assert "WantedBy=timers.target" in timer


def test_deploy_installs_and_enables_employee_consistency_timer() -> None:
    deploy = (PROJECT_ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")

    assert 'EMPLOYEE_CONSISTENCY_SERVICE="division-overtime-employee-consistency.service"' in deploy
    assert 'EMPLOYEE_CONSISTENCY_TIMER="division-overtime-employee-consistency.timer"' in deploy
    assert 'sudo systemctl enable --now "$EMPLOYEE_CONSISTENCY_TIMER"' in deploy

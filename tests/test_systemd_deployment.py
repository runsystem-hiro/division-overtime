from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SYSTEMD_DIR = PROJECT_ROOT / "systemd"


def test_notification_services_mark_timer_runs() -> None:
    expected = {
        "division-overtime-threshold.service": "run threshold --source timer",
        "division-overtime-weekly.service": "run weekly --source timer",
    }

    for filename, command in expected.items():
        service = (SYSTEMD_DIR / filename).read_text(encoding="utf-8")
        assert command in service


def test_deploy_installs_and_verifies_all_systemd_units() -> None:
    deploy = (PROJECT_ROOT / "scripts/deploy.sh").read_text(encoding="utf-8")

    units = [
        "division-overtime-threshold.service",
        "division-overtime-threshold.timer",
        "division-overtime-weekly.service",
        "division-overtime-weekly.timer",
        "division-overtime-health.service",
        "division-overtime-health.timer",
        "division-overtime-employee-consistency.service",
        "division-overtime-employee-consistency.timer",
        "division-overtime-web.service",
    ]
    timers = [
        "division-overtime-threshold.timer",
        "division-overtime-weekly.timer",
        "division-overtime-health.timer",
        "division-overtime-employee-consistency.timer",
    ]

    assert 'SYSTEMD_UNIT_DIR="/etc/systemd/system"' in deploy
    for unit in units:
        assert unit in deploy
    assert 'sudo install -m 0644 "systemd/$unit" "$SYSTEMD_UNIT_DIR/$unit"' in deploy
    assert "sudo systemctl daemon-reload" in deploy
    assert 'cmp -s "systemd/$unit" "$SYSTEMD_UNIT_DIR/$unit"' in deploy
    assert "installed systemd unit differs from repository" in deploy
    for timer in timers:
        assert timer in deploy
    assert 'sudo systemctl enable --now "${SYSTEMD_TIMERS[@]}"' in deploy


def test_systemd_deployment_is_documented() -> None:
    deployment = (PROJECT_ROOT / "docs/deployment.md").read_text(encoding="utf-8")
    operations = (PROJECT_ROOT / "docs/operations.md").read_text(encoding="utf-8")

    for text in [
        "全systemd unit",
        "リポジトリ内定義と一致",
        "systemctl cat division-overtime-threshold.service",
        "systemctl cat division-overtime-weekly.service",
        "--source timer",
    ]:
        assert text in deployment

    assert "正式デプロイ時に`/etc/systemd/system/`へ反映" in operations
    assert "systemctl cat division-overtime-threshold.service" in operations
    assert "systemctl cat division-overtime-weekly.service" in operations

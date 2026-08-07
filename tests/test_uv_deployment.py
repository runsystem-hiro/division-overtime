from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_deploy_uses_frozen_uv_sync_without_changing_venv_path() -> None:
    deploy = (PROJECT_ROOT / "scripts/deploy.sh").read_text(encoding="utf-8")

    assert "require_command uv" in deploy
    assert "uv sync --frozen --extra web --extra dev" in deploy
    assert "-m pip install" not in deploy
    assert 'VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"' in deploy


def test_install_uses_frozen_uv_sync() -> None:
    install = (PROJECT_ROOT / "scripts/install.sh").read_text(encoding="utf-8")

    assert "command -v uv" in install
    assert "uv sync --frozen --extra web --extra dev" in install
    assert "python3 -m venv" not in install
    assert "pip install" not in install


def test_uv_production_migration_is_documented() -> None:
    deployment = (PROJECT_ROOT / "docs/deployment.md").read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "Raspberry Piへのuv導入" in deployment
    assert "uv sync --frozen --extra web --extra dev" in deployment
    assert "uv移行時のロールバック" in deployment
    assert "本番Raspberry Piでもuvを使用" in readme

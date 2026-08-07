from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts/run_with_env.py"


def load_module():
    spec = importlib.util.spec_from_file_location("run_with_env", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_environment_loads_dotenv_without_overriding_existing_values(
    tmp_path: Path,
) -> None:
    module = load_module()
    env_file = tmp_path / ".env"
    env_file.write_text(
        "FROM_FILE=file-value\n"
        "EXISTING=file-value\n"
        "QUOTED='value with spaces'\n"
        "REFERENCE=${FROM_FILE}\n",
        encoding="utf-8",
    )

    environment = module.build_environment(env_file, {"EXISTING": "shell-value"})

    assert environment["FROM_FILE"] == "file-value"
    assert environment["EXISTING"] == "shell-value"
    assert environment["QUOTED"] == "value with spaces"
    assert environment["REFERENCE"] == "${FROM_FILE}"


def test_main_rejects_missing_environment_file(tmp_path: Path, monkeypatch, capsys) -> None:
    module = load_module()
    monkeypatch.setattr(
        module.sys,
        "argv",
        [str(SCRIPT), str(tmp_path / "missing.env"), "true"],
    )

    assert module.main() == 2
    assert "Environment file was not found" in capsys.readouterr().err

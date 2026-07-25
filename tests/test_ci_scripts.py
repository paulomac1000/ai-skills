"""Executable contracts for bounded local CI and exact-lock installation helpers."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from scripts import select_lock

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("select_lock", select_lock)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_lock_selector_cli_and_normalization_fail_closed(capsys) -> None:
    assert select_lock.main(["--platform", "linux", "--architecture", "AMD64", "--python-version", "03.013"]) == 0
    assert capsys.readouterr().out.strip() == "requirements-dev-linux-x64-py313.lock"
    with pytest.raises(RuntimeError, match="architecture"):
        select_lock.normalize_architecture("sparc")
    with pytest.raises(RuntimeError, match="invalid Python"):
        select_lock.normalize_python_version("3")
    with pytest.raises(RuntimeError, match="unsupported lock target"):
        select_lock.lock_id("linux", "x64", "3.15")


def test_install_locked_uses_exact_file_hash_enforcement_and_pip_check(monkeypatch, tmp_path: Path) -> None:
    installer = load(ROOT / "scripts/install_locked.py", "install_locked_contract")
    lock = tmp_path / "requirements.lock"
    lock.write_text("pytest==9.1.1 --hash=sha256:" + "a" * 64 + "\n", encoding="utf-8")
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(installer, "selected_lock", lambda: lock)
    monkeypatch.setattr(
        installer.subprocess,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs)),
    )
    assert installer.main() == 0
    assert calls[0][0] == [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--require-hashes",
        "-r",
        str(lock),
    ]
    assert calls[0][1] == {"check": True, "timeout": 900}
    assert calls[1][0] == [sys.executable, "-m", "pip", "check"]
    assert calls[1][1] == {"check": True, "timeout": 120}


def test_local_ci_runs_every_bounded_gate(monkeypatch, tmp_path: Path) -> None:
    ci = load(ROOT / "scripts/ci.py", "local_ci_contract")
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(ci.compileall, "compile_dir", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(ci, "run", lambda *command: calls.append(command))
    monkeypatch.setattr(ci, "selected_lock", lambda: tmp_path / "target.lock")
    assert ci.main() == 0
    flattened = [" ".join(command) for command in calls]
    assert any("ruff check" in command for command in flattened)
    assert any("mypy" in command for command in flattened)
    assert any("bandit" in command for command in flattened)
    assert any("pip_audit" in command and "target.lock" in command for command in flattened)
    assert any("coverage run --branch" in command for command in flattened)
    assert sum("coverage report" in command for command in flattened) >= 3


def test_local_ci_run_wrapper_is_bounded(monkeypatch) -> None:
    ci = load(ROOT / "scripts/ci.py", "local_ci_run_contract")
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed.update(kwargs)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(ci.subprocess, "run", fake_run)
    ci.run("python", "-V")
    assert observed["command"] == ("python", "-V")
    assert observed["cwd"] == ROOT
    assert observed["check"] is True
    assert observed["timeout"] == ci.COMMAND_TIMEOUT_SECONDS


def test_local_ci_stops_when_compilation_fails(monkeypatch) -> None:
    ci = load(ROOT / "scripts/ci.py", "local_ci_compile_failure")
    monkeypatch.setattr(ci.compileall, "compile_dir", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(ci, "run", lambda *_command: pytest.fail("quality commands must not run"))
    assert ci.main() == 1

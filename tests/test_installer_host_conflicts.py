"""Regression: pip-check host-package conflicts never mask lock-graph breakage."""

import importlib.util
import sys
from pathlib import Path

from scripts import select_lock

PATH = Path(__file__).resolve().parents[1] / "scripts/install_locked.py"
spec = importlib.util.spec_from_file_location("install_locked_probe", PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules.setdefault("select_lock", select_lock)
spec.loader.exec_module(mod)


def test_unmanaged_runner_distribution_is_diagnostic_only():
    lock = "filelock==3.32.0\npackaging==26.2\nplatformdirs==4.11.0\n"
    report = (
        "pipx 1.17.12 has requirement filelock>=4.0.9, but you have filelock 3.32.0.\n"
        "pipx 1.17.12 requires packaging>=26.3, but you have packaging 26.2.\n"
    )
    blocked, ignored = mod.classify_pip_check(report, lock)
    assert blocked == []
    assert len(ignored) == 2


def test_locked_distribution_conflicts_remain_fatal():
    lock = "mcp==2.2.0\nfilelock==3.32.0\n"
    report = "mcp 2.2.0 has requirement filelock>=4, but you have filelock 3.32.0.\n"
    blocked, ignored = mod.classify_pip_check(report, lock)
    assert len(blocked) == 1 and ignored == []


def test_main_rejects_stderr_even_when_stdout_only_names_unmanaged_host(tmp_path, monkeypatch):
    import subprocess

    import pytest

    lock = tmp_path / "selected.lock"
    lock.write_text("filelock==3.32.0\n", encoding="utf-8")
    monkeypatch.setattr(mod, "selected_lock", lambda: lock)

    def run(command, **kwargs):
        if "install" in command:
            return subprocess.CompletedProcess(command, 0)
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="pipx 1.17.12 requires filelock>=4, but you have filelock 3.32.0.\n",
            stderr="ERROR: pip check could not inspect all packages",
        )

    monkeypatch.setattr(mod.subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        mod.main()


def test_main_accepts_only_unmanaged_conflict_when_stderr_empty(tmp_path, monkeypatch):
    import subprocess

    lock = tmp_path / "selected.lock"
    lock.write_text("filelock==3.32.0\n", encoding="utf-8")
    monkeypatch.setattr(mod, "selected_lock", lambda: lock)

    def run(command, **kwargs):
        if "install" in command:
            return subprocess.CompletedProcess(command, 0)
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="pipx 1.17.12 requires filelock>=4, but you have filelock 3.32.0.\n",
            stderr="",
        )

    monkeypatch.setattr(mod.subprocess, "run", run)
    assert mod.main() == 0


def test_unknown_failure_or_unpinned_lock_fails_closed():
    assert mod.classify_pip_check("unexpected resolver failure", "mcp==2.2.0")[0]
    assert mod.classify_pip_check("pipx 1.0 requires x>=2, but you have x 1", "")[0]

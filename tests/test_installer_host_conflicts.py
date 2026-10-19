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


def test_pep503_locked_name_cannot_be_downgraded_to_unmanaged():
    lock = "zope.interface==7.2\nmy__package...core==1.0\n"
    report = (
        "zope-interface 7.2 requires setuptools>=90, but you have setuptools 70.\n"
        "my-package-core 1.0 requires packaging>=99, but you have packaging 25.\n"
    )
    blocked, unmanaged = mod.classify_pip_check(report, lock)
    assert len(blocked) == 2
    assert unmanaged == []


def test_unmanaged_host_report_cannot_hide_missing_locked_package():
    lock = "filelock==3.32.0\npackaging==26.2\n"
    report = (
        "pipx 1.0 requires filelock, which is not installed.\n"
        "some-tool 2.0 requires packaging>=27, which is not installed.\n"
        "other-host-tool 4.0 requires unpinned-lib, which is not installed.\n"
    )
    blocking, unmanaged = mod.classify_pip_check(report, lock)
    assert len(blocking) == 2
    assert len(unmanaged) == 1
    assert "unpinned-lib" in unmanaged[0]


def test_verify_only_blocks_missing_locked_package_from_unmanaged_host(tmp_path, monkeypatch):
    import subprocess

    import pytest

    lock = tmp_path / "selected.lock"
    lock.write_text("filelock==3.32.0\n", encoding="utf-8")
    monkeypatch.setattr(mod, "selected_lock", lambda: lock)

    def run(command, **kwargs):
        assert command[-2:] == ["pip", "check"]
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="pipx 1.0 requires filelock, which is not installed.\n",
            stderr="",
        )

    monkeypatch.setattr(mod.subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        mod.main(verify_only=True)


def test_lock_inventory_fails_on_missing_and_replaced_versions(monkeypatch):
    import importlib.metadata

    def installed(name):
        if name == "filelock":
            raise importlib.metadata.PackageNotFoundError(name)
        if name == "zope-interface":
            return "7.1"
        raise AssertionError(name)

    monkeypatch.setattr(mod.metadata, "version", installed)
    failures = mod._locked_inventory_findings("filelock==3.32.0\nzope.interface==7.2\n")
    assert "locked_distribution_missing:filelock==3.32.0" in failures
    assert "locked_distribution_version_mismatch:zope-interface==7.2:installed=7.1" in failures


def test_lock_inventory_compares_versions_under_pep440_canonicalization(monkeypatch):
    def installed(name):
        if name == "filelock":
            return "3.32.0"
        if name == "zope-interface":
            return "7.2.0rc1"
        raise AssertionError(name)

    monkeypatch.setattr(mod.metadata, "version", installed)
    assert mod._locked_inventory_findings("filelock==3.32.0\nzope.interface==7.2.0-rc1\n") == []


def test_lock_inventory_rejects_a_different_installed_release(monkeypatch):
    def installed(name):
        if name == "zope-interface":
            return "7.2.0rc2"
        raise AssertionError(name)

    monkeypatch.setattr(mod.metadata, "version", installed)
    failures = mod._locked_inventory_findings("zope.interface==7.2.0-rc1\n")
    assert failures == ["locked_distribution_version_mismatch:zope-interface==7.2.0-rc1:installed=7.2.0rc2"]


def test_lock_inventory_fails_closed_on_a_non_conforming_installed_version(monkeypatch):
    def installed(name):
        if name == "zope-interface":
            return "not-a-version"
        raise AssertionError(name)

    monkeypatch.setattr(mod.metadata, "version", installed)
    failures = mod._locked_inventory_findings("zope.interface==7.2\n")
    assert failures == ["locked_distribution_version_mismatch:zope-interface==7.2:installed=not-a-version"]


def test_lock_inventory_reports_a_missing_packaging_dependency(monkeypatch):
    import pytest

    monkeypatch.setitem(sys.modules, "packaging.version", None)
    with pytest.raises(mod.LockedInventoryUnavailable) as failure:
        mod._locked_inventory_findings("filelock==3.32.0\n")
    assert "packaging is required" in str(failure.value)


def test_main_reports_an_unavailable_locked_inventory_dependency(tmp_path, monkeypatch, capsys):
    import subprocess

    import pytest

    lock = tmp_path / "selected.lock"
    lock.write_text("filelock==3.32.0\n", encoding="utf-8")
    monkeypatch.setattr(mod, "selected_lock", lambda: lock)
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, stdout="", stderr=""),
    )
    monkeypatch.setitem(sys.modules, "packaging.version", None)
    with pytest.raises(SystemExit) as failure:
        mod.main(verify_only=True)
    assert failure.value.code == 1
    assert "LOCK_INVENTORY_UNAVAILABLE" in capsys.readouterr().err


def test_verify_only_rejects_pip_check_success_with_wrong_locked_versions(tmp_path, monkeypatch):
    import subprocess

    import pytest

    lock = tmp_path / "selected.lock"
    lock.write_text("filelock==3.32.0\n", encoding="utf-8")
    monkeypatch.setattr(mod, "selected_lock", lambda: lock)
    monkeypatch.setattr(
        mod, "_locked_inventory_findings", lambda _: ["locked_distribution_missing:filelock==3.32.0"]
    )
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, stdout="", stderr=""),
    )
    with pytest.raises(subprocess.CalledProcessError):
        mod.main(verify_only=True)


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
    monkeypatch.setattr(mod, "_locked_inventory_findings", lambda _: [])

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


def test_verify_only_reuses_host_conflict_classification(tmp_path, monkeypatch):
    import subprocess

    lock = tmp_path / "selected.lock"
    lock.write_text("filelock==3.32.0\n", encoding="utf-8")
    monkeypatch.setattr(mod, "selected_lock", lambda: lock)
    monkeypatch.setattr(mod, "_locked_inventory_findings", lambda _: [])
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        assert "install" not in command
        return subprocess.CompletedProcess(
            command, 1,
            stdout="pipx 1.17.12 requires filelock>=4, but you have filelock 3.32.0.\n",
            stderr="",
        )

    monkeypatch.setattr(mod.subprocess, "run", run)
    assert mod.main(verify_only=True) == 0
    assert len(commands) == 1
    assert commands[0][-2:] == ["pip", "check"]


def test_unknown_failure_or_unpinned_lock_fails_closed():
    assert mod.classify_pip_check("unexpected resolver failure", "mcp==2.2.0")[0]
    assert mod.classify_pip_check("pipx 1.0 requires x>=2, but you have x 1", "")[0]

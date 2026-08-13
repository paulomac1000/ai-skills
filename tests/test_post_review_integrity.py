"""Regressions for the final portability and fail-closed review findings."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from contracts.run_evidence_command import main as run_evidence_command
from contracts.validate_consumer_feedback import validate_registry
from contracts.validate_trusted_executable_sources import _git, _repository_from_remote
from scripts import check_release_version
from scripts.ci_environment import configured_passthrough

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills/mcp-server-architect/tools"


def _load(name: str, path: Path):
    tools = str(path.parent)
    inserted = tools not in sys.path
    if inserted:
        sys.path.insert(0, tools)
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted:
            sys.path.remove(tools)


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return f'"{pid}"' in completed.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_consumer_feedback_owner_read_failure_becomes_finding(tmp_path: Path) -> None:
    (tmp_path / "contracts").mkdir()
    (tmp_path / "skills/example").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "contracts/consumer-canaries.yaml").write_text("schema_version: 1\ncanaries: []\n", encoding="utf-8")
    (tmp_path / "skills/example/guide.md").write_bytes(b"# Guide\n\xff\n")
    (tmp_path / "tests/test_example.py").write_text("def test_example():\n    assert True\n", encoding="utf-8")
    registry = {
        "schema_version": 1,
        "incidents": [
            {
                "id": "field.owner-read-failure",
                "source_kind": "field-report",
                "failure_mode": "The owner document became unreadable after path validation.",
                "generalized_invariant": "Owner read failures must be deterministic findings rather than tracebacks.",
                "canonical_owner": "skills/example/guide.md#owner",
                "regression_selectors": ["tests/test_example.py::test_example"],
                "status": "implemented",
            }
        ],
    }
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump(registry), encoding="utf-8")
    findings = validate_registry(path, repository_root=tmp_path)
    assert any("invalid canonical owner" in finding for finding in findings)


def test_trusted_git_ignores_global_config_and_plaintext_remote(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    observed: dict[str, object] = {}

    def fake_run(argv, **kwargs):
        observed["argv"] = argv
        observed["env"] = kwargs.get("env")
        return subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert _git(tmp_path, "rev-parse", "HEAD") == "ok"
    argv = observed["argv"]
    assert isinstance(argv, list)
    assert "core.fsmonitor=false" in argv
    assert "core.pager=cat" in argv
    environment = observed["env"]
    assert isinstance(environment, dict)
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert environment["GIT_CONFIG_GLOBAL"] == os.devnull
    assert environment["GIT_TERMINAL_PROMPT"] == "0"
    with pytest.raises(ValueError, match="secure GitHub"):
        _repository_from_remote("http://github.com/owner/repo.git")


def test_release_base_git_failure_is_a_finding(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_argv: list[str], _operation: str) -> str:
        raise ValueError("missing base object")

    monkeypatch.setattr(check_release_version, "_git_output", fail)
    findings = check_release_version.validate_version_bumps("f" * 40)
    assert findings == ["release base could not be validated: missing base object"]


def test_ci_passthrough_cannot_reintroduce_its_control_variable() -> None:
    source = {
        "AI_SKILLS_CI_PASSTHROUGH": "TOKEN,AI_SKILLS_CI_PASSTHROUGH,OTHER",
        "TOKEN": "secret",
        "OTHER": "value",
    }
    assert configured_passthrough(source) == ("OTHER", "TOKEN")


def test_canary_git_environment_keeps_windows_roots_and_lowercase_proxies(monkeypatch: pytest.MonkeyPatch) -> None:
    checker = _load("consumer_canary_environment", TOOLS / "check_consumer_canaries.py")
    for name in (
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "SYSTEMDRIVE",
        "https_proxy",
        "http_proxy",
        "no_proxy",
    ):
        monkeypatch.setenv(name, f"value-{name}")
    environment = checker._git_environment()
    for name in (
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "SYSTEMDRIVE",
        "https_proxy",
        "http_proxy",
        "no_proxy",
    ):
        assert environment[name] == f"value-{name}"


def test_hashed_requirement_continuations_preserve_exact_sdk_pin() -> None:
    planner = _load("adoption_planner_hashed_requirements", TOOLS / "plan_existing_project.py")
    entries = planner._logical_requirements(
        "mcp==2.0.0 \\\n    --hash=sha256:111 \\\n    --hash=sha256:222\nother==1.0.0\n"
    )
    assert entries == ["mcp==2.0.0", "other==1.0.0"]
    assert planner._is_exact_requirement("==2.0.0") is True


def test_evidence_timeout_kills_descendant_and_still_writes_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    child_pid = tmp_path / "child.pid"
    script = tmp_path / "spawn_child.py"
    script.write_text(
        "import pathlib, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid), encoding='utf-8')\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    output = tmp_path / "execution.json"
    status = run_evidence_command(
        [
            "--execution-id",
            "process-tree-timeout",
            "--timeout-seconds",
            "1",
            "--output",
            str(output),
            "--",
            sys.executable,
            str(script),
            str(child_pid),
        ]
    )
    assert status == 124
    record = json.loads(output.read_text(encoding="utf-8"))
    assert "exceeded timeout" in record["validation_error"]
    assert child_pid.is_file()
    pid = int(child_pid.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 5
    while _pid_alive(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _pid_alive(pid), f"evidence command descendant {pid} survived timeout"

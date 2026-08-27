"""Bounded-output and no-overwrite regressions for MCP public-contract capture."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "skills/mcp-server-architect/tools/capture_mcp_contract.py"


def _load_capture(name: str):
    spec = importlib.util.spec_from_file_location(name, CAPTURE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _snapshot() -> dict[str, object]:
    return {
        "format": "ai-skills-mcp-public-contract",
        "schema_version": 1,
        "source_revision": "c" * 40,
        "artifact": {
            "kind": "wheel",
            "identity": "sample.whl",
            "digest": "sha256:" + "1" * 64,
        },
        "server": {"name": "sample", "version": "1.0.0"},
        "sdk": {"profile": "python-official-mcp", "version": "2.0.0"},
        "transports": ["stdio"],
        "authentication": {"required": False, "mechanism": "none", "target_selection": "fixed"},
        "tools": [],
    }


def _args(output: Path, working_directory: Path, probe: Path, *probe_args: str) -> list[str]:
    return [
        "--output",
        str(output),
        "--working-directory",
        str(working_directory),
        "--expected-source-revision",
        "c" * 40,
        "--expected-artifact-digest",
        "sha256:" + "1" * 64,
        "--",
        sys.executable,
        str(probe),
        *probe_args,
    ]


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


def test_contract_probe_output_is_bounded_while_child_is_running(tmp_path: Path) -> None:
    capture = _load_capture("capture_probe_bounds")
    probe = tmp_path / "noisy.py"
    probe.write_text(
        "import sys\nsys.stdout.buffer.write(b'x' * (3 * 1024 * 1024))\nsys.stdout.flush()\n",
        encoding="utf-8",
    )
    output = tmp_path / "capture.json"
    with pytest.raises(SystemExit) as exc:
        capture.main(_args(output, tmp_path, probe))
    assert exc.value.code == 2
    assert not output.exists()


def test_contract_probe_timeout_terminates_descendant_process_tree(tmp_path: Path) -> None:
    capture = _load_capture("capture_probe_process_tree")
    child_pid = tmp_path / "child.pid"
    probe = tmp_path / "spawn_child.py"
    probe.write_text(
        "import pathlib, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid), encoding='utf-8')\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="exceeded timeout"):
        capture._run_probe([sys.executable, str(probe), str(child_pid)], tmp_path, 1)
    assert child_pid.is_file()
    pid = int(child_pid.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 5
    while _pid_alive(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _pid_alive(pid), f"probe descendant {pid} survived process-tree termination"


def test_contract_capture_closes_check_then_write_overwrite_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = _load_capture("capture_probe_exclusive_output")
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps(_snapshot()), encoding="utf-8")
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import pathlib, sys\nprint(pathlib.Path(sys.argv[1]).read_text())\n",
        encoding="utf-8",
    )
    output = tmp_path / "capture.json"
    output.write_text("must-survive\n", encoding="utf-8")
    monkeypatch.setattr(capture.os.path, "lexists", lambda _path: False)

    with pytest.raises(SystemExit) as exc:
        capture.main(_args(output, tmp_path, probe, str(snapshot)))
    assert exc.value.code == 2
    assert output.read_text(encoding="utf-8") == "must-survive\n"

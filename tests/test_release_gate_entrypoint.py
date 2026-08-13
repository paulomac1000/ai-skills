"""Regression for the exact stable-release gate entrypoint used by hosted CI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_release_gate_runs_as_script_without_pythonpath(tmp_path: Path) -> None:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_release_version.py"), "--base", head],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env={"PATH": __import__("os").environ.get("PATH", "")},
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

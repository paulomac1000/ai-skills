"""Regressions for the latest AGENTS.md evidence review."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills/agents-md-architect/tools"
sys.path.insert(0, str(TOOLS))

import audit_agents_md as audit_module  # noqa: E402


def _codes(findings: list[Any]) -> set[str]:
    return {item.code for item in findings}


def _agents(full_gate: str) -> str:
    return f"""# AGENTS.md

## Scope

These instructions apply to the repository.

## Commands and verification

- Full gate: `{full_gate}`

## Safety boundaries

Secrets must not be committed. Destructive writes require explicit authorization and rollback.

## Definition of done

Report the exact revision, skipped checks, and residual risk.
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_gitlab_variable_named_script_cannot_establish_gate_evidence(tmp_path: Path) -> None:
    _write(
        tmp_path / ".gitlab-ci.yml",
        """variables:
  script: python scripts/ghost.py

real_job:
  script: echo real gate
""",
    )
    _write(tmp_path / "AGENTS.md", _agents("python scripts/ghost.py"))

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")

    assert "commands.unlocated-full-gate" in _codes(findings)


def test_gitlab_top_level_job_script_establishes_gate_evidence(tmp_path: Path) -> None:
    _write(
        tmp_path / ".gitlab-ci.yml",
        """variables:
  script: python scripts/ghost.py

real_job:
  script:
    - python scripts/ci.py
""",
    )
    _write(tmp_path / "AGENTS.md", _agents("python scripts/ci.py"))

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")

    assert "commands.unlocated-full-gate" not in _codes(findings)


def test_class_body_import_is_not_visible_inside_method(tmp_path: Path) -> None:
    _write(
        tmp_path / "scripts/ci.py",
        """class Runner:
    import subprocess

    def run(self) -> None:
        subprocess.run(["python", "scripts/ghost.py"], check=True)
""",
    )
    _write(tmp_path / "AGENTS.md", _agents("python scripts/ghost.py"))

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")

    assert "commands.unlocated-full-gate" in _codes(findings)


def test_global_import_remains_visible_inside_method(tmp_path: Path) -> None:
    _write(
        tmp_path / "scripts/ci.py",
        """import subprocess

class Runner:
    def run(self) -> None:
        subprocess.run(["python", "scripts/ci.py"], check=True)
""",
    )
    _write(tmp_path / "AGENTS.md", _agents("python scripts/ci.py"))

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")

    assert "commands.unlocated-full-gate" not in _codes(findings)

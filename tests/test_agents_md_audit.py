"""Behavior and safety contracts for static AGENTS.md repository audits."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills/agents-md-architect/tools"
sys.path.insert(0, str(TOOLS))

import audit_agents_md as audit_module  # noqa: E402


def write_root(repository: Path, extra: str = "") -> None:
    (repository / "docs").mkdir(exist_ok=True)
    (repository / "docs/architecture.md").write_text("# Architecture\n", encoding="utf-8")
    (repository / "scripts").mkdir(exist_ok=True)
    (repository / "scripts/ci.py").write_text("print('gate')\n", encoding="utf-8")
    (repository / "AGENTS.md").write_text(
        """# AGENTS.md

These instructions apply to the repository.

## Scope

Maintain the service without expanding an audit into implementation.

## Commands and verification

- Focused check: `python -m pytest tests/test_service.py`
- Full gate: `python scripts/ci.py`

## Architecture boundaries

- Production data must remain outside tracked files.
- When changing boundaries, read [the architecture guide](docs/architecture.md) for ownership.

## Definition of done

Report focused and full checks, the exact revision, skipped checks, and residual risk.
"""
        + extra,
        encoding="utf-8",
    )


def codes(findings: list[audit_module.AuditFinding]) -> set[str]:
    return {item.code for item in findings}


def test_clean_repository_audit_is_deterministic_and_read_only(tmp_path: Path) -> None:
    write_root(tmp_path)
    before = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    first = audit_module.audit(tmp_path)
    second = audit_module.audit(tmp_path)
    after = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert first == second
    assert first[1] == []
    assert before == after


def test_repository_content_is_never_executed(tmp_path: Path) -> None:
    marker = tmp_path / "executed.txt"
    write_root(tmp_path, f"\n- Full gate: `python -c \"open('{marker}', 'w').write('bad')\"`\n")
    _, findings = audit_module.audit(tmp_path)
    assert marker.exists() is False
    assert "commands.unverified-full-gate" in codes(findings)


def test_nested_conflict_and_duplicate_are_reported(tmp_path: Path) -> None:
    write_root(tmp_path)
    nested = tmp_path / "packages/api"
    nested.mkdir(parents=True)
    (nested / "AGENTS.md").write_text(
        """# Local instructions

These instructions apply only to this subtree.

## Local commands

- Focused check: `python -m pytest packages/api/tests`

## Local boundaries

- Production data must not remain outside tracked files.

## Completion check

Run the local focused check before completion.
""",
        encoding="utf-8",
    )
    _, findings = audit_module.audit(tmp_path, "application")
    assert "nested.conflict" in codes(findings)

    text = (nested / "AGENTS.md").read_text(encoding="utf-8").replace("must not", "must")
    (nested / "AGENTS.md").write_text(text, encoding="utf-8")
    _, findings = audit_module.audit(tmp_path, "application")
    assert "nested.duplicate-inherited-rule" in codes(findings)


def test_readme_duplication_lint_leakage_and_unverified_gate_are_detected(tmp_path: Path) -> None:
    paragraph = (
        "This long operational paragraph explains product behavior in enough detail that it belongs in the README "
        "instead of being copied into every agent instruction file."
    )
    (tmp_path / "README.md").write_text(f"# Product\n\n{paragraph}\n", encoding="utf-8")
    write_root(
        tmp_path,
        f"\n{paragraph}\n\n- Use line length 100 and quote style double.\n- Complete gate: `python missing.py`\n",
    )
    _, findings = audit_module.audit(tmp_path)
    assert {
        "content.documentation-duplication",
        "content.lint-leakage",
        "commands.unverified-full-gate",
    } <= codes(findings)


@pytest.mark.skipif(os.name == "nt", reason="symlink creation may require elevated privileges on Windows")
def test_symlinked_agents_file_is_not_read(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-agents.md"
    outside.write_text("# AGENTS.md\n\nMALICIOUS\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").symlink_to(outside)
    _, findings = audit_module.audit(tmp_path)
    assert "security.symlink-agents" in codes(findings)
    assert all("MALICIOUS" not in item.message for item in findings)


def test_json_cli_reports_discovery_and_findings(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_root(tmp_path, "\n- Complete gate: `python missing.py`\n")
    assert audit_module.main([str(tmp_path), "--format", "json"]) == 1
    output = capsys.readouterr().out
    assert '"discovery"' in output
    assert '"commands.unverified-full-gate"' in output

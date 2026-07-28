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

## Scope and precedence

These instructions apply to the repository. Nested AGENTS.md files define inherited subtree differences.

## Commands and verification

- Focused check: `python -m pytest tests/test_service.py`
- Full gate: `python scripts/ci.py`

## Architecture boundaries

- Generated files must not be edited directly.
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
    first = audit_module.audit(tmp_path, "application", "monorepo", "en")
    second = audit_module.audit(tmp_path, "application", "monorepo", "en")
    after = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert first == second
    assert first[1] == []
    assert before == after


def test_repository_content_is_never_executed(tmp_path: Path) -> None:
    marker = tmp_path / "executed.txt"
    write_root(tmp_path, f"\n- Full gate: `python -c \"open('{marker}', 'w').write('bad')\"`\n")
    _, findings = audit_module.audit(tmp_path, "application", "monorepo", "en")
    assert marker.exists() is False
    assert "commands.unlocated-full-gate" in codes(findings)


def test_nested_conflict_is_reported_by_shared_tree_parser(tmp_path: Path) -> None:
    write_root(tmp_path)
    nested = tmp_path / "packages/api"
    nested.mkdir(parents=True)
    (nested / "AGENTS.md").write_text(
        """# Local instructions

## Scope and local differences

These instructions apply only to this subtree.

## Local commands and completion

- Local focused check: `python -m pytest packages/api/tests`
- Local completion check: `python scripts/ci.py`

## Local boundaries

Generated files must be edited directly.

## Completion check

Run the local focused check before completion.
""",
        encoding="utf-8",
    )
    _, findings = audit_module.audit(tmp_path, "application", "monorepo", "en")
    assert "tree.conflicting-rule" in codes(findings)


def test_readme_duplication_lint_leakage_and_unlocated_gate_are_detected(tmp_path: Path) -> None:
    paragraph = (
        "This long operational paragraph explains product behavior in enough detail that it belongs in the README "
        "instead of being copied into every agent instruction file."
    )
    (tmp_path / "README.md").write_text(f"# Product\n\n{paragraph}\n", encoding="utf-8")
    write_root(
        tmp_path,
        f"\n{paragraph}\n\n- Use line length 100 and quote style double.\n- Complete gate: `python missing.py`\n",
    )
    _, findings = audit_module.audit(tmp_path, "application", "monorepo", "en")
    assert {
        "content.documentation-duplication",
        "content.lint-leakage",
        "commands.unlocated-full-gate",
    } <= codes(findings)


def test_existing_path_without_exact_invocation_is_unverified(tmp_path: Path) -> None:
    write_root(tmp_path)
    (tmp_path / "scripts/helper.py").write_text("print('helper')\n", encoding="utf-8")
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    text = text.replace("python scripts/ci.py", "python scripts/helper.py --dangerous")
    (tmp_path / "AGENTS.md").write_text(text, encoding="utf-8")
    _, findings = audit_module.audit(tmp_path, "application", "monorepo", "en")
    assert "commands.unverified-full-gate" in codes(findings)


def test_audit_and_validator_ignore_the_same_blockquoted_fence(tmp_path: Path) -> None:
    write_root(
        tmp_path,
        """

> ```markdown
> CONSENT_KEYWORDS = ["approve"]
> - Complete gate: `python missing.py`
> ```
""",
    )
    _, findings = audit_module.audit(tmp_path, "application", "monorepo", "en")
    assert "safety.keyword-approval" not in codes(findings)
    assert "commands.unlocated-full-gate" not in codes(findings)


@pytest.mark.skipif(os.name == "nt", reason="symlink creation may require elevated privileges on Windows")
def test_symlinked_agents_file_is_not_read(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-agents.md"
    outside.write_text("# AGENTS.md\n\nMALICIOUS\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").symlink_to(outside)
    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "security.symlink-agents" in codes(findings)
    assert all("MALICIOUS" not in item.message for item in findings)


def test_json_cli_reports_discovery_findings_and_selected_axes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_root(tmp_path, "\n- Complete gate: `python missing.py`\n")
    assert (
        audit_module.main(
            [
                str(tmp_path),
                "--layout",
                "monorepo",
                "--profile",
                "application",
                "--language",
                "en",
                "--format",
                "json",
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    assert '"discovery"' in output
    assert '"commands.unlocated-full-gate"' in output

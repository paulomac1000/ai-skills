"""Regression coverage for final AGENTS.md contract and evidence hardening."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
AGENTS_TOOLS = ROOT / "skills/agents-md-architect/tools"
CI_TOOLS = ROOT / "skills/ci-cd-architect/tools"
CONTRACTS = ROOT / "contracts"
for candidate in (AGENTS_TOOLS, CI_TOOLS, CONTRACTS):
    sys.path.insert(0, str(candidate))

import agents_md_tree_validation as tree_validation  # noqa: E402
import audit_agents_md as audit_module  # noqa: E402
import check_github_actions_policy as workflow_policy  # noqa: E402
import confined_io  # noqa: E402
import validate_agents_md as validator  # noqa: E402
from agents_md_types import ParsedDocument  # noqa: E402


def _codes(findings: list[Any]) -> set[str]:
    return {item.code for item in findings}


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _marked_document(*, empty_scope: bool = False) -> str:
    scope_body = "" if empty_scope else "Repository material is maintained by the named owners."
    return f"""# Repository instructions

## Alpha

<!-- agents-md: contract scope -->
{scope_body}

## Beta

<!-- agents-md: contract commands -->
Repository operators use the established entrypoint.

## Gamma

<!-- agents-md: contract safety -->
Repository operators follow the established boundary.

## Delta

<!-- agents-md: contract completion -->
Repository operators report the resulting revision.
"""


def _agents_with_gate(gate_markdown: str) -> str:
    return f"""# Repository instructions

## Scope

These instructions apply to the repository scope.

## Commands and verification

{gate_markdown}

## Safety boundaries

Security-sensitive and destructive operations require explicit authorization.

## Definition of done

Completion requires reporting the exact revision and residual risk.
"""


def test_contract_markers_do_not_replace_english_semantics(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    _write(path, _marked_document())

    findings = validator.validate_path(path, "application", tmp_path, "single", "en")

    assert {
        "profile.missing-scope",
        "profile.missing-commands",
        "profile.missing-safety",
        "profile.missing-completion",
    } <= _codes(findings)


def test_other_language_markers_require_nonempty_h2_binding(tmp_path: Path) -> None:
    valid = tmp_path / "valid" / "AGENTS.md"
    invalid = tmp_path / "invalid" / "AGENTS.md"
    _write(valid, _marked_document())
    _write(invalid, _marked_document(empty_scope=True))

    valid_findings = validator.validate_path(valid, "application", valid.parent, "single", "other")
    invalid_findings = validator.validate_path(invalid, "application", invalid.parent, "single", "other")

    assert "language.semantic-unverified" not in _codes(valid_findings)
    assert "language.invalid-contract-marker" in _codes(invalid_findings)
    assert "language.semantic-unverified" in _codes(invalid_findings)


@pytest.mark.parametrize(
    "gate_markdown",
    (
        "- Full gate:\n\n  `make quality`",
        "| Full completion gate | `make quality` |",
        "## Completion gate\n\n```bash\nmake quality\n```",
        "- Completion check: `make quality`",
        "- Pe\u0142na bramka: `make quality`",
    ),
)
def test_completion_gate_markdown_forms_are_audited(tmp_path: Path, gate_markdown: str) -> None:
    _write(tmp_path / "Makefile", "quality:\n\tpython scripts/ci.py\n")
    _write(tmp_path / "AGENTS.md", _agents_with_gate(gate_markdown))

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")

    assert "commands.unlocated-full-gate" not in _codes(findings)


@pytest.mark.parametrize(
    ("runner", "content", "command"),
    (
        ("Makefile", "quality:\n\tpython scripts/ci.py\n", "make quality"),
        ("Justfile", "quality:\n    python scripts/ci.py\n", "just quality"),
        (
            "Taskfile.yml",
            "version: '3'\ntasks:\n  quality:\n    cmds:\n      - python scripts/ci.py\n",
            "task quality",
        ),
        ("package.json", '{"scripts":{"quality":"python scripts/ci.py"}}', "npm run quality"),
        ("package.json", '{"scripts":{"quality":"python scripts/ci.py"}}', "pnpm quality"),
    ),
)
def test_public_task_runner_entrypoints_are_command_evidence(
    tmp_path: Path,
    runner: str,
    content: str,
    command: str,
) -> None:
    _write(tmp_path / runner, content)
    _write(tmp_path / "AGENTS.md", _agents_with_gate(f"- Full gate: `{command}`"))

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")

    assert "commands.unlocated-full-gate" not in _codes(findings)


def _document(
    path: Path,
    root: Path,
    *,
    sections: dict[str, str],
    lines: frozenset[str],
) -> ParsedDocument:
    return ParsedDocument(
        path=path,
        relative_path=path.relative_to(root).as_posix(),
        text="",
        visible_lines=(),
        sections=sections,
        contracts=frozenset(),
        directives=(),
        commands=(),
        ownership=(),
        meaningful_lines=lines,
    )


def test_leaf_duplication_is_checked_against_full_ancestor_chain(tmp_path: Path) -> None:
    repeated = "This inherited safety boundary is intentionally long enough to trigger duplication detection."
    root = _document(
        tmp_path / "AGENTS.md",
        tmp_path,
        sections={"safety": repeated},
        lines=frozenset({"root rule"}),
    )
    middle = _document(
        tmp_path / "packages/AGENTS.md",
        tmp_path,
        sections={},
        lines=frozenset({"middle rule"}),
    )
    leaf = _document(
        tmp_path / "packages/api/AGENTS.md",
        tmp_path,
        sections={"safety": repeated},
        lines=frozenset({"root rule"}),
    )

    findings = tree_validation._validate_tree((root, middle, leaf), tmp_path)
    leaf_codes = {item.code for item in findings if item.path == str(leaf.path)}

    assert "tree.duplicated-section" in leaf_codes
    assert "tree.no-local-difference" in leaf_codes


def test_agents_and_workflow_auditors_share_confined_reader() -> None:
    validator_source = inspect.getsourcefile(validator.read_utf8_bounded)
    workflow_source = inspect.getsourcefile(workflow_policy.read_utf8_bounded)
    shared_source = inspect.getsourcefile(confined_io.read_utf8_bounded)

    assert validator_source is not None
    assert workflow_source is not None
    assert shared_source is not None
    assert Path(validator_source).resolve() == Path(shared_source).resolve()
    assert Path(workflow_source).resolve() == Path(shared_source).resolve()


def test_shared_reader_rejects_intermediate_symlink(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    outside = tmp_path / "outside"
    repository.mkdir()
    outside.mkdir()
    _write(outside / "AGENTS.md", "# outside\n")
    try:
        (repository / "linked").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks are unavailable")

    with pytest.raises(confined_io.ConfinedReadError):
        confined_io.read_utf8_bounded(repository / "linked/AGENTS.md", repository, 1024)

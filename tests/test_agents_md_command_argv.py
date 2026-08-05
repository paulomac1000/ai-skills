"""Regression coverage for lossless public-task command argument boundaries."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills/agents-md-architect/tools"
sys.path.insert(0, str(TOOLS))

import audit_agents_md as audit_module  # noqa: E402
from agents_md_command import canonical_invocation, parse_invocation  # noqa: E402
from agents_md_completion_evidence import public_task_invocations  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _agents(command: str) -> str:
    return f"""# Repository instructions

## Scope

These instructions apply to the repository.

## Commands and verification

- Full gate: `{command}`

## Safety boundaries

Secrets must not be committed. Destructive writes require authorization and rollback.

## Definition of done

Report the exact revision, skipped checks, and residual risk.
"""


def _audit_package(tmp_path: Path, scripts: dict[str, str], command: str) -> set[str]:
    _write(tmp_path / "package.json", json.dumps({"scripts": scripts}, ensure_ascii=False))
    _write(tmp_path / "AGENTS.md", _agents(command))
    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    return {finding.code for finding in findings}


@pytest.mark.parametrize("manager", ("npm", "pnpm", "yarn"))
def test_quoted_package_script_name_preserves_one_argument(tmp_path: Path, manager: str) -> None:
    quoted = canonical_invocation((manager, "run", "foo bar"))
    assert "commands.unlocated-full-gate" not in _audit_package(tmp_path, {"foo bar": "pytest"}, quoted)


def test_unquoted_package_script_name_does_not_match_quoted_name(tmp_path: Path) -> None:
    codes = _audit_package(tmp_path, {"foo bar": "pytest"}, "npm run foo bar")
    assert "commands.unlocated-full-gate" in codes


def test_script_foo_and_foo_bar_have_distinct_argv() -> None:
    text = json.dumps({"scripts": {"foo": "pytest", "foo bar": "pytest"}})
    invocations = {
        invocation.argv
        for command in public_task_invocations("package.json", text)
        if (invocation := parse_invocation(command)) is not None
    }
    assert ("npm", "run", "foo") in invocations
    assert ("npm", "run", "foo bar") in invocations
    assert ("npm", "run", "foo", "bar") not in invocations


def test_leading_option_script_name_cannot_become_cli_option(tmp_path: Path) -> None:
    commands = public_task_invocations("package.json", json.dumps({"scripts": {"--version": "pytest"}}))
    assert commands == set()
    assert "commands.unlocated-full-gate" in _audit_package(tmp_path, {"--version": "pytest"}, "npm run --version")


@pytest.mark.parametrize("name", ("test:ci", "za\u017c\u00f3\u0142\u0107", "say'hello", 'say"hello'))
def test_package_script_names_round_trip_without_boundary_loss(tmp_path: Path, name: str) -> None:
    command = canonical_invocation(("npm", "run", name))
    parsed = parse_invocation(command)
    assert parsed is not None
    assert parsed.argv == ("npm", "run", name)
    assert "commands.unlocated-full-gate" not in _audit_package(tmp_path, {name: "pytest"}, command)


def test_taskfile_task_name_with_space_requires_one_quoted_argument(tmp_path: Path) -> None:
    taskfile = "version: '3'\ntasks:\n  'foo bar':\n    cmds:\n      - pytest\n"
    _write(tmp_path / "Taskfile.yml", taskfile)
    _write(tmp_path / "AGENTS.md", _agents(canonical_invocation(("task", "foo bar"))))
    _, quoted_findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "commands.unlocated-full-gate" not in {finding.code for finding in quoted_findings}

    _write(tmp_path / "AGENTS.md", _agents("task foo bar"))
    _, unquoted_findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "commands.unlocated-full-gate" in {finding.code for finding in unquoted_findings}


def test_package_manager_shorthand_does_not_fabricate_script_evidence(tmp_path: Path) -> None:
    commands = public_task_invocations("package.json", json.dumps({"scripts": {"quality": "pytest"}}))
    argv = {invocation.argv for command in commands if (invocation := parse_invocation(command)) is not None}
    assert ("pnpm", "run", "quality") in argv
    assert ("yarn", "run", "quality") in argv
    assert ("pnpm", "quality") not in argv
    assert ("yarn", "quality") not in argv

    assert "commands.unlocated-full-gate" in _audit_package(tmp_path, {"quality": "pytest"}, "pnpm quality")


def test_nested_package_script_does_not_validate_root_command(tmp_path: Path) -> None:
    _write(tmp_path / "apps/web/package.json", json.dumps({"scripts": {"test": "pytest"}}))
    _write(tmp_path / "AGENTS.md", _agents("npm run test"))

    discovery, findings = audit_module.audit(tmp_path, "application", "single", "en")
    known, evidence_findings = audit_module._known_gate_commands(tmp_path, discovery)

    assert evidence_findings == []
    assert audit_module._command_reference_status(tmp_path, "npm run test", known, ".") == "unlocated"
    assert audit_module._command_reference_status(tmp_path, "npm run test", known, "apps/web") == "located-public"
    assert "commands.unlocated-full-gate" in {finding.code for finding in findings}


def test_discovered_script_path_with_spaces_preserves_one_argv_argument(tmp_path: Path) -> None:
    _write(tmp_path / "scripts/full gate.py", "print('ok')\n")
    quoted = canonical_invocation(("python", "scripts/full gate.py"))
    _write(tmp_path / "AGENTS.md", _agents(quoted))

    _, quoted_findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "commands.unlocated-full-gate" not in {finding.code for finding in quoted_findings}

    _write(tmp_path / "AGENTS.md", _agents("python scripts/full gate.py"))
    _, unquoted_findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "commands.unlocated-full-gate" in {finding.code for finding in unquoted_findings}

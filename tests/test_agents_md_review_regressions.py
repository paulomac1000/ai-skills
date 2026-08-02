"""Regressions for the final AGENTS.md review and untrusted-input boundaries."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills/agents-md-architect/tools"
sys.path.insert(0, str(TOOLS))

import agents_md_parse as parser  # noqa: E402
import agents_md_types as types  # noqa: E402
import audit_agents_md as audit_module  # noqa: E402
import discover_repository as discovery  # noqa: E402
import validate_agents_md as validator  # noqa: E402


def codes(findings: list[Any]) -> set[str]:
    return {item.code for item in findings}


def valid_application(extra: str = "") -> str:
    return f"""# AGENTS.md

## Scope

These instructions apply to the repository.

## Commands and verification

- Full gate: `python scripts/ci.py`

## Safety boundaries

Secrets must not be committed. Destructive writes require explicit authorization and rollback.

## Definition of done

Report the exact revision, skipped checks, and residual risk.
{extra}"""


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_audit_reuses_bounded_validator_documents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for index in range(types.MAX_INSTRUCTION_FILES + 1):
        write(tmp_path / f"packages/p{index}/AGENTS.md", "# Local\n")

    def fail_second_read(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("audit performed a second instruction-file read")

    monkeypatch.setattr(audit_module, "_read_text", fail_second_read)
    _, findings = audit_module.audit(tmp_path, "application", "monorepo", "en")
    assert "input.too-many-files" in codes(findings)


def test_destructive_command_ending_in_entrypoint_is_only_unverified(tmp_path: Path) -> None:
    write(tmp_path / "scripts/ci.py", "print('gate')\n")
    write(tmp_path / "AGENTS.md", valid_application().replace("python scripts/ci.py", "rm scripts/ci.py"))
    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "commands.unverified-full-gate" in codes(findings)
    assert "commands.unlocated-full-gate" not in codes(findings)


@pytest.mark.parametrize("layout", ["single", "monorepo"])
def test_empty_instruction_tree_never_passes(tmp_path: Path, layout: str) -> None:
    findings = validator.validate_many([], "application", tmp_path, layout, "en")
    assert "tree.missing-root" in codes(findings)


def test_single_layout_rejects_nested_instruction_files(tmp_path: Path) -> None:
    root = write(tmp_path / "AGENTS.md", valid_application())
    nested = write(tmp_path / "packages/api/AGENTS.md", valid_application())
    findings = validator.validate_many([root, nested], "application", tmp_path, "single", "en")
    assert "tree.unexpected-nested" in codes(findings)


def test_quoted_fence_cannot_hide_unquoted_active_instruction(tmp_path: Path) -> None:
    text = valid_application("\n> ```markdown\n> example\nREPLACE_SECRET\n```\n")
    path = write(tmp_path / "AGENTS.md", text)
    findings = validator.validate_path(path, "application", tmp_path, "single", "en")
    assert {"content.placeholder", "structure.unclosed-fence"} <= codes(findings)


def test_four_space_fence_does_not_close_active_fence(tmp_path: Path) -> None:
    path = write(
        tmp_path / "AGENTS.md",
        valid_application("\n```markdown\nexample\n    ```\nREPLACE_SECRET\n"),
    )
    findings = validator.validate_path(path, "application", tmp_path, "single", "en")
    assert "structure.unclosed-fence" in codes(findings)
    assert "content.placeholder" not in codes(findings)


@pytest.mark.parametrize("profile", ["router", "application"])
def test_router_and_application_require_safety(tmp_path: Path, profile: str) -> None:
    safety = (
        "## Safety boundaries\n\n"
        "Secrets must not be committed. Destructive writes require explicit authorization and rollback.\n\n"
    )
    text = valid_application().replace(safety, "")
    if profile == "router":
        text = text.replace(
            "## Commands and verification\n\n- Full gate: `python scripts/ci.py`",
            "## Task routing\n\nRoute architecture work to the canonical guide.",
        )
    path = write(tmp_path / "AGENTS.md", text)
    assert "profile.missing-safety" in codes(validator.validate_path(path, profile, tmp_path, "single", "en"))


def test_filesystem_resolution_errors_are_stable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = write(tmp_path / "AGENTS.md", valid_application())
    original = Path.resolve

    def fail_resolve(self: Path, strict: bool = False) -> Path:
        if self.name == "AGENTS.md":
            raise PermissionError("denied")
        return original(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", fail_resolve)
    findings = validator.validate_path(path, "application", tmp_path, "single", "en")
    assert "input.unreadable" in codes(findings)


@pytest.mark.parametrize(
    "line",
    [
        "The secretary tracks requests indirectly.",
        "The latest protest bypasses the compass check.",
    ],
)
def test_english_directive_substrings_are_not_classified(line: str) -> None:
    assert parser._directive_category(line, "en") is None


@pytest.mark.parametrize("line", ["protest musi przejsc", "sekretariat zapisuje terminy"])
def test_polish_directive_substrings_are_not_classified(line: str) -> None:
    assert parser._directive_category(line, "pl") is None


def test_discovery_reports_scandir_errors_and_entry_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_scandir(path: Path) -> Any:
        raise PermissionError(13, "denied", str(Path(path) / "private"))

    monkeypatch.setattr(discovery.os, "scandir", broken_scandir)
    result = discovery.discover(tmp_path)
    assert result.issues and "unreadable path" in result.issues[0]

    monkeypatch.undo()
    monkeypatch.setattr(discovery, "MAX_DISCOVERY_ENTRIES", 1)
    write(tmp_path / "one.txt", "1")
    write(tmp_path / "two.txt", "2")
    result = discovery.discover(tmp_path)
    assert any("discovery entries exceed" in issue for issue in result.issues)


def test_audit_reports_incomplete_discovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = discovery.discover(tmp_path)
    incomplete = discovery.Discovery(
        root=original.root,
        files=original.files,
        ecosystems=original.ecosystems,
        manifests=original.manifests,
        ci_files=original.ci_files,
        task_runners=original.task_runners,
        agent_files=original.agent_files,
        documentation=original.documentation,
        symlinks=original.symlinks,
        issues=("unreadable path private: denied",),
        empty=original.empty,
        monorepo_signals=original.monorepo_signals,
    )
    monkeypatch.setattr(audit_module, "discover", lambda _root: incomplete)
    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "discovery.incomplete" in codes(findings)


def test_macos_host_path_is_reported(tmp_path: Path) -> None:
    path = write(
        tmp_path / "AGENTS.md",
        valid_application("\nUse /Users/alice/private/repository for builds.\n"),
    )
    assert "portability.absolute-host-path" in codes(
        validator.validate_path(path, "application", tmp_path, "single", "en")
    )


def test_gate_source_aggregate_is_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write(tmp_path / "scripts/ci.py", "print('ci')\n")
    write(tmp_path / "scripts/other.py", "print('other')\n")
    write(tmp_path / "AGENTS.md", valid_application())
    monkeypatch.setattr(audit_module, "MAX_GATE_FILES", 1)
    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "evidence.too-many-gate-sources" in codes(findings)

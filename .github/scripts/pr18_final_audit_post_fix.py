#!/usr/bin/env python3
"""Repair generated source details before static validation."""

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"{path}: expected one occurrence of {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


regressions = Path("tests/test_final_audit_regressions.py")
replace_once(
    regressions,
    '    text = "jobs: &jobs\n  loop: *jobs\n"\n',
    '    text = "jobs: &jobs\\n  loop: *jobs\\n"\n',
)
replace_once(
    regressions,
    "\n\ndef test_workflow_policy_impl_is_published_and_type_checked() -> None:\n",
    '''

def test_codex_context_budget_is_not_a_per_file_read_limit(tmp_path: Path) -> None:
    write(tmp_path / "AGENTS.md", "root")
    write(tmp_path / "packages/PROJECT_GUIDE.md", "nested fallback content")

    findings = codex_platform._validate_codex_context(tmp_path, ("PROJECT_GUIDE.md",), 20)
    codes = {finding.code for finding in findings}

    assert "platform.codex-context-budget" in codes
    assert "input.too-large" not in codes


def test_workflow_policy_impl_is_published_and_type_checked() -> None:
''',
)

codex = Path("skills/agents-md-architect/tools/agents_md_codex_platform.py")
for statement in (
    "from agents_md_parse import trusted_input",
    "from confined_io import ConfinedReadError, read_utf8_bounded",
    "from discover_repository import discover",
):
    replace_once(codex, statement + "\n", statement + "  # noqa: E402\n")
replace_once(
    codex,
    "from agents_md_types import Finding\n",
    "from agents_md_types import Finding, MAX_INSTRUCTION_FILE_BYTES  # noqa: E402\n",
)
replace_once(
    codex,
    "read_utf8_bounded(trusted, root, max_bytes)",
    "read_utf8_bounded(trusted, root, MAX_INSTRUCTION_FILE_BYTES)",
)

replace_once(
    Path("skills/agents-md-architect/tools/agents_md_shell_evidence_impl.py"),
    "import re\n",
    "import re\nimport shlex\n",
)

#!/usr/bin/env python3
"""Repair generated source details before static validation."""

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"{path}: expected one occurrence of {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    Path("tests/test_final_audit_regressions.py"),
    '    text = "jobs: &jobs\n  loop: *jobs\n"\n',
    '    text = "jobs: &jobs\\n  loop: *jobs\\n"\n',
)

codex = Path("skills/agents-md-architect/tools/agents_md_codex_platform.py")
for statement in (
    "from agents_md_parse import trusted_input",
    "from agents_md_types import Finding",
    "from confined_io import ConfinedReadError, read_utf8_bounded",
    "from discover_repository import discover",
):
    replace_once(codex, statement + "\n", statement + "  # noqa: E402\n")

replace_once(
    Path("skills/agents-md-architect/tools/agents_md_shell_evidence_impl.py"),
    "import re\n",
    "import re\nimport shlex\n",
)

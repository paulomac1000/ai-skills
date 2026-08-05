from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills/agents-md-architect/tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from agents_md_completion_evidence import completion_command_rules  # noqa: E402


def test_completion_gate_preserves_multi_backtick_command_content() -> None:
    text = 'Full gate: ``python -c "print(`value`)"``\n'

    rules = completion_command_rules(text)

    assert [rule.command for rule in rules] == ['python -c "print(`value`)"']


def test_completion_gate_does_not_fabricate_inner_backtick_fragments() -> None:
    text = "Full gate: ``echo `date` ``\n"

    rules = completion_command_rules(text)

    assert [rule.command for rule in rules] == ["echo `date`"]
    assert all(rule.command not in {"echo", "date"} for rule in rules)


def test_single_backtick_completion_gate_remains_supported() -> None:
    text = "Full gate: `python scripts/ci.py`\n"

    rules = completion_command_rules(text)

    assert [rule.command for rule in rules] == ["python scripts/ci.py"]

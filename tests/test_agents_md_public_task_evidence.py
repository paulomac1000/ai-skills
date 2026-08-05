from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills/agents-md-architect/tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from agents_md_completion_evidence import public_task_invocations  # noqa: E402


def test_just_recipe_with_dependencies_exposes_public_command() -> None:
    text = """build:
    echo build

test: build
    python scripts/ci.py
"""

    assert public_task_invocations("Justfile", text) == {"just build", "just test"}


def test_just_assignment_is_not_a_public_recipe() -> None:
    assert public_task_invocations("Justfile", 'setting := "value"\n') == set()

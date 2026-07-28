"""Repository contracts for the AGENTS.md architect skill."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/agents-md-architect"


def test_standard_covers_discovered_instruction_failures() -> None:
    text = (SKILL / "STANDARD.md").read_text(encoding="utf-8").casefold()
    required = {
        "scope and precedence",
        "operating modes and profiles",
        "canonical ownership and architecture boundaries",
        "safety and data boundaries",
        "context economy and routing",
        "nested instructions",
        "anti-patterns and drift",
        "definition of done",
        "context bloat",
        "skill leakage",
        "lint leakage",
        "blind references",
        "keyword matching",
        "local pass does not guarantee remote ci",
        "exact revision",
    }
    assert all(token in text for token in required)


def test_templates_cover_root_and_local_instruction_roles() -> None:
    root = (SKILL / "templates/AGENTS.md.template").read_text(encoding="utf-8")
    nested = (SKILL / "templates/nested-AGENTS.md.template").read_text(encoding="utf-8")
    for token in ("Operating modes", "Sources of truth", "Architecture and safety boundaries", "Definition of done"):
        assert token in root
    assert "apply only" in nested
    assert "Local differences" in nested
    assert "REPLACE_WITH" in root and "REPLACE_WITH" in nested


def test_skill_routes_detail_to_focused_references() -> None:
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 90
    for reference in (
        "references/repository-discovery.md",
        "references/profiles-and-routing.md",
        "references/anti-patterns-and-drift.md",
        "references/lifecycle-and-evidence.md",
    ):
        assert reference in text or (SKILL / reference).is_file()
    assert "tools/validate_agents_md.py" in text

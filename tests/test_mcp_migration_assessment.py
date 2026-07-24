"""Executable contract for migration evidence and normative precedence."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/mcp-server-architect"


def test_migration_assessment_template_covers_production_decision_evidence() -> None:
    template = yaml.safe_load(
        (SKILL / "templates/migration-assessment.yaml.template").read_text(encoding="utf-8")
    )

    assert template["schema_version"] == 1
    assert template["skill"]["name"] == "mcp-server-architect"
    assert template["skill"]["version"] == "1.0.0-rc.1"
    assert template["repository"]["revision"] == "full-immutable-commit-sha"
    assert template["applicability"]
    entry = template["applicability"][0]
    assert {"rule_id", "status", "rationale", "implementation", "verification", "waiver_id"} <= set(entry)
    assert {"preserved", "intentionally_changed", "removed_legacy"} <= set(template["behavior"])
    assert {"exact_revision", "artifact_identity", "official_client_commands", "transport_results", "result"} <= set(
        template["artifact_verification"]
    )
    assert {"trigger_conditions", "procedure", "data_recovery"} <= set(template["rollback"])
    assert template["decision"]["status"] == "request-changes"


def test_normative_precedence_fails_closed_on_resource_conflicts() -> None:
    reference = (SKILL / "references/migration-assessment.md").read_text(encoding="utf-8")
    ordered = (
        "`STANDARD.md` and active normative decisions",
        "the applicable implementation profile",
        "`SKILL.md` workflow instructions",
        "generators and templates",
        "examples",
        "migration simulations",
    )
    positions = [reference.index(value) for value in ordered]
    assert positions == sorted(positions)
    assert "lower-ranked resource cannot weaken a higher-ranked requirement" in reference
    assert "stop the migration" in reference
    assert "independent reviewer" in reference

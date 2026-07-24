"""Executable contract for generic adoption evidence and MCP extensions."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/mcp-server-architect"
CONTRACTS = ROOT / "contracts"


def test_mcp_template_extends_the_generic_adoption_contract() -> None:
    generic = yaml.safe_load((CONTRACTS / "adoption-assessment.yaml.template").read_text(encoding="utf-8"))
    template = yaml.safe_load(
        (SKILL / "templates/migration-assessment.yaml.template").read_text(encoding="utf-8")
    )
    manifest = yaml.safe_load((SKILL / "manifest.yaml").read_text(encoding="utf-8"))

    assert template["schema_version"] == generic["schema_version"] == 1
    assert template["skill"]["name"] == manifest["name"]
    assert template["skill"]["version"] == manifest["version"]
    assert template["skill"]["maturity"] == manifest["maturity"]
    for field in (
        "verification_mode",
        "prepared_by",
        "compatibility_claims",
        "applicability",
        "artifact_verification",
        "compatibility_results",
        "extensions",
        "rollback",
        "residual_risks",
        "decision",
    ):
        assert field in template
    mcp = template["extensions"]["mcp"]
    assert mcp["target_level"] in {"L1", "L2", "L3", "L4"}
    assert mcp["profiles"]
    assert set(mcp["transport_results"]) == {"stdio", "streamable_http"}
    assert template["decision"]["status"] == "request-changes"


def test_manifest_requires_repository_adoption_contract_and_mcp_extension() -> None:
    manifest = yaml.safe_load((SKILL / "manifest.yaml").read_text(encoding="utf-8"))
    adoption = manifest["adoption"]
    assert adoption == {
        "template": "contracts/adoption-assessment.yaml.template",
        "validator": "contracts/validate_adoption.py",
        "rule_catalog": "contracts/rule-catalog.yaml",
        "rule_map": "contracts/standard-rule-map.yaml",
        "extension": "mcp",
    }
    for key in ("template", "validator", "rule_catalog", "rule_map"):
        assert (ROOT / adoption[key]).is_file()


def test_normative_precedence_and_machine_validation_fail_closed() -> None:
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
    assert "contracts/rule-catalog.yaml" in reference
    assert "contracts/validate_adoption.py" in reference
    assert "--require-approval" in reference
    assert "canonical provider, login, and numeric ID" in reference

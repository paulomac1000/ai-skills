"""Regressions for AFDS executable behavior and decision implementation contracts."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/afds_change_contracts"


def _headings(text: str) -> set[str]:
    return {match.group(1).strip().casefold() for match in re.finditer(r"^##\s+(.+?)\s*$", text, re.M)}


def _implementation_rows(text: str) -> list[dict[str, str]]:
    section = re.search(
        r"^## Implementation consequences\s*$\n(?P<body>.*?)(?=^##\s+|\Z)",
        text,
        re.M | re.S,
    )
    assert section is not None
    rows = [line.strip() for line in section.group("body").splitlines() if line.strip().startswith("|")]
    assert len(rows) >= 3
    header = [cell.strip().casefold() for cell in rows[0].strip("|").split("|")]
    result: list[dict[str, str]] = []
    for row in rows[2:]:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        assert len(cells) == len(header)
        result.append(dict(zip(header, cells, strict=True)))
    return result


def _completion_findings(text: str) -> list[str]:
    claim_complete = bool(re.search(r"Implementation claim:\s*\*\*complete\*\*", text, re.I))
    if not claim_complete:
        return []
    findings: list[str] = []
    for row in _implementation_rows(text):
        if row["required"].casefold() != "yes":
            continue
        resolution = row["resolution"].casefold()
        if resolution not in {"satisfied", "not_applicable"}:
            findings.append(f'{row["kind"]}: required consequence is {resolution}')
            continue
        if resolution == "not_applicable" and row["evidence"] in {"", "-"}:
            findings.append(f'{row["kind"]}: not_applicable consequence is missing reason')
            continue
        if row["kind"].casefold() == "verification" and resolution == "satisfied" and row["evidence"] in {"", "-"}:
            findings.append("verification: satisfied consequence is missing evidence")
    return findings


def test_behavior_contract_fixture_keeps_statement_kinds_and_proof_mapping_distinct() -> None:
    text = (FIXTURES / "behavior-contract.md").read_text(encoding="utf-8")
    headings = _headings(text)
    for required in {
        "scope",
        "obligations",
        "acceptance criteria",
        "normal flow",
        "negative and failure flows",
        "public effects and compatibility",
        "decision references",
        "assumptions",
        "examples",
        "verification mapping",
        "machine contract authority",
    }:
        assert required in headings
    assert "qa-change-verifier:criterion/CRIT-1" in text
    assert "Executed PASS/FAIL results remain in CI/evidence records." in text
    assert "canonical machine-readable schema remains authoritative" in text


def test_decision_completion_requires_every_mandatory_consequence_and_verification_evidence() -> None:
    incomplete = (FIXTURES / "decision-incomplete.md").read_text(encoding="utf-8")
    complete = (FIXTURES / "decision-complete.md").read_text(encoding="utf-8")
    missing_reason = (FIXTURES / "decision-not-applicable-without-reason.md").read_text(encoding="utf-8")
    assert "status: active" in incomplete
    assert _completion_findings(incomplete) == ["verification: required consequence is pending"]
    assert _completion_findings(missing_reason) == ["rollback: not_applicable consequence is missing reason"]
    kinds = {row["kind"] for row in _implementation_rows(incomplete)}
    assert {"implementation", "migration", "rollout", "rollback", "cleanup", "verification"} <= kinds
    assert "## Affected obligations and consumers" in incomplete
    assert _completion_findings(complete) == []


def test_normative_standard_separates_decision_authority_from_completion_without_new_status_enum() -> None:
    standard = (ROOT / "skills/afds-doc-writer/STANDARD.md").read_text(encoding="utf-8")
    assert "decision accepted is not the same fact as decision implemented" in standard
    assert "`status: active` establishes current decision authority only" in standard
    assert "satisfied with its required current evidence/reference" in standard
    assert "explicitly not applicable with reason" in standard
    assert "pending, blocked, unknown, unverified, or unreviewed" in standard
    assert "Do not add a second global AFDS status enum" in standard
    assert "implementation_status" not in standard


def test_playbooks_route_completion_through_existing_change_impact_protocol() -> None:
    playbooks = (ROOT / "skills/afds-doc-writer/references/type-playbooks.md").read_text(encoding="utf-8")
    lifecycle = (ROOT / "skills/afds-doc-writer/references/lifecycle-and-impact.md").read_text(encoding="utf-8")
    assert "Use the lifecycle/change-impact protocol for downstream consequences" in playbooks
    assert "Treat decision acceptance and implementation completion as separate lifecycle facts." in lifecycle
    assert "existing change-impact protocol instead of inventing a second dependency graph" in lifecycle


def test_new_rules_have_catalog_map_and_evidence_plan_coverage() -> None:
    catalog = yaml.safe_load((ROOT / "contracts/rule-catalog.yaml").read_text(encoding="utf-8"))
    ids = {rule["id"] for rule in catalog["skills"]["afds-doc-writer"]["rules"]}
    expected = {"afds.behavior.acceptance-traceable", "afds.decision.implementation-traceable"}
    assert expected <= ids

    rule_map = yaml.safe_load((ROOT / "contracts/standard-rule-map.yaml").read_text(encoding="utf-8"))
    mapped = rule_map["skills"]["afds-doc-writer"]["headings"]
    assert mapped["executable-behavior-and-acceptance-contracts"]["rule_id"] == "afds.behavior.acceptance-traceable"
    assert mapped["decision-authority-and-implementation-completion"]["rule_id"] == "afds.decision.implementation-traceable"

    plan = yaml.safe_load((ROOT / "contracts/evidence-claim-plan.yaml").read_text(encoding="utf-8"))
    subjects = {
        entry["subject"]
        for entries in plan["profiles"].values()
        for entry in entries
        if entry.get("kind") == "rule"
    }
    assert expected <= subjects

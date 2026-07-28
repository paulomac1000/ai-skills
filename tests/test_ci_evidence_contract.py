"""Repository evidence production and skill adoption instructions are mandatory."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILLS = (
    "afds-doc-writer",
    "agents-md-architect",
    "ci-cd-architect",
    "mcp-server-architect",
    "mcp-server-consumer",
)


def test_every_skill_requires_the_shared_adoption_gate() -> None:
    required = (
        "## Adoption and migration evidence",
        "contracts/adoption-assessment.yaml.template",
        "contracts/rule-catalog.yaml",
        "contracts/validate_adoption.py",
        "provider-backed",
        "GitHub.com",
        "independent",
        "exact SHA",
    )
    for skill in SKILLS:
        text = (ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
        for token in required:
            assert token in text, f"{skill} does not explain {token!r}"


def test_every_declared_evidence_lane_writes_a_machine_bound_report() -> None:
    workflow_text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    jobs = workflow["jobs"]
    matrix = yaml.safe_load((ROOT / "contracts/compatibility-matrix.yaml").read_text(encoding="utf-8"))
    for lane in matrix["lanes"].values():
        job = jobs[lane["workflow_job"]]
        rendered = yaml.safe_dump(job)
        assert "contracts/run_evidence_command.py" in rendered
        assert "contracts/write_evidence_report.py" in rendered
        assert "evidence/report.json" in rendered
        evidence_uploads = [
            step
            for step in job["steps"]
            if isinstance(step, dict)
            and str(step.get("uses") or "").startswith("actions/upload-artifact@")
            and "evidence/" in str((step.get("with") or {}).get("path") or "")
        ]
        assert len(evidence_uploads) == 1
        assert evidence_uploads[0]["with"]["retention-days"] == 90
        checkout_steps = [
            step
            for step in job["steps"]
            if isinstance(step, dict) and str(step.get("uses") or "").startswith("actions/checkout@")
        ]
        assert checkout_steps
        for checkout in checkout_steps:
            assert checkout["with"]["ref"] == "${{ github.event.pull_request.head.sha || github.sha }}"
            assert checkout["with"]["persist-credentials"] is False


def test_claim_plan_covers_every_stable_rule_with_test_selectors() -> None:
    catalog = yaml.safe_load((ROOT / "contracts/rule-catalog.yaml").read_text(encoding="utf-8"))
    plan = yaml.safe_load((ROOT / "contracts/evidence-claim-plan.yaml").read_text(encoding="utf-8"))
    claims = plan["profiles"]["repository-rules"]
    by_subject = {claim["subject"]: claim for claim in claims if claim["kind"] == "rule"}
    expected = {rule["id"] for skill in catalog["skills"].values() for rule in skill["rules"]}
    assert set(by_subject) == expected
    for rule_id, claim in by_subject.items():
        assert claim["execution_id"].strip(), rule_id
        assert claim["selectors"], rule_id
        assert all(selector.strip() for selector in claim["selectors"])

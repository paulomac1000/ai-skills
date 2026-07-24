"""Executable acceptance contract for repository-wide skill adoption assessments."""

from __future__ import annotations

import copy
from datetime import date
from pathlib import Path

import yaml

from contracts.validate_adoption import validate_document

ROOT = Path(__file__).resolve().parents[1]
CATALOG = yaml.safe_load((ROOT / "contracts/rule-catalog.yaml").read_text(encoding="utf-8"))


def assessment_for(skill_name: str, *, mcp: bool = False) -> dict:
    manifest = yaml.safe_load((ROOT / "skills" / skill_name / "manifest.yaml").read_text(encoding="utf-8"))
    rules = CATALOG["skills"][skill_name]["rules"]
    assessment = {
        "schema_version": 1,
        "assessment_id": f"{skill_name}-pilot-001",
        "generated_at": "2026-07-24T12:00:00Z",
        "prepared_by": ["migration-author"],
        "repository": {
            "name": "example/repository",
            "revision": "a" * 40,
            "source_branch": "migration/skills",
        },
        "skill": {
            "name": skill_name,
            "version": manifest["version"],
            "maturity": manifest["maturity"],
        },
        "scope": {
            "included": ["production implementation and quality gates"],
            "excluded": [],
            "exclusion_rationale": [],
        },
        "compatibility_claims": {
            "operating_systems": ["linux"],
            "runtimes": {"python": ["3.12"]} if "python" in (manifest["compatibility"].get("runtimes") or {}) else {},
        },
        "applicability": [
            {
                "rule_id": rule["id"],
                "status": "applicable",
                "rationale": "Required by the selected production scope.",
                "implementation": [{"path": "src/implementation.py", "symbol": "production_boundary"}],
                "verification": [
                    {
                        "command": f"pytest -q tests/test_{index}.py",
                        "evidence": f"ci://run/100/job/{index}",
                        "result": "passed",
                    }
                ],
                "waiver_id": None,
            }
            for index, rule in enumerate(rules)
        ],
        "behavior": {
            "preserved": ["Existing supported behavior remains available."],
            "intentionally_changed": [],
            "removed_legacy": [],
        },
        "waivers": [],
        "artifact_verification": {
            "exact_revision": "a" * 40,
            "artifacts": [
                {
                    "kind": "wheel",
                    "identity": "example-package==1.0.0",
                    "digest": "sha256:" + "b" * 64,
                    "commands": ["python -m pytest -q tests/artifact"],
                    "result": "passed",
                }
            ],
        },
        "compatibility_results": [
            {
                "operating_system": "linux",
                "runtime": "python",
                "version": "3.12",
                "command": "python -m pytest -q",
                "evidence": "ci://run/100/job/linux-python-312",
                "result": "passed",
            }
        ],
        "extensions": {},
        "rollback": {
            "trigger_conditions": ["A post-deployment contract smoke fails."],
            "procedure": ["Restore the pinned previous artifact."],
            "data_recovery": ["Replay the verified pre-deployment snapshot when needed."],
        },
        "residual_risks": [],
        "decision": {
            "status": "approve",
            "rationale": "Every catalog rule and claimed environment has passed evidence.",
            "reviewer": "independent-reviewer",
        },
    }
    if not assessment["compatibility_claims"]["runtimes"]:
        assessment["compatibility_results"][0].pop("runtime")
        assessment["compatibility_results"][0].pop("version")
    if mcp:
        assessment["extensions"] = {
            "mcp": {
                "target_level": "L3",
                "profiles": ["python"],
                "advertised_transports": ["stdio", "streamable_http"],
                "official_client_commands": ["python -m pytest -q tests/official_client"],
                "transport_results": {
                    transport: {
                        field: {
                            "result": "passed",
                            "evidence": f"ci://run/100/mcp/{transport}/{field}",
                        }
                        for field in (
                            "capability_listing",
                            "representative_read",
                            "failure_path",
                            "write_boundary",
                        )
                    }
                    for transport in ("stdio", "streamable_http")
                },
            }
        }
    return assessment


def findings(document: dict) -> list[str]:
    return [
        str(finding)
        for finding in validate_document(
            document,
            CATALOG,
            ROOT / "skills",
            require_approval=True,
            as_of=date(2026, 7, 24),
        )
    ]


def test_generic_assessment_accepts_complete_non_mcp_adoption() -> None:
    assert findings(assessment_for("afds-doc-writer")) == []


def test_mcp_extension_accepts_complete_official_client_transport_evidence() -> None:
    assert findings(assessment_for("mcp-server-architect", mcp=True)) == []


def test_missing_unknown_and_duplicate_rules_fail_completeness() -> None:
    document = assessment_for("mcp-server-consumer")
    removed = document["applicability"].pop()
    document["applicability"].append(copy.deepcopy(document["applicability"][0]))
    document["applicability"].append({**copy.deepcopy(removed), "rule_id": "consumer.unknown.rule"})
    result = "\n".join(findings(document))
    assert "missing catalog rules" in result
    assert "duplicates another applicability entry" in result
    assert "does not exist in the stable rule catalog" in result


def test_revision_artifact_and_verification_claims_fail_closed() -> None:
    document = assessment_for("ci-cd-architect")
    document["artifact_verification"]["exact_revision"] = "c" * 40
    document["artifact_verification"]["artifacts"][0]["identity"] = "replace-with-artifact"
    document["artifact_verification"]["artifacts"][0]["digest"] = "sha256:bad"
    document["applicability"][0]["verification"][0]["result"] = "not-run"
    result = "\n".join(findings(document))
    assert "must equal repository.revision" in result
    assert "must not contain a placeholder" in result
    assert "must be a sha256 digest" in result
    assert "must be passed" in result


def test_deferred_rule_requires_live_matching_waiver() -> None:
    document = assessment_for("afds-doc-writer")
    entry = document["applicability"][0]
    entry.update({"status": "deferred", "implementation": [], "verification": [], "waiver_id": "waiver-1"})
    document["waivers"] = [
        {
            "waiver_id": "waiver-1",
            "rule_id": entry["rule_id"],
            "owner": "platform-owner",
            "rationale": "Temporary upstream limitation.",
            "compensating_controls": ["Block deployment outside the pilot environment."],
            "expires_at": "2026-07-23",
        }
    ]
    result = "\n".join(findings(document))
    assert "waiver expired" in result


def test_approval_requires_independent_reviewer_and_complete_compatibility() -> None:
    document = assessment_for("mcp-server-consumer")
    document["decision"]["reviewer"] = "migration-author"
    document["compatibility_results"][0]["result"] = "failed"
    result = "\n".join(findings(document))
    assert "must be independent" in result
    assert "missing passed evidence" in result


def test_mcp_approval_rejects_incomplete_transport_and_blocking_risk() -> None:
    document = assessment_for("mcp-server-architect", mcp=True)
    document["extensions"]["mcp"]["transport_results"]["stdio"]["failure_path"]["result"] = "not-run"
    document["residual_risks"] = [
        {
            "risk": "Approval provenance remains unresolved.",
            "owner": "security-owner",
            "mitigation": "Keep writes disabled.",
            "blocking": True,
        }
    ]
    result = "\n".join(findings(document))
    assert "must be passed or explicitly not-applicable" in result
    assert "cannot approve while a blocking residual risk remains" in result

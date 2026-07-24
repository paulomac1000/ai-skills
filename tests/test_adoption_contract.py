"""Executable acceptance contract for repository-wide skill adoption assessments."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from contracts.validate_adoption import validate_document

ROOT = Path(__file__).resolve().parents[1]
CATALOG = yaml.safe_load((ROOT / "contracts/rule-catalog.yaml").read_text(encoding="utf-8"))
SCHEMA = json.loads((ROOT / "contracts/adoption-assessment.schema.json").read_text(encoding="utf-8"))
REVISION = "a" * 40
REPOSITORY = "example/repository"
ARTIFACT_PATH = "contracts/README.md"
ARTIFACT_DIGEST = "sha256:" + hashlib.sha256((ROOT / ARTIFACT_PATH).read_bytes()).hexdigest()
PROVIDER_DIGEST = "sha256:" + "c" * 64


class FakeVerifier:
    """Deterministic provider adapter used by semantic contract tests."""

    def __init__(self, failures: Sequence[str] = ()) -> None:
        self.failures = list(failures)
        self.action_calls = 0
        self.artifact_calls = 0
        self.review_calls = 0

    def verify_action(self, reference: Mapping[str, Any], expected_revision: str) -> Sequence[str]:
        self.action_calls += 1
        return self.failures

    def verify_artifact(
        self,
        reference: Mapping[str, Any],
        expected_revision: str,
        expected_digest: str,
    ) -> Sequence[str]:
        self.artifact_calls += 1
        return self.failures

    def verify_review(self, reference: Mapping[str, Any], expected_revision: str) -> Sequence[str]:
        self.review_calls += 1
        return self.failures


def evidence(job_id: int, *, artifact_id: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "provider": "github-actions",
        "repository": REPOSITORY,
        "run_id": 100,
        "job_id": job_id,
        "revision": REVISION,
    }
    if artifact_id is not None:
        result["artifact_id"] = artifact_id
        result["provider_digest"] = PROVIDER_DIGEST
    return result


def assessment_for(skill_name: str, *, mcp: bool = False) -> dict[str, Any]:
    manifest = yaml.safe_load((ROOT / "skills" / skill_name / "manifest.yaml").read_text(encoding="utf-8"))
    rules = CATALOG["skills"][skill_name]["rules"]
    combination = copy.deepcopy(manifest["compatibility"]["tested_combinations"][0])
    assessment: dict[str, Any] = {
        "schema_version": 1,
        "verification_mode": "provider-backed",
        "assessment_id": f"{skill_name}-pilot-001",
        "generated_at": "2026-07-24T12:00:00Z",
        "prepared_by": [{"provider": "github", "login": "migration-author", "id": 1001}],
        "repository": {
            "name": REPOSITORY,
            "revision": REVISION,
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
        "compatibility_claims": {"combinations": [combination]},
        "applicability": [
            {
                "rule_id": rule["id"],
                "status": "applicable",
                "rationale": "Required by the selected production scope.",
                "implementation": [{"path": ARTIFACT_PATH, "symbol": "Repository adoption contracts"}],
                "verification": [
                    {
                        "command": f"pytest -q tests/test_{index}.py",
                        "evidence": evidence(index + 1),
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
            "exact_revision": REVISION,
            "artifacts": [
                {
                    "kind": "document-set",
                    "identity": "repository-adoption-contracts==1.0.0",
                    "path": ARTIFACT_PATH,
                    "digest": ARTIFACT_DIGEST,
                    "commands": ["python -m pytest -q tests/test_adoption_contract.py"],
                    "evidence": evidence(200, artifact_id=300),
                    "result": "passed",
                }
            ],
        },
        "compatibility_results": [
            {
                **combination,
                "command": "python -m pytest -q",
                "evidence": evidence(400),
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
            "rationale": "Every catalog rule and claimed target tuple has provider-backed evidence.",
            "reviewer": {
                "provider": "github",
                "repository": REPOSITORY,
                "pull_request": 12,
                "review_id": 9001,
                "login": "independent-reviewer",
                "id": 2002,
                "revision": REVISION,
                "state": "APPROVED",
            },
        },
    }
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
                            "evidence": evidence(500 + transport_index * 10 + field_index),
                        }
                        for field_index, field in enumerate(
                            ("capability_listing", "representative_read", "failure_path", "write_boundary")
                        )
                    }
                    for transport_index, transport in enumerate(("stdio", "streamable_http"))
                },
            }
        }
    return assessment


def findings(document: dict[str, Any], *, verifier: FakeVerifier | None = None) -> list[str]:
    return [
        str(finding)
        for finding in validate_document(
            document,
            CATALOG,
            ROOT / "skills",
            require_approval=True,
            as_of=date(2026, 7, 24),
            schema=SCHEMA,
            repository_root=ROOT,
            evidence_verifier=verifier or FakeVerifier(),
        )
    ]



def assert_template_shape(template: Any, completed: Any, location: str = "root") -> None:
    """Require every template key and item shape to exist in a complete document."""
    if isinstance(template, Mapping):
        assert isinstance(completed, Mapping), location
        for key, value in template.items():
            assert key in completed, f"{location}.{key}"
            assert_template_shape(value, completed[key], f"{location}.{key}")
    elif isinstance(template, list) and template:
        assert isinstance(completed, list) and completed, location
        assert_template_shape(template[0], completed[0], f"{location}[0]")


def test_published_templates_follow_the_schema_backed_complete_shapes() -> None:
    generic_template = yaml.safe_load(
        (ROOT / "contracts/adoption-assessment.yaml.template").read_text(encoding="utf-8")
    )
    mcp_template = yaml.safe_load(
        (ROOT / "skills/mcp-server-architect/templates/migration-assessment.yaml.template").read_text(
            encoding="utf-8"
        )
    )
    assert_template_shape(generic_template, assessment_for("afds-doc-writer"))
    assert_template_shape(mcp_template, assessment_for("mcp-server-architect", mcp=True))

def test_public_schema_is_valid_and_matches_template_top_level_contract() -> None:
    Draft202012Validator.check_schema(SCHEMA)
    template = yaml.safe_load((ROOT / "contracts/adoption-assessment.yaml.template").read_text(encoding="utf-8"))
    assert set(SCHEMA["required"]) == set(template)
    assert "example.invalid" not in SCHEMA["$id"]


def test_public_schema_accepts_complete_non_mcp_and_mcp_documents() -> None:
    validator = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
    for document in (assessment_for("afds-doc-writer"), assessment_for("mcp-server-architect", mcp=True)):
        assert list(validator.iter_errors(document)) == []


def test_public_schema_rejects_unknown_and_missing_fields() -> None:
    validator = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
    document = assessment_for("ci-cd-architect")
    document["unknown"] = True
    document.pop("rollback")
    messages = "\n".join(error.message for error in validator.iter_errors(document))
    assert "Additional properties are not allowed" in messages
    assert "'rollback' is a required property" in messages


def test_generic_assessment_accepts_complete_non_mcp_adoption() -> None:
    assert findings(assessment_for("afds-doc-writer")) == []


def test_mcp_extension_accepts_complete_official_client_transport_evidence() -> None:
    verifier = FakeVerifier()
    assert findings(assessment_for("mcp-server-architect", mcp=True), verifier=verifier) == []
    assert verifier.action_calls > 0 and verifier.artifact_calls == 1 and verifier.review_calls == 1


def test_structural_attestation_cannot_approve() -> None:
    document = assessment_for("afds-doc-writer")
    document["verification_mode"] = "structural-attestation"
    assert "approval requires provider-backed evidence" in "\n".join(findings(document))


def test_provider_backed_mode_requires_a_verifier() -> None:
    document = assessment_for("afds-doc-writer")
    result = validate_document(
        document,
        CATALOG,
        ROOT / "skills",
        require_approval=True,
        as_of=date(2026, 7, 24),
        schema=SCHEMA,
        repository_root=ROOT,
        evidence_verifier=None,
    )
    assert any("requires an evidence verifier" in str(item) for item in result)


def test_provider_failures_block_approval() -> None:
    result = "\n".join(findings(assessment_for("afds-doc-writer"), verifier=FakeVerifier(["run missing"])))
    assert "provider verification failed: run missing" in result


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
    artifact = document["artifact_verification"]["artifacts"][0]
    artifact["identity"] = "replace-with-artifact"
    artifact["digest"] = "sha256:" + "c" * 64
    document["applicability"][0]["verification"][0]["result"] = "not-run"
    result = "\n".join(findings(document))
    assert "must equal repository.revision" in result
    assert "must not contain a placeholder" in result
    assert "does not match the artifact at path" in result
    assert "must be passed" in result


def test_missing_implementation_path_and_symbol_are_rejected() -> None:
    document = assessment_for("afds-doc-writer")
    document["applicability"][0]["implementation"] = [
        {"path": "missing/file.py", "symbol": "missing_symbol"},
        {"path": ARTIFACT_PATH, "symbol": "missing_symbol"},
    ]
    result = "\n".join(findings(document))
    assert "does not identify an existing file" in result
    assert "was not found in the implementation file" in result


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
    assert "waiver expired" in "\n".join(findings(document))


def test_approval_requires_canonical_independent_reviewer_and_complete_tuple() -> None:
    document = assessment_for("mcp-server-consumer")
    document["decision"]["reviewer"].update({"login": "MIGRATION-AUTHOR", "id": 1001})
    document["compatibility_results"][0]["result"] = "failed"
    result = "\n".join(findings(document))
    assert "must be independent" in result
    assert "missing passed evidence for combinations" in result


def test_evidence_revision_and_repository_must_match_assessment() -> None:
    document = assessment_for("afds-doc-writer")
    reference = document["applicability"][0]["verification"][0]["evidence"]
    reference["repository"] = "other/repository"
    reference["revision"] = "b" * 40
    result = "\n".join(findings(document))
    assert "must equal repository.name" in result
    assert "must equal repository.revision" in result


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

"""Executable acceptance contract for repository-wide skill adoption assessments."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

from contracts.validate_adoption import _path_digest, validate_document

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "contracts/adoption-assessment.schema.json").read_text(encoding="utf-8"))
REVISION = "a" * 40
REPOSITORY = "example/repository"
PROVIDER_DIGEST = "sha256:" + "c" * 64
REPORT_DIGEST = "sha256:" + "d" * 64

AUTHORITY = {
    "verifier_repository": "trusted-owner/ai-skills-verifier",
    "verifier_revision": "b" * 40,
    "claim_catalog_repository": "trusted-owner/ai-skills-policy",
    "claim_catalog_revision": "c" * 40,
    "workflow_path": ".github/workflows/verify-adoption.yml",
}


class FakeVerifier:
    """Deterministic provider adapter used by semantic contract tests."""

    def __init__(
        self,
        failures: Sequence[str] = (),
        *,
        acceptance_authority: Mapping[str, str] | None = AUTHORITY,
    ) -> None:
        self.failures = list(failures)
        self.acceptance_authority = acceptance_authority
        self.action_references: list[Mapping[str, Any]] = []
        self.artifact_references: list[Mapping[str, Any]] = []
        self.review_calls = 0

    def verify_action(self, reference: Mapping[str, Any], expected_revision: str) -> Sequence[str]:
        self.action_references.append(reference)
        return self.failures

    def verify_artifact(
        self,
        reference: Mapping[str, Any],
        expected_revision: str,
        expected_digest: str,
    ) -> Sequence[str]:
        self.artifact_references.append(reference)
        return self.failures

    def verify_review(self, reference: Mapping[str, Any], expected_revision: str) -> Sequence[str]:
        self.review_calls += 1
        return self.failures


def evidence(
    job_id: int,
    *,
    lane: str = "python-compatibility",
    artifact_id: int | None = None,
) -> dict[str, Any]:
    return {
        "provider": "github-actions",
        "repository": REPOSITORY,
        "run_id": 100,
        "job_id": job_id,
        "check_run_id": 10_000 + job_id,
        "revision": REVISION,
        "workflow_id": 300,
        "workflow_path": ".github/workflows/ci.yml",
        "workflow_name": "CI",
        "event": "pull_request",
        "job_name": f"evidence-job-{job_id}",
        "lane": lane,
        "artifact_id": artifact_id or 300 + job_id,
        "artifact_name": f"evidence-{job_id}",
        "provider_digest": PROVIDER_DIGEST,
        "report_path": "evidence/report.json",
        "report_digest": REPORT_DIGEST,
    }


def _minimal_catalog(skill_name: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "skills": {
            skill_name: {
                "rules": [
                    {
                        "id": f"{skill_name}.required-rule",
                        "source": "STANDARD.md#required-rule",
                        "description": "Required rule.",
                    }
                ]
            }
        },
    }


def _write_skill(tmp_path: Path, skill_name: str, combination: dict[str, str]) -> Path:
    skills = tmp_path / "skills"
    skill = skills / skill_name
    skill.mkdir(parents=True)
    (skill / "manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "name": skill_name,
                "version": "1.1.0-rc.1",
                "maturity": "release-candidate",
                "compatibility": {"tested_combinations": [combination]},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return skills


def assessment_for(
    tmp_path: Path,
    skill_name: str = "example-skill",
    *,
    mcp: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("immutable artifact\n", encoding="utf-8")
    test_file = tmp_path / "tests" / "test_rule.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_rule():\n    pass\n", encoding="utf-8")
    combination = {
        "operating_system": "linux",
        "architecture": "x64",
        "runtime": "python",
        "version": "3.12",
        "lane": "python-compatibility",
    }
    skills = _write_skill(tmp_path, skill_name, combination)
    catalog = _minimal_catalog(skill_name)
    rule_id = catalog["skills"][skill_name]["rules"][0]["id"]
    document: dict[str, Any] = {
        "schema_version": 1,
        "verification_mode": "provider-backed",
        "acceptance_authority": dict(AUTHORITY),
        "assessment_id": f"{skill_name}-pilot-001",
        "generated_at": "2026-07-24T12:00:00Z",
        "prepared_by": [{"provider": "github", "login": "migration-author", "id": 1001}],
        "repository": {"name": REPOSITORY, "revision": REVISION, "source_branch": "migration/skills"},
        "skill": {"name": skill_name, "version": "1.1.0-rc.1", "maturity": "release-candidate"},
        "scope": {"included": ["production implementation"], "excluded": [], "exclusion_rationale": []},
        "compatibility_claims": {"combinations": [combination]},
        "applicability": [
            {
                "rule_id": rule_id,
                "status": "applicable",
                "rationale": "Required by the selected scope.",
                "implementation": [{"path": "artifact.txt", "symbol": "immutable artifact"}],
                "verification": [
                    {
                        "command": "python -m pytest tests/test_rule.py",
                        "test_case": "tests/test_rule.py::test_rule",
                        "evidence": evidence(1),
                        "result": "passed",
                    }
                ],
                "waiver_id": None,
            }
        ],
        "behavior": {
            "preserved": ["Supported behavior remains available."],
            "intentionally_changed": [],
            "removed_legacy": [],
        },
        "waivers": [],
        "artifact_verification": {
            "exact_revision": REVISION,
            "artifacts": [
                {
                    "kind": "document-set",
                    "identity": "example-artifact==1.0.0",
                    "path": "artifact.txt",
                    "digest": "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    "commands": ["python -m pytest tests/test_artifact.py"],
                    "evidence": evidence(2, artifact_id=302),
                    "result": "passed",
                }
            ],
        },
        "compatibility_results": [
            {
                **combination,
                "command": "python -m pytest -q",
                "evidence": evidence(3, lane="python-compatibility"),
                "result": "passed",
            }
        ],
        "extensions": {},
        "rollback": {
            "trigger_conditions": ["A post-deployment contract smoke fails."],
            "procedure": ["Restore the pinned previous artifact."],
            "data_recovery": ["Replay the verified snapshot when needed."],
        },
        "residual_risks": [],
        "decision": {
            "status": "approve",
            "rationale": "Every rule and target tuple has provider-backed evidence.",
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
        document["extensions"] = {
            "mcp": {
                "target_level": "L3",
                "profiles": ["python"],
                "capabilities": [],
                "advertised_transports": ["stdio"],
                "official_client_commands": ["python -m pytest tests/official_client"],
                "transport_results": {
                    "stdio": {
                        field: {
                            "result": "passed",
                            "evidence": evidence(10 + index, lane="mcp-transport"),
                        }
                        for index, field in enumerate(
                            ("capability_listing", "representative_read", "failure_path", "write_boundary")
                        )
                    },
                    "streamable_http": {
                        field: {"result": "not-applicable", "evidence": None}
                        for field in ("capability_listing", "representative_read", "failure_path", "write_boundary")
                    },
                },
            }
        }
    return document, catalog, skills


def findings(
    document: dict[str, Any],
    catalog: dict[str, Any],
    skills: Path,
    root: Path,
    verifier: FakeVerifier | None = None,
) -> list[str]:
    return [
        str(item)
        for item in validate_document(
            document,
            catalog,
            skills,
            require_approval=True,
            as_of=date(2026, 7, 24),
            schema=SCHEMA,
            repository_root=root,
            evidence_verifier=verifier or FakeVerifier(),
        )
    ]


def test_public_schema_is_valid() -> None:
    Draft202012Validator.check_schema(SCHEMA)


def test_provider_backed_assessment_binds_exact_claims(tmp_path: Path) -> None:
    document, catalog, skills = assessment_for(tmp_path)
    verifier = FakeVerifier()
    assert findings(document, catalog, skills, tmp_path, verifier) == []
    claims = [reference["_expected_claim"] for reference in verifier.action_references]
    assert {claim["kind"] for claim in claims} == {"rule", "compatibility"}
    assert verifier.artifact_references[0]["_expected_claim"]["kind"] == "artifact"
    assert verifier.review_calls == 1


def test_green_but_wrong_lane_is_rejected_before_provider_lookup(tmp_path: Path) -> None:
    document, catalog, skills = assessment_for(tmp_path)
    document["compatibility_results"][0]["evidence"]["lane"] = "documentation"
    result = "\n".join(findings(document, catalog, skills, tmp_path))
    assert "must equal the claimed compatibility lane" in result


def test_provider_failures_block_approval(tmp_path: Path) -> None:
    document, catalog, skills = assessment_for(tmp_path)
    result = "\n".join(findings(document, catalog, skills, tmp_path, FakeVerifier(["wrong job"])))
    assert "provider verification failed: wrong job" in result


def test_structural_attestation_cannot_approve(tmp_path: Path) -> None:
    document, catalog, skills = assessment_for(tmp_path)
    document["verification_mode"] = "structural-attestation"
    assert "approval requires provider-backed evidence" in "\n".join(findings(document, catalog, skills, tmp_path))


def test_not_applicable_transport_requires_null_evidence(tmp_path: Path) -> None:
    document, catalog, skills = assessment_for(tmp_path, skill_name="mcp-server-architect", mcp=True)
    assert findings(document, catalog, skills, tmp_path) == []
    check = document["extensions"]["mcp"]["transport_results"]["streamable_http"]["failure_path"]
    check["evidence"] = evidence(99)
    assert "is not of type 'null'" in "\n".join(findings(document, catalog, skills, tmp_path))


@pytest.mark.skipif(os.name == "nt", reason="symlink creation requires platform privileges on some Windows runners")
def test_artifact_paths_reject_leaf_parent_dangling_and_nested_symlinks(tmp_path: Path) -> None:
    document, catalog, skills = assessment_for(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")

    leaf = tmp_path / "leaf-link"
    leaf.symlink_to(outside)
    document["artifact_verification"]["artifacts"][0]["path"] = "leaf-link"
    assert "without symlinks" in "\n".join(findings(document, catalog, skills, tmp_path))

    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    (real_parent / "artifact.txt").write_text("nested\n", encoding="utf-8")
    parent_link = tmp_path / "parent-link"
    parent_link.symlink_to(real_parent, target_is_directory=True)
    document["artifact_verification"]["artifacts"][0]["path"] = "parent-link/artifact.txt"
    assert "without symlinks" in "\n".join(findings(document, catalog, skills, tmp_path))

    dangling = tmp_path / "dangling"
    dangling.symlink_to(tmp_path / "missing")
    document["artifact_verification"]["artifacts"][0]["path"] = "dangling"
    assert "without symlinks" in "\n".join(findings(document, catalog, skills, tmp_path))

    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "safe.txt").write_text("safe\n", encoding="utf-8")
    (tree / "nested-link").symlink_to(outside)
    with pytest.raises(ValueError, match="contains symlink"):
        _path_digest(tree)


def test_candidate_local_verifier_cannot_approve(tmp_path: Path) -> None:
    document, catalog, skills = assessment_for(tmp_path)
    result = "\n".join(
        findings(
            document,
            catalog,
            skills,
            tmp_path,
            FakeVerifier(acceptance_authority=None),
        )
    )
    assert "candidate-local verification is diagnostic only" in result


def test_authority_mismatch_fails_closed(tmp_path: Path) -> None:
    document, catalog, skills = assessment_for(tmp_path)
    different = dict(AUTHORITY, verifier_revision="d" * 40)
    result = "\n".join(
        findings(
            document,
            catalog,
            skills,
            tmp_path,
            FakeVerifier(acceptance_authority=different),
        )
    )
    assert "does not match the authority used by the verifier" in result


def test_assessed_repository_cannot_be_its_own_acceptance_authority(tmp_path: Path) -> None:
    document, catalog, skills = assessment_for(tmp_path)
    document["acceptance_authority"]["verifier_repository"] = REPOSITORY
    result = "\n".join(findings(document, catalog, skills, tmp_path))
    assert "must be external to the assessed repository" in result


def test_empty_directory_changes_artifact_tree_digest(tmp_path: Path) -> None:
    tree = tmp_path / "tree-digest"
    tree.mkdir()
    before = _path_digest(tree)
    (tree / "empty").mkdir()
    after = _path_digest(tree)
    assert before != after


def test_mcp_applicability_is_derived_from_catalog_context(tmp_path: Path) -> None:
    document, catalog, skills = assessment_for(
        tmp_path,
        skill_name="mcp-server-architect",
        mcp=True,
    )
    catalog["skills"]["mcp-server-architect"]["rules"][0]["applies_when"] = {"maturity_at_least": "L4"}
    result = "\n".join(findings(document, catalog, skills, tmp_path))
    assert "catalog applicability requires this rule to be not-applicable" in result

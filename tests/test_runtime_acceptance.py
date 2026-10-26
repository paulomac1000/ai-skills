"""Regression tests for the provider-neutral RuntimeAcceptanceReceipt v1 contract (#97).

Negative cases are separated from schema-construction cases. No test may pass
because an expected value was silently copied into the observed evidence.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from contracts.runtime_acceptance import (
    AcceptanceCurrentness,
    AcceptanceProfile,
    AcceptanceVerdict,
    ClockProvenance,
    EvidenceAuthority,
    ExpectedRuntime,
    ObservedRuntime,
    ProofResult,
    ProofStatus,
    RuntimeAcceptanceDependencies,
    adjudicate,
    compose_observations,
    compose_receipt,
    dependency_snapshot,
    derive_currentness,
    evaluate_acceptance,
    evidence_set_digest,
    payload_digest,
    verify_receipt,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts" / "runtime-acceptance-receipt.schema.json"

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
SOURCE_A = "a" * 40
SOURCE_B = "b" * 40
OBSERVED_AT = "2026-10-25T12:00:00Z"
LATER_AT = "2026-10-26T12:00:00Z"

SKILL_PROFILE = AcceptanceProfile(
    profile_id="managed-skill-distribution",
    profile_revision="prof-skill-v1",
    policy_revision="policy-v1",
    required_identity_fields=("artifact_digest",),
    required_proof_kinds=("installed_files", "deterministic_helper_test"),
    minimum_authority={
        "installed_files": EvidenceAuthority.INDEPENDENT_OBSERVER,
        "deterministic_helper_test": EvidenceAuthority.QA_DETERMINISTIC,
    },
)

RUNTIME_PROFILE = AcceptanceProfile(
    profile_id="runtime-service",
    profile_revision="prof-runtime-v1",
    policy_revision="policy-v1",
    required_identity_fields=("artifact_digest", "source_revision", "config_revision"),
    required_proof_kinds=("artifact_identity", "readiness", "action_class"),
    minimum_authority={
        "artifact_identity": EvidenceAuthority.INDEPENDENT_OBSERVER,
        "readiness": EvidenceAuthority.INDEPENDENT_OBSERVER,
        "action_class": EvidenceAuthority.INDEPENDENT_OBSERVER,
    },
)


def expected(**overrides: object) -> ExpectedRuntime:
    values: dict[str, object] = {
        "artifact_digest": DIGEST_A,
        "source_revision": SOURCE_A,
        "config_revision": "config-7",
        "deployment_identity": "deployment-fedora-1",
    }
    values.update(overrides)
    return ExpectedRuntime(**values)  # type: ignore[arg-type]


def observed(**overrides: object) -> ObservedRuntime:
    values: dict[str, object] = {
        "runtime_identity_ref": "runtime-identity:fedora-1",
        "runtime_id": "runtime-fedora-1",
        "instance_generation": "generation-42",
        "observed_at": OBSERVED_AT,
        "artifact_digest": DIGEST_A,
        "source_revision": SOURCE_A,
        "artifact_version": "3.32.0",
        "config_revision": "config-7",
        "deployment_identity": "deployment-fedora-1",
    }
    values.update(overrides)
    return ObservedRuntime(**values)  # type: ignore[arg-type]


def proof(
    kind: str,
    status: ProofStatus = ProofStatus.PROVEN,
    authority: EvidenceAuthority = EvidenceAuthority.INDEPENDENT_OBSERVER,
    evidence: str | None = "evidence:1",
) -> ProofResult:
    return ProofResult(kind=kind, status=status, authority=authority, evidence_ref=evidence)


def skill_proofs() -> list[ProofResult]:
    return [
        proof("installed_files"),
        proof("deterministic_helper_test", authority=EvidenceAuthority.QA_DETERMINISTIC),
    ]


def runtime_proofs() -> list[ProofResult]:
    return [
        proof("artifact_identity"),
        proof("readiness"),
        proof("action_class"),
    ]


# --- Invariant A: expected is not observed ---------------------------------


def test_expected_digest_without_observed_artifact_is_inconclusive() -> None:
    decision = evaluate_acceptance(SKILL_PROFILE, expected(), observed(artifact_digest=None), skill_proofs())
    assert decision.verdict is AcceptanceVerdict.INCONCLUSIVE
    assert "required-observed-artifact_digest-unknown" in decision.reason_codes


def test_required_artifact_mismatch_is_rejected() -> None:
    decision = evaluate_acceptance(SKILL_PROFILE, expected(), observed(artifact_digest=DIGEST_B), skill_proofs())
    assert decision.verdict is AcceptanceVerdict.REJECTED
    assert "required-artifact_digest-mismatch" in decision.reason_codes


def test_healthy_process_running_wrong_artifact_is_rejected() -> None:
    proofs = [proof("artifact_identity"), proof("readiness"), proof("action_class")]
    decision = evaluate_acceptance(RUNTIME_PROFILE, expected(), observed(artifact_digest=DIGEST_B), proofs)
    assert decision.verdict is AcceptanceVerdict.REJECTED


def test_required_readiness_failed_is_rejected() -> None:
    proofs = runtime_proofs()
    proofs[1] = proof("readiness", status=ProofStatus.FAILED)
    decision = evaluate_acceptance(RUNTIME_PROFILE, expected(), observed(), proofs)
    assert decision.verdict is AcceptanceVerdict.REJECTED
    assert "required-proof-readiness-failed" in decision.reason_codes


def test_required_proof_unknown_is_inconclusive() -> None:
    proofs = [proof("installed_files"), proof("deterministic_helper_test", status=ProofStatus.UNKNOWN)]
    decision = evaluate_acceptance(SKILL_PROFILE, expected(), observed(), proofs)
    assert decision.verdict is AcceptanceVerdict.INCONCLUSIVE
    assert "required-proof-deterministic_helper_test-unknown" in decision.reason_codes


def test_required_proof_unsupported_is_inconclusive() -> None:
    proofs = [proof("installed_files", status=ProofStatus.UNSUPPORTED), proof("deterministic_helper_test")]
    decision = evaluate_acceptance(SKILL_PROFILE, expected(), observed(), proofs)
    assert decision.verdict is AcceptanceVerdict.INCONCLUSIVE


def test_required_proof_kind_missing_is_inconclusive() -> None:
    decision = evaluate_acceptance(SKILL_PROFILE, expected(), observed(), [proof("installed_files")])
    assert decision.verdict is AcceptanceVerdict.INCONCLUSIVE
    assert "required-proof-deterministic_helper_test-missing" in decision.reason_codes


def test_optional_proof_unsupported_keeps_scoped_acceptance() -> None:
    proofs = skill_proofs() + [proof("model_behavior", status=ProofStatus.UNSUPPORTED, evidence=None)]
    decision = evaluate_acceptance(SKILL_PROFILE, expected(), observed(), proofs)
    assert decision.verdict is AcceptanceVerdict.ACCEPTED


def test_model_behavior_required_profile_stays_non_green_when_not_proven() -> None:
    profile = AcceptanceProfile(
        profile_id="model-behavior-required",
        profile_revision="prof-model-v1",
        policy_revision="policy-v1",
        required_identity_fields=("artifact_digest",),
        required_proof_kinds=("installed_files", "model_behavior"),
        minimum_authority={"installed_files": EvidenceAuthority.INDEPENDENT_OBSERVER},
    )
    proofs = skill_proofs() + [proof("model_behavior", status=ProofStatus.UNKNOWN, evidence=None)]
    decision = evaluate_acceptance(profile, expected(), observed(), proofs)
    assert decision.verdict is AcceptanceVerdict.INCONCLUSIVE


# --- Authority separation (invariant E) ------------------------------------


def test_worker_report_cannot_satisfy_independent_observer_floor() -> None:
    proofs = [
        proof("installed_files", authority=EvidenceAuthority.WORKER_REPORT),
        proof("deterministic_helper_test", authority=EvidenceAuthority.QA_DETERMINISTIC),
    ]
    decision = evaluate_acceptance(SKILL_PROFILE, expected(), observed(), proofs)
    assert decision.verdict is AcceptanceVerdict.REJECTED
    assert "required-proof-installed_files-authority-insufficient" in decision.reason_codes


def test_proven_without_evidence_ref_is_rejected() -> None:
    proofs = [proof("installed_files", evidence=None), proof("deterministic_helper_test")]
    decision = evaluate_acceptance(SKILL_PROFILE, expected(), observed(), proofs)
    assert decision.verdict is AcceptanceVerdict.REJECTED
    assert "required-proof-installed_files-evidence-missing" in decision.reason_codes


# --- Target binding ---------------------------------------------------------


def test_observation_from_other_deployment_is_rejected() -> None:
    decision = evaluate_acceptance(
        RUNTIME_PROFILE, expected(), observed(deployment_identity="deployment-terminal101"), runtime_proofs()
    )
    assert decision.verdict is AcceptanceVerdict.REJECTED
    assert "target-binding-mismatch" in decision.reason_codes


def test_missing_observed_deployment_identity_is_inconclusive() -> None:
    decision = evaluate_acceptance(RUNTIME_PROFILE, expected(), observed(deployment_identity=None), runtime_proofs())
    assert decision.verdict is AcceptanceVerdict.INCONCLUSIVE
    assert "target-binding-unknown" in decision.reason_codes


# --- Conflicting observations -----------------------------------------------


def test_conflicting_observations_cannot_compose_one_pass() -> None:
    first = observed()
    second = observed(artifact_digest=DIGEST_B, observed_at=LATER_AT)
    with pytest.raises(ValueError, match="artifact_digest"):
        compose_observations([first, second])


def test_conflicting_generations_cannot_compose() -> None:
    with pytest.raises(ValueError, match="instance_generation"):
        compose_observations([observed(), observed(instance_generation="generation-43", observed_at=LATER_AT)])


def test_compose_observations_fills_missing_fields() -> None:
    merged = compose_observations(
        [
            observed(artifact_digest=None),
            observed(artifact_digest=DIGEST_A, observed_at=LATER_AT),
        ]
    )
    assert merged.artifact_digest == DIGEST_A
    assert merged.observed_at == LATER_AT


def test_duplicate_proof_kind_is_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate proof kind"):
        evaluate_acceptance(SKILL_PROFILE, expected(), observed(), [proof("installed_files"), proof("installed_files")])


# --- Currentness / staleness -------------------------------------------------


def dependencies(generation: str = "generation-42", config: str = "config-7") -> RuntimeAcceptanceDependencies:
    return RuntimeAcceptanceDependencies(
        artifact_digest=DIGEST_A,
        source_revision=SOURCE_A,
        config_revision=config,
        instance_generation=generation,
        profile_revision="prof-skill-v1",
        policy_revision="policy-v1",
    )


def test_generation_change_without_artifact_change_is_stale() -> None:
    current = dependencies(generation="generation-43")
    assert derive_currentness(dependencies(), current) is AcceptanceCurrentness.STALE


def test_config_revision_change_is_stale() -> None:
    assert derive_currentness(dependencies(), dependencies(config="config-8")) is AcceptanceCurrentness.STALE


def test_policy_revision_change_is_stale() -> None:
    current = dependencies()
    current = RuntimeAcceptanceDependencies(
        artifact_digest=DIGEST_A,
        source_revision=SOURCE_A,
        config_revision="config-7",
        instance_generation="generation-42",
        profile_revision="prof-skill-v1",
        policy_revision="policy-v2",
    )
    assert derive_currentness(dependencies(), current) is AcceptanceCurrentness.STALE


def test_profile_revision_change_is_stale() -> None:
    current = RuntimeAcceptanceDependencies(
        artifact_digest=DIGEST_A,
        source_revision=SOURCE_A,
        config_revision="config-7",
        instance_generation="generation-42",
        profile_revision="prof-skill-v2",
        policy_revision="policy-v1",
    )
    assert derive_currentness(dependencies(), current) is AcceptanceCurrentness.STALE


def test_missing_current_observation_is_unknown() -> None:
    current = RuntimeAcceptanceDependencies(
        artifact_digest=None,
        source_revision=SOURCE_A,
        config_revision="config-7",
        instance_generation="generation-42",
        profile_revision="prof-skill-v1",
        policy_revision="policy-v1",
    )
    assert derive_currentness(dependencies(), current) is AcceptanceCurrentness.UNKNOWN


def test_expired_receipt_adjudicates_stale() -> None:
    now = datetime.fromisoformat("2026-10-26T12:00:01+00:00")
    outcome = adjudicate(
        AcceptanceVerdict.ACCEPTED,
        dependencies(),
        dependencies(),
        expires_at="2026-10-26T12:00:00Z",
        now=now,
    )
    assert outcome is AcceptanceVerdict.STALE


def test_rollback_old_pass_does_not_accept_new_generation() -> None:
    outcome = adjudicate(
        AcceptanceVerdict.ACCEPTED,
        dependencies(generation="generation-42"),
        dependencies(generation="generation-43"),
        expires_at=None,
        now=datetime.fromisoformat("2026-10-26T12:00:00+00:00"),
    )
    assert outcome is AcceptanceVerdict.STALE


def test_current_receipt_adjudicates_accepted() -> None:
    outcome = adjudicate(
        AcceptanceVerdict.ACCEPTED,
        dependencies(),
        dependencies(),
        expires_at=None,
        now=datetime.fromisoformat("2026-10-26T12:00:00+00:00"),
    )
    assert outcome is AcceptanceVerdict.ACCEPTED


def test_rejected_verdict_passes_through_adjudication() -> None:
    outcome = adjudicate(
        AcceptanceVerdict.REJECTED,
        dependencies(),
        dependencies(generation="generation-99"),
        expires_at=None,
        now=datetime.fromisoformat("2026-10-26T12:00:00+00:00"),
    )
    assert outcome is AcceptanceVerdict.REJECTED


# --- Managed-skill profile conformance (Stage D) ------------------------


def test_managed_skill_profile_full_acceptance() -> None:
    decision = evaluate_acceptance(SKILL_PROFILE, expected(), observed(), skill_proofs())
    assert decision.verdict is AcceptanceVerdict.ACCEPTED


def test_managed_skill_wrong_helper_release_is_rejected() -> None:
    decision = evaluate_acceptance(SKILL_PROFILE, expected(), observed(artifact_digest=DIGEST_C), skill_proofs())
    assert decision.verdict is AcceptanceVerdict.REJECTED


# --- Runtime-service profile conformance (Stage D) ---------------------------


def test_runtime_service_profile_full_acceptance() -> None:
    decision = evaluate_acceptance(RUNTIME_PROFILE, expected(), observed(), runtime_proofs())
    assert decision.verdict is AcceptanceVerdict.ACCEPTED


def test_runtime_service_requires_consumer_route_when_profiled() -> None:
    profile = AcceptanceProfile(
        profile_id="runtime-service-routed",
        profile_revision="prof-runtime-routed-v1",
        policy_revision="policy-v1",
        required_identity_fields=("artifact_digest", "source_revision", "config_revision"),
        required_proof_kinds=("artifact_identity", "readiness", "action_class", "consumer_route"),
        minimum_authority={
            "artifact_identity": EvidenceAuthority.INDEPENDENT_OBSERVER,
            "readiness": EvidenceAuthority.INDEPENDENT_OBSERVER,
            "action_class": EvidenceAuthority.INDEPENDENT_OBSERVER,
            "consumer_route": EvidenceAuthority.INDEPENDENT_OBSERVER,
        },
    )
    decision = evaluate_acceptance(profile, expected(), observed(), runtime_proofs())
    assert decision.verdict is AcceptanceVerdict.INCONCLUSIVE
    assert "required-proof-consumer_route-missing" in decision.reason_codes

    routed = runtime_proofs() + [proof("consumer_route")]
    assert evaluate_acceptance(profile, expected(), observed(), routed).verdict is AcceptanceVerdict.ACCEPTED


def test_load_bearing_dependency_unknown_blocks_acceptance() -> None:
    profile = AcceptanceProfile(
        profile_id="runtime-service-dependents",
        profile_revision="prof-runtime-deps-v1",
        policy_revision="policy-v1",
        required_identity_fields=("artifact_digest", "source_revision", "config_revision"),
        required_proof_kinds=("artifact_identity", "readiness", "action_class", "dependency:yolo-detector-v2"),
        minimum_authority={
            "artifact_identity": EvidenceAuthority.INDEPENDENT_OBSERVER,
            "readiness": EvidenceAuthority.INDEPENDENT_OBSERVER,
            "action_class": EvidenceAuthority.INDEPENDENT_OBSERVER,
            "dependency:yolo-detector-v2": EvidenceAuthority.INDEPENDENT_OBSERVER,
        },
    )
    proofs = runtime_proofs() + [proof("dependency:yolo-detector-v2", status=ProofStatus.UNKNOWN)]
    decision = evaluate_acceptance(profile, expected(), observed(), proofs)
    assert decision.verdict is AcceptanceVerdict.INCONCLUSIVE
    assert "required-proof-dependency:yolo-detector-v2-unknown" in decision.reason_codes


# --- Receipt composition and integrity ---------------------------------------


def composed_document() -> dict[str, object]:
    return compose_receipt(
        acceptance_id="acceptance-fedora-1-0001",
        profile=SKILL_PROFILE,
        target_environment_class="workstation",
        target_deployment_identity="deployment-fedora-1",
        target_identity="host:fedora",
        expected=expected(),
        observed=observed(),
        proofs=skill_proofs(),
        evidence_refs=["evidence:1", "evidence:2"],
        expires_at=None,
    )


def test_compose_receipt_verdict_matches_evaluation() -> None:
    document = composed_document()
    assert document["verdict"] == "accepted"
    assert document["currentness_at_issue"] == "CURRENT"


def test_version_is_not_runtime_generation() -> None:
    document = composed_document()
    observed_block = document["observed"]
    assert isinstance(observed_block, dict)
    assert observed_block["artifact_version"] == "3.32.0"
    assert observed_block["instance_generation"] == "generation-42"
    assert observed_block["artifact_version"] != observed_block["instance_generation"]
    snapshot = document["dependency_snapshot"]
    assert isinstance(snapshot, dict)
    assert snapshot["instance_generation"] == "generation-42"


def test_evidence_set_digest_is_order_insensitive_and_bound() -> None:
    assert evidence_set_digest(["evidence:2", "evidence:1"]) == evidence_set_digest(["evidence:1", "evidence:2"])
    document = composed_document()
    inputs = document["inputs"]
    assert isinstance(inputs, dict)
    assert inputs["evidence_set_digest"] == evidence_set_digest(["evidence:1", "evidence:2"])


def test_evidence_set_digest_mismatch_is_detected() -> None:
    document = composed_document()
    inputs = document["inputs"]
    assert isinstance(inputs, dict)
    inputs["evidence_set_digest"] = "sha256:" + "f" * 64
    findings = verify_receipt(document, schema_path=SCHEMA_PATH)
    assert any("evidence_set_digest" in finding for finding in findings)


def test_payload_digest_mismatch_is_detected() -> None:
    document = composed_document()
    document["payload_digest"] = "sha256:" + "0" * 64
    findings = verify_receipt(document, schema_path=SCHEMA_PATH)
    assert any("payload_digest" in finding for finding in findings)


def test_payload_digest_excludes_itself_and_is_stable() -> None:
    document = composed_document()
    digest = payload_digest(document)
    assert digest == document["payload_digest"]
    tampered = dict(document)
    tampered["acceptance_id"] = "acceptance-fedora-1-0002"
    assert payload_digest(tampered) != digest


def test_verify_clean_receipt_has_no_findings() -> None:
    assert verify_receipt(composed_document(), schema_path=SCHEMA_PATH) == []


def test_schema_rejects_unknown_top_level_field() -> None:
    document = composed_document()
    document["surprise"] = "value"
    validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    errors = list(validator.iter_errors(document))
    assert any("surprise" in error.message for error in errors)


def test_schema_rejects_overlong_field() -> None:
    document = composed_document()
    document["acceptance_id"] = "x" * 257
    validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    errors = list(validator.iter_errors(document))
    assert len(errors) == 1


def test_schema_requires_evidence_ref_for_proven_status() -> None:
    document = composed_document()
    proofs_block = document["proofs"]
    assert isinstance(proofs_block, list)
    proofs_block[0]["evidence_ref"] = None
    validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    errors = list(validator.iter_errors(document))
    assert len(errors) >= 1


def test_naive_clock_cannot_claim_exact_normalization() -> None:
    document = composed_document()
    observed_block = document["observed"]
    assert isinstance(observed_block, dict)
    observed_block["clock_provenance"] = {
        "source_timestamp": "2026-10-25T14:00:00",
        "source_offset": None,
        "source_clock": "filesystem",
        "normalization": "exact",
    }
    findings = verify_receipt(document, schema_path=SCHEMA_PATH)
    assert any("clock" in finding for finding in findings)


def test_derived_clock_normalization_is_explicit_and_clean() -> None:
    document = composed_document()
    observed_block = document["observed"]
    assert isinstance(observed_block, dict)
    observed_block["clock_provenance"] = ClockProvenance(
        source_timestamp="2026-10-25T14:00:00",
        source_offset=None,
        source_clock="filesystem",
        normalization="derived",
    ).as_document()
    document["payload_digest"] = payload_digest(document)
    assert verify_receipt(document, schema_path=SCHEMA_PATH) == []


def test_naive_observed_at_without_timezone_is_detected() -> None:
    document = composed_document()
    observed_block = document["observed"]
    assert isinstance(observed_block, dict)
    observed_block["observed_at"] = "2026-10-25T12:00:00"
    findings = verify_receipt(document, schema_path=SCHEMA_PATH)
    assert any("observed_at" in finding for finding in findings)


def test_dependency_snapshot_roundtrip() -> None:
    snapshot = dependency_snapshot(SKILL_PROFILE, observed())
    assert snapshot == dependencies()

"""Regression tests for the provider-neutral RuntimeAcceptanceReceipt v1 contract (#97).

Negative cases are separated from schema-construction cases. No test may pass
because an expected value was silently copied into the observed evidence.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import cast

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
    adjudicate_current,
    authority_satisfies,
    compose_observations,
    compose_receipt,
    dependency_snapshot,
    derive_currentness,
    evaluate_acceptance,
    evidence_set_digest,
    payload_digest,
    profile_digest,
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
    runtime_generation: str | None = "generation-42",
    runtime_id: str | None = "runtime-fedora-1",
) -> ProofResult:
    return ProofResult(
        kind=kind,
        status=status,
        authority=authority,
        evidence_ref=evidence,
        runtime_generation=runtime_generation,
        runtime_id=runtime_id,
    )


def skill_proofs(
    runtime_generation: str | None = "generation-42", runtime_id: str | None = "runtime-fedora-1"
) -> list[ProofResult]:
    return [
        proof("installed_files", runtime_generation=runtime_generation, runtime_id=runtime_id),
        proof(
            "deterministic_helper_test",
            authority=EvidenceAuthority.QA_DETERMINISTIC,
            runtime_generation=runtime_generation,
            runtime_id=runtime_id,
        ),
    ]


def runtime_proofs(runtime_id: str = "runtime-fedora-1") -> list[ProofResult]:
    return [
        proof("artifact_identity", runtime_id=runtime_id),
        proof("readiness", runtime_id=runtime_id),
        proof("action_class", runtime_id=runtime_id),
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


def dependencies(
    runtime_id: str = "runtime-fedora-1",
    generation: str = "generation-42",
    config: str = "config-7",
    profile: AcceptanceProfile | None = None,
    deployment_identity: str | None = "deployment-fedora-1",
) -> RuntimeAcceptanceDependencies:
    resolved = profile or SKILL_PROFILE
    return RuntimeAcceptanceDependencies(
        runtime_id=runtime_id,
        artifact_digest=DIGEST_A,
        source_revision=SOURCE_A,
        config_revision=config,
        instance_generation=generation,
        profile_id=resolved.profile_id,
        profile_digest=profile_digest(resolved),
        policy_revision=resolved.policy_revision,
        deployment_identity=deployment_identity,
    )


def test_generation_change_without_artifact_change_is_stale() -> None:
    current = dependencies(generation="generation-43")
    assert derive_currentness(dependencies(), current) is AcceptanceCurrentness.STALE


def test_config_revision_change_is_stale() -> None:
    assert derive_currentness(dependencies(), dependencies(config="config-8")) is AcceptanceCurrentness.STALE


def test_policy_revision_change_is_stale() -> None:
    current = dependencies()
    current = RuntimeAcceptanceDependencies(
        runtime_id="runtime-fedora-1",
        artifact_digest=DIGEST_A,
        source_revision=SOURCE_A,
        config_revision="config-7",
        instance_generation="generation-42",
        profile_id="managed-skill-distribution",
        profile_digest=profile_digest(SKILL_PROFILE),
        policy_revision="policy-v2",
    )
    assert derive_currentness(dependencies(), current) is AcceptanceCurrentness.STALE


def test_profile_revision_change_is_stale() -> None:
    drifted = AcceptanceProfile(
        profile_id=SKILL_PROFILE.profile_id,
        profile_revision="prof-skill-v2",
        policy_revision=SKILL_PROFILE.policy_revision,
        required_identity_fields=SKILL_PROFILE.required_identity_fields,
        required_proof_kinds=SKILL_PROFILE.required_proof_kinds,
        minimum_authority=SKILL_PROFILE.minimum_authority,
    )
    current = dependencies(profile=drifted)
    assert current.profile_digest != profile_digest(SKILL_PROFILE)
    assert derive_currentness(dependencies(), current) is AcceptanceCurrentness.STALE


def test_different_profile_same_revision_is_stale() -> None:
    other = AcceptanceProfile(
        profile_id="other-profile",
        profile_revision=SKILL_PROFILE.profile_revision,
        policy_revision=SKILL_PROFILE.policy_revision,
        required_identity_fields=SKILL_PROFILE.required_identity_fields,
        required_proof_kinds=SKILL_PROFILE.required_proof_kinds,
        minimum_authority=SKILL_PROFILE.minimum_authority,
    )
    assert derive_currentness(dependencies(), dependencies(profile=other)) is AcceptanceCurrentness.STALE


def test_missing_current_observation_is_unknown() -> None:
    current = RuntimeAcceptanceDependencies(
        runtime_id="runtime-fedora-1",
        artifact_digest=None,
        source_revision=SOURCE_A,
        config_revision="config-7",
        instance_generation="generation-42",
        profile_id="managed-skill-distribution",
        profile_digest=profile_digest(SKILL_PROFILE),
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


# --- Review round 1 blockers -------------------------------------------------


def test_forged_accepted_verdict_is_detected_by_verify() -> None:
    document = composed_document()
    document["verdict"] = "accepted"
    document["payload_digest"] = payload_digest(document)
    forged = dict(document)
    proofs_block = forged["proofs"]
    assert isinstance(proofs_block, list)
    proofs_block[1]["status"] = "failed"
    forged["payload_digest"] = payload_digest(forged)
    findings = verify_receipt(forged, schema_path=SCHEMA_PATH, profile=SKILL_PROFILE)
    assert any("verdict" in finding for finding in findings)


def test_verify_rejects_snapshot_disagreeing_with_observed() -> None:
    document = composed_document()
    snapshot = document["dependency_snapshot"]
    assert isinstance(snapshot, dict)
    snapshot["instance_generation"] = "generation-999"
    document["payload_digest"] = payload_digest(document)
    findings = verify_receipt(document, schema_path=SCHEMA_PATH, profile=SKILL_PROFILE)
    assert any("dependency_snapshot" in finding for finding in findings)


def test_old_generation_proof_cannot_accept_new_generation() -> None:
    proofs = [
        proof("installed_files", runtime_generation="generation-41"),
        proof(
            "deterministic_helper_test",
            runtime_generation="generation-41",
            authority=EvidenceAuthority.QA_DETERMINISTIC,
        ),
    ]
    decision = evaluate_acceptance(SKILL_PROFILE, expected(), observed(), proofs)
    assert decision.verdict is AcceptanceVerdict.REJECTED
    assert "required-proof-installed_files-generation-mismatch" in decision.reason_codes


def test_unbound_proof_is_rejected_for_generation_bound_profile() -> None:
    proofs = [
        proof("installed_files", runtime_generation=None),
        proof("deterministic_helper_test", authority=EvidenceAuthority.QA_DETERMINISTIC),
    ]
    decision = evaluate_acceptance(SKILL_PROFILE, expected(), observed(), proofs)
    assert decision.verdict is AcceptanceVerdict.REJECTED
    assert "required-proof-installed_files-generation-unbound" in decision.reason_codes


def test_receipt_target_disagreeing_with_evaluated_target_is_rejected() -> None:
    with pytest.raises(ValueError, match="target deployment identity"):
        compose_receipt(
            acceptance_id="acceptance-cross-target",
            profile=SKILL_PROFILE,
            target_environment_class="production",
            target_deployment_identity="deployment-production-9",
            target_identity="host:other",
            expected=expected(),
            observed=observed(),
            proofs=skill_proofs(runtime_generation="generation-42"),
            evidence_refs=["evidence:1", "evidence:2"],
        )


def test_proof_evidence_outside_evidence_set_is_detected() -> None:
    document = composed_document()
    proofs_block = document["proofs"]
    assert isinstance(proofs_block, list)
    proofs_block[0]["evidence_ref"] = "evidence:rogue"
    document["payload_digest"] = payload_digest(document)
    findings = verify_receipt(document, schema_path=SCHEMA_PATH)
    assert any("evidence:rogue" in finding for finding in findings)


# --- Review round 2/3: majors ------------------------------------------------


def test_model_review_cannot_satisfy_deterministic_qa_floor() -> None:
    assert not authority_satisfies(EvidenceAuthority.MODEL_REVIEW, EvidenceAuthority.QA_DETERMINISTIC)
    assert authority_satisfies(EvidenceAuthority.QA_DETERMINISTIC, EvidenceAuthority.QA_DETERMINISTIC)
    assert authority_satisfies(EvidenceAuthority.INDEPENDENT_OBSERVER, EvidenceAuthority.QA_DETERMINISTIC)
    proofs = [
        proof("installed_files"),
        proof("deterministic_helper_test", authority=EvidenceAuthority.MODEL_REVIEW),
    ]
    decision = evaluate_acceptance(SKILL_PROFILE, expected(), observed(), proofs)
    assert decision.verdict is AcceptanceVerdict.REJECTED
    assert "required-proof-deterministic_helper_test-authority-insufficient" in decision.reason_codes


def test_receipt_binds_the_complete_acceptance_profile_digest() -> None:
    document = composed_document()
    profile_block = document["acceptance_profile"]
    assert isinstance(profile_block, dict)
    assert profile_block["digest"] == profile_digest(SKILL_PROFILE)
    assert verify_receipt(document, schema_path=SCHEMA_PATH, profile=SKILL_PROFILE) == []
    drifted = AcceptanceProfile(
        profile_id=SKILL_PROFILE.profile_id,
        profile_revision=SKILL_PROFILE.profile_revision,
        policy_revision="policy-v2",
        required_identity_fields=SKILL_PROFILE.required_identity_fields,
        required_proof_kinds=SKILL_PROFILE.required_proof_kinds,
        minimum_authority=SKILL_PROFILE.minimum_authority,
    )
    findings = verify_receipt(document, schema_path=SCHEMA_PATH, profile=drifted)
    assert any("acceptance_profile.digest" in finding for finding in findings)


def test_rejected_receipt_keeps_typed_reason_codes() -> None:
    document = compose_receipt(
        acceptance_id="acceptance-rejected-1",
        profile=SKILL_PROFILE,
        target_environment_class="workstation",
        target_deployment_identity="deployment-fedora-1",
        target_identity="host:fedora",
        expected=expected(),
        observed=observed(artifact_digest=DIGEST_B),
        proofs=skill_proofs(),
        evidence_refs=["evidence:1", "evidence:2"],
    )
    assert document["verdict"] == "rejected"
    reasons = document["reason_codes"]
    assert isinstance(reasons, list)
    assert "required-artifact_digest-mismatch" in reasons
    findings = verify_receipt(document, schema_path=SCHEMA_PATH, profile=SKILL_PROFILE)
    assert findings == []


def test_verify_detects_tampered_reason_codes() -> None:
    document = compose_receipt(
        acceptance_id="acceptance-rejected-2",
        profile=SKILL_PROFILE,
        target_environment_class="workstation",
        target_deployment_identity="deployment-fedora-1",
        target_identity="host:fedora",
        expected=expected(),
        observed=observed(artifact_digest=DIGEST_B),
        proofs=skill_proofs(),
        evidence_refs=["evidence:1", "evidence:2"],
    )
    document["reason_codes"] = []
    document["payload_digest"] = payload_digest(document)
    findings = verify_receipt(document, schema_path=SCHEMA_PATH, profile=SKILL_PROFILE)
    assert any("reason_codes mismatch" in finding for finding in findings)


def test_compose_observations_preserves_provenance_refs() -> None:
    first = observed(provenance_refs=("obs:a",))
    second = observed(artifact_digest=None, observed_at=LATER_AT, provenance_refs=("obs:b",))
    merged = compose_observations([first, second])
    assert set(merged.provenance_refs) == {"runtime-identity:fedora-1", "obs:a", "obs:b"}


def test_adjudicate_requires_timezone_aware_now() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        adjudicate(
            AcceptanceVerdict.ACCEPTED,
            dependencies(),
            dependencies(),
            expires_at=None,
            now=datetime(2026, 10, 26, 12, 0, 0),
        )


def test_adjudicate_detects_replayed_stale_observation() -> None:
    outcome = adjudicate(
        AcceptanceVerdict.ACCEPTED,
        dependencies(),
        dependencies(),
        expires_at=None,
        now=datetime.fromisoformat("2026-10-26T12:00:00+00:00"),
        current_observation=observed(observed_at="2026-10-20T12:00:00Z"),
        max_age_seconds=3600,
    )
    assert outcome is AcceptanceVerdict.STALE


def test_stale_current_observation_adjudicates_stale() -> None:
    outcome = adjudicate(
        AcceptanceVerdict.ACCEPTED,
        dependencies(),
        dependencies(),
        expires_at=None,
        now=datetime.fromisoformat("2026-10-26T12:00:00+00:00"),
        current_observation=observed(observed_at="2026-10-20T12:00:00Z"),
        max_age_seconds=3600,
    )
    assert outcome is AcceptanceVerdict.STALE


def test_fresh_current_observation_adjudicates_accepted() -> None:
    outcome = adjudicate(
        AcceptanceVerdict.ACCEPTED,
        dependencies(),
        dependencies(),
        expires_at=None,
        now=datetime.fromisoformat("2026-10-25T12:30:00+00:00"),
        current_observation=observed(),
        max_age_seconds=3600,
    )
    assert outcome is AcceptanceVerdict.ACCEPTED


def test_authoritative_adjudication_requires_observation_and_window() -> None:
    now = datetime.fromisoformat("2026-10-26T12:00:00+00:00")
    with pytest.raises(TypeError):
        adjudicate_current(
            AcceptanceVerdict.ACCEPTED,
            dependencies(),
            dependencies(),
            now=now,
        )
    with pytest.raises(ValueError, match="freshness window"):
        adjudicate_current(
            AcceptanceVerdict.ACCEPTED,
            dependencies(),
            dependencies(),
            now=now,
            current_observation=observed(),
            max_age_seconds=0,
        )
    with pytest.raises(ValueError, match="clock-skew"):
        adjudicate_current(
            AcceptanceVerdict.ACCEPTED,
            dependencies(),
            dependencies(),
            now=now,
            current_observation=observed(observed_at="2026-10-26T13:00:00Z"),
            max_age_seconds=3600,
        )


def test_authoritative_adjudication_detects_missing_fresh_evidence() -> None:
    now = datetime.fromisoformat("2026-10-26T12:00:00+00:00")
    outcome = adjudicate_current(
        AcceptanceVerdict.ACCEPTED,
        dependencies(),
        dependencies(),
        now=now,
        current_observation=observed(observed_at="2026-10-20T12:00:00Z"),
        max_age_seconds=3600,
    )
    assert outcome is AcceptanceVerdict.STALE
    fresh = adjudicate_current(
        AcceptanceVerdict.ACCEPTED,
        dependencies(),
        dependencies(),
        now=now,
        current_observation=observed(observed_at="2026-10-26T11:30:00Z"),
        max_age_seconds=3600,
    )
    assert fresh is AcceptanceVerdict.ACCEPTED
    skewed = adjudicate_current(
        AcceptanceVerdict.ACCEPTED,
        dependencies(),
        dependencies(),
        now=now,
        current_observation=observed(observed_at="2026-10-26T12:00:10Z"),
        max_age_seconds=3600,
        clock_skew_seconds=60,
    )
    assert skewed is AcceptanceVerdict.ACCEPTED


def test_compose_rejects_schema_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="at least one proof"):
        compose_receipt(
            acceptance_id="acceptance-empty",
            profile=SKILL_PROFILE,
            target_environment_class="workstation",
            target_deployment_identity="deployment-fedora-1",
            target_identity=None,
            expected=expected(),
            observed=observed(),
            proofs=[],
            evidence_refs=["evidence:1"],
        )
    with pytest.raises(ValueError, match="acceptance id"):
        compose_receipt(
            acceptance_id="x" * 257,
            profile=SKILL_PROFILE,
            target_environment_class="workstation",
            target_deployment_identity="deployment-fedora-1",
            target_identity=None,
            expected=expected(),
            observed=observed(),
            proofs=skill_proofs(),
            evidence_refs=["evidence:1"],
        )
    with pytest.raises(ValueError, match="sha256"):
        compose_receipt(
            acceptance_id="acceptance-bad-digest",
            profile=SKILL_PROFILE,
            target_environment_class="workstation",
            target_deployment_identity="deployment-fedora-1",
            target_identity=None,
            expected=expected(artifact_digest="not-a-digest"),
            observed=observed(),
            proofs=skill_proofs(),
            evidence_refs=["evidence:1"],
        )
    with pytest.raises(ValueError, match="ISO 8601"):
        compose_receipt(
            acceptance_id="acceptance-bad-expiry",
            profile=SKILL_PROFILE,
            target_environment_class="workstation",
            target_deployment_identity="deployment-fedora-1",
            target_identity=None,
            expected=expected(),
            observed=observed(),
            proofs=skill_proofs(),
            evidence_refs=["evidence:1"],
            expires_at="yesterday",
        )


def test_composed_receipt_passes_full_schema_validation() -> None:
    document = composed_document()
    assert verify_receipt(document, schema_path=SCHEMA_PATH, profile=SKILL_PROFILE) == []


def test_verify_reruns_runtime_service_profile_without_false_mismatch() -> None:
    document = compose_receipt(
        acceptance_id="acceptance-runtime-service-1",
        profile=RUNTIME_PROFILE,
        target_environment_class="server",
        target_deployment_identity="deployment-fedora-1",
        target_identity="host:fedora",
        expected=expected(),
        observed=observed(),
        proofs=runtime_proofs(),
        evidence_refs=["evidence:1", "evidence:2"],
    )
    assert document["verdict"] == "accepted"
    assert verify_receipt(document, schema_path=SCHEMA_PATH, profile=RUNTIME_PROFILE) == []


def test_tampered_receipt_target_is_detected_by_verify() -> None:
    document = compose_receipt(
        acceptance_id="acceptance-tamper-target",
        profile=SKILL_PROFILE,
        target_environment_class="workstation",
        target_deployment_identity="deployment-fedora-1",
        target_identity="host:fedora",
        expected=expected(),
        observed=observed(),
        proofs=skill_proofs(),
        evidence_refs=["evidence:1", "evidence:2"],
    )
    target_block = document["target"]
    assert isinstance(target_block, dict)
    target_block["deployment_identity"] = "deployment-production-9"
    document["payload_digest"] = payload_digest(document)
    findings = verify_receipt(document, schema_path=SCHEMA_PATH, profile=SKILL_PROFILE)
    assert any("target.deployment_identity mismatch" in finding for finding in findings)


def test_tampered_required_flag_is_detected_by_verify() -> None:
    document = composed_document()
    proofs_block = document["proofs"]
    assert isinstance(proofs_block, list)
    proofs_block[1]["required"] = False
    document["payload_digest"] = payload_digest(document)
    findings = verify_receipt(document, schema_path=SCHEMA_PATH, profile=SKILL_PROFILE)
    assert any("required flag" in finding for finding in findings)


def test_compose_observations_keeps_every_source_identity_reference() -> None:
    merged = compose_observations(
        [
            observed(artifact_digest=None),
            observed(
                artifact_digest=DIGEST_A, observed_at=LATER_AT, runtime_identity_ref="runtime-identity:observer-b"
            ),
        ]
    )
    assert set(merged.provenance_refs) >= {"runtime-identity:fedora-1", "runtime-identity:observer-b"}


def test_verify_tolerates_missing_deployment_identity_for_unbinding_profiles() -> None:
    profile = AcceptanceProfile(
        profile_id="unbound-targets",
        profile_revision="prof-unbound-v1",
        policy_revision="policy-v1",
        required_identity_fields=("artifact_digest",),
        required_proof_kinds=("installed_files",),
        minimum_authority={"installed_files": EvidenceAuthority.INDEPENDENT_OBSERVER},
        require_target_binding=False,
    )
    document = compose_receipt(
        acceptance_id="acceptance-unbound-1",
        profile=profile,
        target_environment_class="workstation",
        target_deployment_identity="target-unspecified",
        target_identity=None,
        expected=expected(deployment_identity=None),
        observed=observed(deployment_identity=None),
        proofs=skill_proofs(),
        evidence_refs=["evidence:1", "evidence:2"],
    )
    assert document["verdict"] == "accepted"
    assert verify_receipt(document, schema_path=SCHEMA_PATH, profile=profile) == []


# --- Bot review threads (round 6.5) ------------------------------------------


def test_merged_observed_at_is_converted_to_utc() -> None:
    merged = compose_observations(
        [observed(observed_at="2026-10-25T14:00:00+02:00")],
    )
    assert merged.observed_at == "2026-10-25T12:00:00Z"


def test_known_stale_dependency_is_not_masked_by_unknown() -> None:
    receipt_deps = dependencies()
    current = RuntimeAcceptanceDependencies(
        runtime_id="runtime-fedora-1",
        artifact_digest=None,
        source_revision=SOURCE_A,
        config_revision="config-9",
        instance_generation="generation-42",
        profile_id="managed-skill-distribution",
        profile_digest=profile_digest(SKILL_PROFILE),
        policy_revision="policy-v1",
    )
    assert derive_currentness(receipt_deps, current) is AcceptanceCurrentness.STALE


def test_runtime_id_change_is_stale() -> None:
    current = dependencies(runtime_id="runtime-fedora-2")
    assert derive_currentness(dependencies(), current) is AcceptanceCurrentness.STALE


def test_deployment_identity_change_is_stale() -> None:
    current = dependencies(deployment_identity="deployment-terminal101")
    assert derive_currentness(dependencies(), current) is AcceptanceCurrentness.STALE


# --- Remediation F1-F3 (#97 closeout) ----------------------------------------


def test_f1_cross_runtime_proof_reuse_same_generation_is_rejected() -> None:
    """Runtime A proof must not accept runtime B when only the generation label matches."""
    runtime_b = observed(runtime_id="runtime-B", deployment_identity="deployment-B")
    proofs_from_a = runtime_proofs(runtime_id="runtime-A")
    decision = evaluate_acceptance(
        RUNTIME_PROFILE,
        expected(deployment_identity="deployment-B"),
        runtime_b,
        proofs_from_a,
    )
    assert decision.verdict is AcceptanceVerdict.REJECTED
    assert "required-proof-artifact_identity-runtime-mismatch" in decision.reason_codes


def test_f1_unbound_runtime_proof_fails_closed() -> None:
    decision = evaluate_acceptance(
        RUNTIME_PROFILE,
        expected(),
        observed(),
        runtime_proofs(runtime_id=None),
    )
    assert decision.verdict is AcceptanceVerdict.REJECTED
    assert "required-proof-artifact_identity-runtime-unbound" in decision.reason_codes


def test_f1_cross_runtime_reuse_cannot_compose_or_verify() -> None:
    document = compose_receipt(
        acceptance_id="f1-end-to-end",
        profile=RUNTIME_PROFILE,
        target_environment_class="server",
        target_deployment_identity="deployment-fedora-1",
        target_identity="host:fedora",
        expected=expected(),
        observed=observed(),
        proofs=runtime_proofs(runtime_id="runtime-OTHER"),
        evidence_refs=["evidence:1", "evidence:2", "evidence:3"],
    )
    assert document["verdict"] == "rejected"
    assert verify_receipt(document, schema_path=SCHEMA_PATH, profile=RUNTIME_PROFILE) == []


def test_f1_proof_runtime_id_is_serialized_and_rechecked() -> None:
    document = compose_receipt(
        acceptance_id="f1-serialization",
        profile=RUNTIME_PROFILE,
        target_environment_class="server",
        target_deployment_identity="deployment-fedora-1",
        target_identity="host:fedora",
        expected=expected(),
        observed=observed(),
        proofs=runtime_proofs(),
        evidence_refs=["evidence:1", "evidence:2", "evidence:3"],
    )
    proofs_block = document["proofs"]
    assert isinstance(proofs_block, list)
    assert all(item["runtime_id"] == "runtime-fedora-1" for item in proofs_block)
    forged = dict(document)
    assert isinstance(forged["proofs"], list)
    forged["proofs"][0]["runtime_id"] = "runtime-OTHER"
    forged["payload_digest"] = payload_digest(forged)
    findings = verify_receipt(forged, schema_path=SCHEMA_PATH, profile=RUNTIME_PROFILE)
    assert any("verdict mismatch" in finding for finding in findings)


def test_f2_profile_identity_is_part_of_currentness() -> None:
    other = AcceptanceProfile(
        profile_id="other-profile",
        profile_revision=SKILL_PROFILE.profile_revision,
        policy_revision=SKILL_PROFILE.policy_revision,
        required_identity_fields=SKILL_PROFILE.required_identity_fields,
        required_proof_kinds=("installed_files", "deterministic_helper_test"),
        minimum_authority=SKILL_PROFILE.minimum_authority,
    )
    assert profile_digest(other) != profile_digest(SKILL_PROFILE)
    fresh = observed(observed_at="2026-10-26T11:59:00Z")
    outcome = adjudicate_current(
        AcceptanceVerdict.ACCEPTED,
        dependency_snapshot(SKILL_PROFILE, observed()),
        dependency_snapshot(other, fresh),
        now=datetime.fromisoformat("2026-10-26T12:00:00+00:00"),
        current_observation=fresh,
        max_age_seconds=3600,
    )
    assert outcome is AcceptanceVerdict.STALE


def test_f3_cross_deployment_observation_is_rejected() -> None:
    deps_a = dependency_snapshot(
        SKILL_PROFILE,
        observed(deployment_identity="deployment-A", observed_at="2026-10-26T10:00:00Z"),
    )
    fresh_b = observed(deployment_identity="deployment-B", observed_at="2026-10-26T11:59:00Z")
    with pytest.raises(ValueError, match="deployment identity"):
        adjudicate_current(
            AcceptanceVerdict.ACCEPTED,
            deps_a,
            deps_a,
            now=datetime.fromisoformat("2026-10-26T12:00:00+00:00"),
            current_observation=fresh_b,
            max_age_seconds=3600,
        )


def test_f3_unbound_deployment_observation_cannot_substitute_for_bound() -> None:
    deps_a = dependency_snapshot(
        SKILL_PROFILE,
        observed(deployment_identity="deployment-A", observed_at="2026-10-26T10:00:00Z"),
    )
    with pytest.raises(ValueError, match="deployment identity"):
        adjudicate_current(
            AcceptanceVerdict.ACCEPTED,
            deps_a,
            deps_a,
            now=datetime.fromisoformat("2026-10-26T12:00:00+00:00"),
            current_observation=observed(deployment_identity=None, observed_at="2026-10-26T11:59:00Z"),
            max_age_seconds=3600,
        )


def test_f3_cross_deployment_via_stale_semantics() -> None:
    deps_a = dependency_snapshot(
        SKILL_PROFILE,
        observed(deployment_identity="deployment-A", observed_at="2026-10-26T10:00:00Z"),
    )
    current_b = dependencies(deployment_identity="deployment-B")
    assert derive_currentness(deps_a, current_b) is AcceptanceCurrentness.STALE


def test_f3_unbound_profile_tolerates_absent_deployment_in_binding() -> None:
    unbound = AcceptanceProfile(
        profile_id="unbound",
        profile_revision="prof-unbound-v1",
        policy_revision="policy-v1",
        required_identity_fields=("artifact_digest",),
        required_proof_kinds=("installed_files",),
        minimum_authority={"installed_files": EvidenceAuthority.INDEPENDENT_OBSERVER},
        require_target_binding=False,
    )
    deps = dependency_snapshot(unbound, observed(deployment_identity=None))
    adjudicate_current(
        AcceptanceVerdict.ACCEPTED,
        deps,
        deps,
        now=datetime.fromisoformat("2026-10-26T12:00:00+00:00"),
        current_observation=observed(deployment_identity=None),
        max_age_seconds=3600,
    )


def test_generation_binding_applies_only_to_proven_proofs() -> None:
    proofs = [
        proof("installed_files"),
        proof("deterministic_helper_test", status=ProofStatus.UNKNOWN, runtime_generation=None),
    ]
    decision = evaluate_acceptance(SKILL_PROFILE, expected(), observed(), proofs)
    assert decision.verdict is AcceptanceVerdict.INCONCLUSIVE
    assert "required-proof-deterministic_helper_test-unknown" in decision.reason_codes
    assert not any("generation-unbound" in reason for reason in decision.reason_codes)


def test_verify_detects_declared_profile_identity_drift() -> None:
    document = composed_document()
    profile_block = document["acceptance_profile"]
    assert isinstance(profile_block, dict)
    profile_block["id"] = "imitation-profile"
    document["payload_digest"] = payload_digest(document)
    findings = verify_receipt(document, schema_path=SCHEMA_PATH, profile=SKILL_PROFILE)
    assert any("acceptance_profile identity mismatch" in finding for finding in findings)


def test_receipt_serializes_observation_provenance_refs() -> None:
    document = compose_receipt(
        acceptance_id="acceptance-provenance-1",
        profile=SKILL_PROFILE,
        target_environment_class="workstation",
        target_deployment_identity="deployment-fedora-1",
        target_identity="host:fedora",
        expected=expected(),
        observed=observed(provenance_refs=("obs:a", "obs:b")),
        proofs=skill_proofs(),
        evidence_refs=["evidence:1", "evidence:2"],
    )
    observed_block = document["observed"]
    assert isinstance(observed_block, dict)
    assert observed_block["provenance_refs"] == ["obs:a", "obs:b"]
    assert verify_receipt(document, schema_path=SCHEMA_PATH) == []


def test_reason_overflow_is_a_composition_error() -> None:
    proofs = [proof(f"kind_{index}", status=ProofStatus.UNKNOWN) for index in range(64)]
    profile = AcceptanceProfile(
        profile_id="overflow-profile",
        profile_revision="prof-overflow-v1",
        policy_revision="policy-v1",
        required_identity_fields=("artifact_digest",),
        required_proof_kinds=tuple(f"kind_{index}" for index in range(64)),
    )
    with pytest.raises(ValueError, match="reason codes"):
        compose_receipt(
            acceptance_id="acceptance-overflow",
            profile=profile,
            target_environment_class="workstation",
            target_deployment_identity="deployment-fedora-1",
            target_identity=None,
            expected=expected(),
            observed=observed(artifact_digest=None),
            proofs=proofs,
            evidence_refs=["evidence:1"],
        )


def test_evidence_set_digest_is_bounded_and_typed() -> None:
    with pytest.raises(ValueError, match="at most 64"):
        evidence_set_digest([f"evidence:{index}" for index in range(65)])
    with pytest.raises(ValueError, match="non-empty string"):
        evidence_set_digest(cast("list[str]", [None]))

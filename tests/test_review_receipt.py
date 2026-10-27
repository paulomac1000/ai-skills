"""ReviewReceipt v1 contract: exact candidate, independence, freshness, input coverage (#93).

Every negative family proves fail-closed behavior through the public
entrypoints (``compose_receipt``, ``evaluate_review``, ``verify_receipt``,
``review_admission``); positive controls prove the same entrypoints admit a
complete, terminal, independent, exact-candidate review.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from contracts import review_receipt as rr

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "contracts" / "review-receipt.schema.json"

C1 = "a" * 40
C2 = "f" * 40
BASE = "b" * 40
RUBRIC = "sha256:" + "d" * 64
PLAN = "sha256:" + "e" * 64
MANIFEST = "sha256:" + "c" * 64
NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
REVIEWED_AT = "2026-10-27T10:06:00Z"


def baseline_subject(candidate: str = C1) -> rr.ReviewSubject:
    return rr.ReviewSubject(
        repository="paulomac1000/ai-skills",
        candidate_sha=candidate,
        base_sha=BASE,
        input_manifest_digest=MANIFEST,
    )


def baseline_producer() -> rr.ReviewProducer:
    return rr.ReviewProducer(
        reviewer_kind=rr.ReviewerKind.MODEL,
        reviewer_identity="chatgpt-pr-validation",
        provider="chatgpt-mcp",
        model_or_engine="gpt-5",
        configuration_revision="adapter/9",
    )


def baseline_independence() -> rr.IndependenceDeclaration:
    return rr.IndependenceDeclaration(
        declared_class=rr.IndependenceClass.INDEPENDENT,
        attestation=rr.IndependenceAttestation(
            authority=rr.AttestationAuthority.ORCHESTRATOR_ATTESTED,
            evidence_ref="dispatch:op-1",
        ),
    )


def baseline_policy_binding() -> rr.ReviewPolicyBinding:
    return rr.ReviewPolicyBinding(
        policy_revision="review-policy/7",
        rubric_id="backend-change-review",
        rubric_revision="7",
        rubric_digest=RUBRIC,
        plan_ref="contracts/semantic-review-plan.yaml",
        plan_digest=PLAN,
    )


def baseline_criteria() -> list[rr.CriterionOutcome]:
    return [
        rr.CriterionOutcome(id="correctness.behavior", required=True, verdict=rr.CriterionVerdict.PASS),
        rr.CriterionOutcome(id="compat.public_contract", required=True, verdict=rr.CriterionVerdict.PASS),
        rr.CriterionOutcome(id="scope.no_unrelated_mutation", required=True, verdict=rr.CriterionVerdict.PASS),
    ]


def baseline_coverage(candidate: str = C1) -> rr.ReviewCoverage:
    return rr.ReviewCoverage(
        access_mode=rr.AccessMode.EXACT_BUNDLE,
        reviewed_through_sha=candidate,
        changed_files=("contracts/review_receipt.py", "tests/test_review_receipt.py"),
        changed_surface_digest="sha256:" + "1" * 64,
        required_context_complete=rr.CoverageState.COMPLETE,
        evidence_selection_authority="parent",
    )


def baseline_operation() -> rr.ProviderOperation:
    return rr.ProviderOperation(
        state=rr.ProviderState.COMPLETED_WITH_REVIEW,
        operation_ref="provider-job-123",
        submitted_at="2026-10-27T10:00:00Z",
        completed_at="2026-10-27T10:05:00Z",
        observation_coverage=rr.CoverageState.COMPLETE,
    )


def baseline_ledger() -> rr.FindingLedger:
    return rr.FindingLedger(items=())


def compose_baseline(
    candidate: str = C1,
    *,
    generation: int = 2,
    issued: rr.ReviewVerdict = rr.ReviewVerdict.APPROVE,
) -> dict[str, object]:
    return rr.compose_receipt(
        review_id="review-93",
        review_generation=generation,
        subject=baseline_subject(candidate),
        producer=baseline_producer(),
        independence=baseline_independence(),
        policy_binding=baseline_policy_binding(),
        criteria=baseline_criteria(),
        coverage=baseline_coverage(candidate),
        provider_operation=baseline_operation(),
        findings=baseline_ledger(),
        issued_verdict=issued,
        evidence_refs=("diff:bundle-1",),
        reviewed_at=REVIEWED_AT,
    )


def baseline_policy(**overrides: object) -> rr.ReviewPolicy:
    values: dict[str, object] = {
        "policy_id": "exact-head-independent-review",
        "policy_revision": "review-policy/7",
        "required_criteria": (
            "correctness.behavior",
            "compat.public_contract",
            "scope.no_unrelated_mutation",
        ),
        "required_changed_files": ("contracts/review_receipt.py",),
        "require_independence": True,
        "minimum_independence_authority": rr.AttestationAuthority.ORCHESTRATOR_ATTESTED,
        "require_full_input": True,
        "require_terminal_operation": True,
        "require_review_content": True,
        "require_resolved_findings": True,
        "require_plan_binding": True,
        "expected_rubric_digest": RUBRIC,
        "expected_plan_digest": PLAN,
    }
    values.update(overrides)
    return rr.ReviewPolicy(**values)  # type: ignore[arg-type]


def baseline_current(
    candidate: str = C1,
    *,
    policy_revision: str = "review-policy/7",
    rubric: str | None = RUBRIC,
    plan: str | None = PLAN,
    manifest: str | None = MANIFEST,
    base: str | None = BASE,
    repository: str = "paulomac1000/ai-skills",
) -> rr.ReviewDependencies:
    return rr.ReviewDependencies(
        repository=repository,
        candidate_sha=candidate,
        policy_revision=policy_revision,
        rubric_digest=rubric,
        plan_digest=plan,
        input_manifest_digest=manifest,
        base_sha=base,
    )


def admit(
    document: dict[str, object],
    policy: rr.ReviewPolicy | None = None,
    current: rr.ReviewDependencies | None = None,
):
    return rr.review_admission(
        document,
        policy=policy or baseline_policy(),
        current_dependencies=current or baseline_current(),
        now=NOW,
        schema_path=SCHEMA_PATH,
    )


# ---------------------------------------------------------------------------
# Positive controls
# ---------------------------------------------------------------------------


def test_full_terminal_independent_review_is_green() -> None:
    decision = admit(compose_baseline())
    assert decision.outcome is rr.AdmissionOutcome.GREEN
    assert decision.gate_verdict is rr.ReviewVerdict.APPROVE
    assert decision.currentness is rr.Currentness.CURRENT


def test_structural_verify_is_clean_for_baseline() -> None:
    document = compose_baseline()
    assert rr.verify_receipt(document, schema_path=SCHEMA_PATH) == []
    assert rr.verify_receipt(document, schema_path=None) == []


@pytest.mark.parametrize("kind", [rr.ReviewerKind.HUMAN, rr.ReviewerKind.BOT, rr.ReviewerKind.SERVICE])
def test_each_reviewer_kind_is_admissible_with_independence(kind: rr.ReviewerKind) -> None:
    document = rr.compose_receipt(
        review_id="review-kind",
        review_generation=1,
        subject=baseline_subject(),
        producer=rr.ReviewProducer(reviewer_kind=kind, reviewer_identity="independent-reviewer-1"),
        independence=baseline_independence(),
        policy_binding=baseline_policy_binding(),
        criteria=baseline_criteria(),
        coverage=baseline_coverage(),
        provider_operation=baseline_operation(),
        findings=baseline_ledger(),
        issued_verdict=rr.ReviewVerdict.APPROVE,
        evidence_refs=("diff:bundle-1",),
        reviewed_at=REVIEWED_AT,
    )
    assert admit(document).outcome is rr.AdmissionOutcome.GREEN


def test_required_not_applicable_is_admissible_only_with_policy_consent() -> None:
    criteria = baseline_criteria()
    criteria[2] = rr.CriterionOutcome(
        id="scope.no_unrelated_mutation",
        required=True,
        verdict=rr.CriterionVerdict.NOT_APPLICABLE,
        applicability_basis="docs-only change: no code paths mutated",
    )
    document = rr.compose_receipt(
        review_id="review-na",
        review_generation=1,
        subject=baseline_subject(),
        producer=baseline_producer(),
        independence=baseline_independence(),
        policy_binding=baseline_policy_binding(),
        criteria=criteria,
        coverage=baseline_coverage(),
        provider_operation=baseline_operation(),
        findings=baseline_ledger(),
        issued_verdict=rr.ReviewVerdict.APPROVE,
        evidence_refs=("diff:bundle-1",),
        reviewed_at=REVIEWED_AT,
    )
    refused = admit(document)
    assert refused.outcome is rr.AdmissionOutcome.NON_GREEN
    assert "required-criterion-scope.no_unrelated_mutation-not-applicable-disallowed" in refused.reason_codes
    allowed = admit(document, policy=baseline_policy(allow_required_not_applicable=True))
    assert allowed.outcome is rr.AdmissionOutcome.GREEN


def test_historical_c1_receipt_stays_queryable_after_c2() -> None:
    document = compose_baseline()
    assert rr.verify_receipt(document, schema_path=SCHEMA_PATH) == []
    decision = admit(document, current=baseline_current(candidate=C2))
    assert decision.outcome is rr.AdmissionOutcome.NOT_CURRENT
    assert decision.reason_codes == ("subject-not-current",)


# ---------------------------------------------------------------------------
# Family A: identity/currentness
# ---------------------------------------------------------------------------


def test_review_of_c1_does_not_approve_c2() -> None:
    decision = admit(compose_baseline(candidate=C1), current=baseline_current(candidate=C2))
    assert decision.outcome is rr.AdmissionOutcome.NOT_CURRENT
    assert decision.currentness is rr.Currentness.STALE


def test_equal_tree_with_different_sha_is_stale() -> None:
    document = compose_baseline(candidate=C1)
    same_tree_other_sha = rr.ReviewDependencies(
        repository="paulomac1000/ai-skills",
        candidate_sha=C2,
        policy_revision="review-policy/7",
        rubric_digest=RUBRIC,
        plan_digest=PLAN,
        input_manifest_digest=MANIFEST,
        base_sha=BASE,
    )
    assert rr.derive_currentness(baseline_current(candidate=C1), same_tree_other_sha) is rr.Currentness.STALE
    assert admit(document, current=same_tree_other_sha).outcome is rr.AdmissionOutcome.NOT_CURRENT


def test_other_repository_is_stale() -> None:
    current = baseline_current(repository="paulomac1000/other-repo")
    decision = admit(compose_baseline(), current=current)
    assert decision.outcome is rr.AdmissionOutcome.NOT_CURRENT


def test_base_revision_drift_is_stale() -> None:
    current = baseline_current(base="9" * 40)
    decision = admit(compose_baseline(), current=current)
    assert decision.outcome is rr.AdmissionOutcome.NOT_CURRENT


def test_changed_policy_revision_is_stale() -> None:
    current = baseline_current(policy_revision="review-policy/8")
    decision = admit(compose_baseline(), current=current)
    assert decision.outcome is rr.AdmissionOutcome.NOT_CURRENT


def test_changed_rubric_digest_is_stale() -> None:
    current = baseline_current(rubric="sha256:" + "8" * 64)
    decision = admit(compose_baseline(), current=current)
    assert decision.outcome is rr.AdmissionOutcome.NOT_CURRENT


def test_changed_plan_digest_is_stale() -> None:
    current = baseline_current(plan="sha256:" + "7" * 64)
    decision = admit(compose_baseline(), current=current)
    assert decision.outcome is rr.AdmissionOutcome.NOT_CURRENT


def test_older_generation_returning_after_newer_is_not_current() -> None:
    document = compose_baseline(generation=1)
    assert rr.verify_receipt(document, schema_path=SCHEMA_PATH) == []
    decision = admit(document, current=baseline_current(candidate=C2))
    assert decision.outcome is rr.AdmissionOutcome.NOT_CURRENT


def test_unknown_current_value_is_not_proven_not_current() -> None:
    current = baseline_current(manifest=None)
    decision = admit(compose_baseline(), current=current)
    assert decision.outcome is rr.AdmissionOutcome.NOT_PROVEN
    assert "subject-currentness-unknown" in decision.reason_codes


def test_known_change_masks_sibling_unknown() -> None:
    current = rr.ReviewDependencies(
        repository="paulomac1000/ai-skills",
        candidate_sha=C1,
        policy_revision="review-policy/8",
        rubric_digest=None,
        plan_digest=PLAN,
        input_manifest_digest=MANIFEST,
        base_sha=BASE,
    )
    assert rr.derive_currentness(baseline_current(), current) is rr.Currentness.STALE


# ---------------------------------------------------------------------------
# Family B: input coverage
# ---------------------------------------------------------------------------


def test_missing_required_changed_file_is_not_green() -> None:
    document = compose_baseline()
    document["coverage"]["changed_files"] = ["tests/test_review_receipt.py"]
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert "coverage-changed-file-missing:contracts/review_receipt.py" in decision.reason_codes


def test_input_manifest_drift_is_not_current() -> None:
    current = baseline_current(manifest="sha256:" + "2" * 64)
    decision = admit(compose_baseline(), current=current)
    assert decision.outcome is rr.AdmissionOutcome.NOT_CURRENT


def test_summary_only_input_cannot_satisfy_full_review() -> None:
    document = compose_baseline()
    document["coverage"]["access_mode"] = "summary_only"
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert "coverage-access-mode-summary_only" in decision.reason_codes


def test_truncated_provider_observation_is_not_green() -> None:
    document = compose_baseline()
    document["provider_operation"]["observation_coverage"] = "partial"
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert "provider-observation-coverage-partial" in decision.reason_codes


def test_omitted_area_with_complete_claim_is_a_finding() -> None:
    document = compose_baseline()
    document["coverage"]["omitted_areas"] = ["skills/qa-change-verifier/tools/"]
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert any("omitted areas" in reason for reason in decision.reason_codes)


def test_incomplete_private_repository_context_is_not_green() -> None:
    document = compose_baseline()
    document["coverage"]["required_context_complete"] = "partial"
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert "coverage-context-partial" in decision.reason_codes


def test_unknown_access_mode_is_not_green() -> None:
    document = compose_baseline()
    document["coverage"]["access_mode"] = "unknown"
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert "coverage-access-mode-unknown" in decision.reason_codes


def test_implementer_selected_evidence_is_not_green() -> None:
    document = compose_baseline()
    document["coverage"]["evidence_selection_authority"] = "implementer"
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert "coverage-selection-authority-implementer" in decision.reason_codes


# ---------------------------------------------------------------------------
# Family C: findings and rubric
# ---------------------------------------------------------------------------


def test_required_unknown_criterion_is_not_green() -> None:
    document = compose_baseline()
    document["criteria"][0]["verdict"] = "unknown"
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert "required-criterion-correctness.behavior-unknown" in decision.reason_codes


def test_missing_required_criterion_is_not_green() -> None:
    document = compose_baseline()
    document["criteria"] = document["criteria"][:2]
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert "required-criterion-scope.no_unrelated_mutation-missing" in decision.reason_codes


def test_required_fail_with_issued_approve_is_blocked() -> None:
    document = compose_baseline()
    document["criteria"][0]["verdict"] = "fail"
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert decision.gate_verdict is rr.ReviewVerdict.BLOCKED
    assert "required-criterion-correctness.behavior-failed" in decision.reason_codes
    assert any("issued approve with failing required criteria" in reason for reason in decision.reason_codes)


def test_not_applicable_without_basis_is_refused() -> None:
    with pytest.raises(ValueError, match="applicability basis"):
        rr.CriterionOutcome(id="c1", required=True, verdict=rr.CriterionVerdict.NOT_APPLICABLE)
    document = compose_baseline()
    document["criteria"][0]["verdict"] = "not_applicable"
    document["criteria"][0]["applicability_basis"] = None
    document["payload_digest"] = rr.payload_digest(document)
    findings = rr.verify_receipt(document, schema_path=SCHEMA_PATH)
    assert findings


def test_scalar_confidence_cannot_rescue_missing_criteria() -> None:
    document = compose_baseline()
    document["criteria"] = []
    document["confidence"] = 1.0
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert any("-missing" in reason for reason in decision.reason_codes)


def test_ui_resolved_finding_without_resolution_evidence_is_refused() -> None:
    with pytest.raises(ValueError, match="resolved_by_revision"):
        rr.FindingRecord(
            finding_id="F1",
            severity=rr.FindingSeverity.BLOCKER,
            state=rr.FindingState.RESOLVED_BY_CANDIDATE,
            generation=2,
        )


def test_finding_resolved_by_foreign_revision_is_a_finding() -> None:
    document = compose_baseline()
    document["findings"]["items"].append(
        {
            "finding_id": "F1",
            "severity": "blocker",
            "state": "resolved_by_candidate",
            "generation": 2,
            "resolved_by_revision": C2,
        }
    )
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert "finding-F1-resolved-by-foreign-revision" in decision.reason_codes
    assert any("does not bind the reviewed candidate" in reason for reason in decision.reason_codes)


def test_finding_after_generation_watermark_is_a_finding() -> None:
    document = compose_baseline(generation=1)
    document["findings"]["items"].append(
        {
            "finding_id": "F2",
            "severity": "major",
            "state": "open",
            "generation": 2,
        }
    )
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert any("exceeds receipt generation" in reason for reason in decision.reason_codes)


def test_open_blocker_prevents_approval() -> None:
    document = rr.compose_receipt(
        review_id="review-blocker",
        review_generation=2,
        subject=baseline_subject(),
        producer=baseline_producer(),
        independence=baseline_independence(),
        policy_binding=baseline_policy_binding(),
        criteria=baseline_criteria(),
        coverage=baseline_coverage(),
        provider_operation=baseline_operation(),
        findings=rr.FindingLedger(
            items=(
                rr.FindingRecord(
                    finding_id="F1",
                    severity=rr.FindingSeverity.BLOCKER,
                    state=rr.FindingState.OPEN,
                    generation=2,
                ),
            )
        ),
        issued_verdict=rr.ReviewVerdict.NEEDS_FIXES,
        evidence_refs=("diff:bundle-1",),
        reviewed_at=REVIEWED_AT,
    )
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert decision.gate_verdict is rr.ReviewVerdict.NEEDS_FIXES
    assert "blocking-finding-open:F1" in decision.reason_codes
    with pytest.raises(ValueError, match="contradicts"):
        rr.compose_receipt(
            review_id="review-blocker",
            review_generation=2,
            subject=baseline_subject(),
            producer=baseline_producer(),
            independence=baseline_independence(),
            policy_binding=baseline_policy_binding(),
            criteria=baseline_criteria(),
            coverage=baseline_coverage(),
            provider_operation=baseline_operation(),
            findings=rr.FindingLedger(
                items=(
                    rr.FindingRecord(
                        finding_id="F1",
                        severity=rr.FindingSeverity.BLOCKER,
                        state=rr.FindingState.OPEN,
                        generation=2,
                    ),
                )
            ),
            issued_verdict=rr.ReviewVerdict.APPROVE,
            evidence_refs=("diff:bundle-1",),
            reviewed_at=REVIEWED_AT,
        )


def test_implementer_waiver_is_refused() -> None:
    with pytest.raises(ValueError, match="implementer"):
        rr.FindingRecord(
            finding_id="F1",
            severity=rr.FindingSeverity.BLOCKER,
            state=rr.FindingState.WAIVED_BY_AUTHORITY,
            generation=2,
            waiver_ref="chat://self",
            waiver_authority="implementer",
        )
    document = compose_baseline()
    document["findings"]["items"].append(
        {
            "finding_id": "F1",
            "severity": "blocker",
            "state": "waived_by_authority",
            "generation": 2,
            "waiver_ref": "chat://self",
            "waiver_authority": "implementer",
        }
    )
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert any("waiver_authority" in reason for reason in decision.reason_codes)
    structural = rr.verify_receipt(document, schema_path=None)
    assert any("malformed receipt shape" in reason for reason in structural)


def test_policy_waiver_is_admissible() -> None:
    document = rr.compose_receipt(
        review_id="review-waiver",
        review_generation=2,
        subject=baseline_subject(),
        producer=baseline_producer(),
        independence=baseline_independence(),
        policy_binding=baseline_policy_binding(),
        criteria=baseline_criteria(),
        coverage=baseline_coverage(),
        provider_operation=baseline_operation(),
        findings=rr.FindingLedger(
            items=(
                rr.FindingRecord(
                    finding_id="F1",
                    severity=rr.FindingSeverity.MINOR,
                    state=rr.FindingState.WAIVED_BY_AUTHORITY,
                    generation=2,
                    waiver_ref="policy-waiver:42",
                    waiver_authority="policy",
                ),
            )
        ),
        issued_verdict=rr.ReviewVerdict.APPROVE,
        evidence_refs=("diff:bundle-1",),
        reviewed_at=REVIEWED_AT,
    )
    assert admit(document).outcome is rr.AdmissionOutcome.GREEN


def test_issued_verdict_cannot_raise_the_derived_gate() -> None:
    document = compose_baseline(issued=rr.ReviewVerdict.NEEDS_FIXES)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert decision.gate_verdict is rr.ReviewVerdict.NEEDS_FIXES
    assert "issued-verdict-needs_fixes" in decision.reason_codes


# ---------------------------------------------------------------------------
# Family D: independence and authority
# ---------------------------------------------------------------------------


def test_same_implementer_reviewer_is_not_green() -> None:
    document = compose_baseline()
    document["independence"]["declared_class"] = "same_implementer"
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert "independence-class-same_implementer" in decision.reason_codes


def test_unknown_reviewer_provenance_is_not_green() -> None:
    document = rr.compose_receipt(
        review_id="review-unknown",
        review_generation=1,
        subject=baseline_subject(),
        producer=rr.ReviewProducer(reviewer_kind=rr.ReviewerKind.SERVICE, reviewer_identity="unknown"),
        independence=rr.IndependenceDeclaration(
            declared_class=rr.IndependenceClass.UNKNOWN,
            attestation=rr.IndependenceAttestation(authority=rr.AttestationAuthority.NONE),
        ),
        policy_binding=baseline_policy_binding(),
        criteria=baseline_criteria(),
        coverage=baseline_coverage(),
        provider_operation=baseline_operation(),
        findings=baseline_ledger(),
        issued_verdict=rr.ReviewVerdict.APPROVE,
        evidence_refs=("diff:bundle-1",),
        reviewed_at=REVIEWED_AT,
    )
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert "independence-class-unknown" in decision.reason_codes


def test_different_model_with_implementer_controlled_authority_is_not_green() -> None:
    document = compose_baseline()
    document["independence"]["attestation"]["authority"] = "orchestrator_attested"
    document["payload_digest"] = rr.payload_digest(document)
    policy = baseline_policy(minimum_independence_authority=rr.AttestationAuthority.INDEPENDENT_AUTHORITY)
    decision = admit(document, policy=policy)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert any(
        reason.startswith("independence-attestation-insufficient:orchestrator_attested")
        for reason in decision.reason_codes
    )


def test_caller_declared_independence_without_attestation_is_not_green() -> None:
    document = compose_baseline()
    document["independence"]["attestation"]["authority"] = "self_declared"
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert any(
        reason.startswith("independence-attestation-insufficient:self_declared") for reason in decision.reason_codes
    )


def test_attestation_without_evidence_is_not_green() -> None:
    document = compose_baseline()
    document["independence"]["attestation"]["evidence_ref"] = None
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert "independence-attestation-evidence-missing" in decision.reason_codes


def test_review_cannot_replace_required_deterministic_criterion() -> None:
    criteria = baseline_criteria()
    criteria[0] = rr.CriterionOutcome(
        id="correctness.behavior",
        required=True,
        verdict=rr.CriterionVerdict.NOT_APPLICABLE,
        applicability_basis="deterministic gate covers behavior",
    )
    document = rr.compose_receipt(
        review_id="review-na-deterministic",
        review_generation=1,
        subject=baseline_subject(),
        producer=baseline_producer(),
        independence=baseline_independence(),
        policy_binding=baseline_policy_binding(),
        criteria=criteria,
        coverage=baseline_coverage(),
        provider_operation=baseline_operation(),
        findings=baseline_ledger(),
        issued_verdict=rr.ReviewVerdict.APPROVE,
        evidence_refs=("diff:bundle-1",),
        reviewed_at=REVIEWED_AT,
    )
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert "required-criterion-correctness.behavior-not-applicable-disallowed" in decision.reason_codes


def test_provider_completion_without_review_content_is_not_green() -> None:
    document = compose_baseline()
    document["provider_operation"]["state"] = "completed_no_findings"
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert any("completed_no_findings" in reason for reason in decision.reason_codes)


def test_digest_consistent_forged_approval_is_detected() -> None:
    document = compose_baseline()
    document["independence"]["attestation"]["authority"] = "self_declared"
    document["payload_digest"] = rr.payload_digest(document)
    policy = baseline_policy()
    decision = admit(document, policy=policy)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert any("verdict mismatch" in reason for reason in decision.reason_codes)
    assert any(reason.startswith("independence-attestation-insufficient") for reason in decision.reason_codes)


# ---------------------------------------------------------------------------
# Family E: async lifecycle and recovery
# ---------------------------------------------------------------------------


def test_ack_unknown_is_represented_and_non_green() -> None:
    document = compose_baseline()
    document["provider_operation"]["state"] = "ack_unknown"
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert "provider-operation-ack_unknown-non-terminal" in decision.reason_codes
    assert any("ack_unknown provider state is a contradiction" in reason for reason in decision.reason_codes)


def test_provider_result_unavailable_is_not_green() -> None:
    document = compose_baseline()
    document["provider_operation"]["observation_coverage"] = "unknown"
    document["coverage"]["required_context_complete"] = "unknown"
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert "provider-observation-coverage-unknown" in decision.reason_codes
    assert "coverage-context-unknown" in decision.reason_codes


def test_durable_operation_ref_is_preserved_across_generations() -> None:
    first = rr.compose_receipt(
        review_id="review-op-1",
        review_generation=1,
        subject=baseline_subject(),
        producer=baseline_producer(),
        independence=baseline_independence(),
        policy_binding=baseline_policy_binding(),
        criteria=baseline_criteria(),
        coverage=baseline_coverage(),
        provider_operation=rr.ProviderOperation(
            state=rr.ProviderState.COMPLETED_WITH_REVIEW,
            operation_ref="provider-job-100",
            completed_at="2026-10-27T09:00:00Z",
            observation_coverage=rr.CoverageState.COMPLETE,
        ),
        findings=baseline_ledger(),
        issued_verdict=rr.ReviewVerdict.NEEDS_FIXES,
        evidence_refs=("diff:bundle-0",),
        reviewed_at="2026-10-27T09:01:00Z",
    )
    second = compose_baseline()
    assert first["provider_operation"]["operation_ref"] == "provider-job-100"
    assert second["provider_operation"]["operation_ref"] == "provider-job-123"
    assert first["payload_digest"] != second["payload_digest"]


def test_cancelled_provider_operation_is_blocked() -> None:
    document = compose_baseline()
    document["provider_operation"]["state"] = "cancelled"
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert decision.gate_verdict is rr.ReviewVerdict.BLOCKED
    assert "provider-operation-cancelled" in decision.reason_codes


def test_duplicate_callback_converges_to_one_receipt() -> None:
    document = compose_baseline()
    assert rr.verify_receipt(document, schema_path=SCHEMA_PATH) == rr.verify_receipt(document, schema_path=SCHEMA_PATH)
    assert rr.payload_digest(document) == rr.payload_digest(compose_baseline())


def test_partial_then_terminal_complete_result() -> None:
    partial = compose_baseline()
    partial["coverage"]["required_context_complete"] = "partial"
    partial["payload_digest"] = rr.payload_digest(partial)
    assert admit(partial).outcome is rr.AdmissionOutcome.NON_GREEN
    assert admit(compose_baseline()).outcome is rr.AdmissionOutcome.GREEN


def test_expired_receipt_is_not_current() -> None:
    document = compose_baseline()
    document["expires_at"] = "2026-10-27T11:00:00Z"
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NOT_CURRENT
    assert "receipt-expired" in decision.reason_codes


def test_future_receipt_is_green_before_expiry() -> None:
    document = compose_baseline()
    document["expires_at"] = "2026-10-28T11:00:00Z"
    document["payload_digest"] = rr.payload_digest(document)
    assert admit(document).outcome is rr.AdmissionOutcome.GREEN


# ---------------------------------------------------------------------------
# Family F: data safety
# ---------------------------------------------------------------------------


def test_unknown_extra_field_is_rejected_by_schema() -> None:
    document = compose_baseline()
    document["forged"] = "field"
    document["payload_digest"] = rr.payload_digest(document)
    findings = rr.verify_receipt(document, schema_path=SCHEMA_PATH)
    assert findings


def test_boolean_schema_version_is_rejected() -> None:
    document = compose_baseline()
    document["schema_version"] = True
    document["payload_digest"] = rr.payload_digest(document)
    assert rr.verify_receipt(document, schema_path=SCHEMA_PATH)
    structural = rr.verify_receipt(document, schema_path=None)
    assert "unsupported receipt schema version" in structural


def test_duplicate_criterion_and_finding_ids_are_findings() -> None:
    document = compose_baseline()
    document["criteria"].append(copy.deepcopy(document["criteria"][0]))
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert any("duplicate criterion ids" in reason for reason in decision.reason_codes)
    document = compose_baseline()
    document["findings"]["items"] = [
        {"finding_id": "F1", "severity": "minor", "state": "open", "generation": 2},
        {"finding_id": "F1", "severity": "minor", "state": "open", "generation": 2},
    ]
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert any("malformed receipt shape" in reason for reason in decision.reason_codes)
    with pytest.raises(ValueError, match="duplicate finding id"):
        rr.FindingLedger(
            items=(
                rr.FindingRecord(
                    finding_id="F1", severity=rr.FindingSeverity.MINOR, state=rr.FindingState.OPEN, generation=2
                ),
                rr.FindingRecord(
                    finding_id="F1", severity=rr.FindingSeverity.MINOR, state=rr.FindingState.OPEN, generation=2
                ),
            )
        )


def test_criterion_referencing_unknown_finding_is_a_finding() -> None:
    document = compose_baseline()
    document["criteria"][0]["finding_refs"] = ["does-not-exist"]
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert any("references unknown findings" in reason for reason in decision.reason_codes)


def test_invalid_digest_fails_closed_without_exception() -> None:
    document = compose_baseline()
    document["subject"]["input_manifest_digest"] = "sha256:nothex"
    document["payload_digest"] = rr.payload_digest(document)
    findings = rr.verify_receipt(document, schema_path=SCHEMA_PATH)
    assert findings
    structural = rr.verify_receipt(document, schema_path=None)
    assert any("malformed receipt shape" in reason for reason in structural)


def test_overlong_payload_fails_closed() -> None:
    document = compose_baseline()
    document["producer"]["reviewer_identity"] = "x" * 300
    document["payload_digest"] = rr.payload_digest(document)
    assert rr.verify_receipt(document, schema_path=SCHEMA_PATH)
    structural = rr.verify_receipt(document, schema_path=None)
    assert any("malformed receipt shape" in reason for reason in structural)


def test_untrusted_rubric_tampering_with_consistent_digest_is_detected() -> None:
    document = compose_baseline()
    document["policy"]["rubric_digest"] = "sha256:" + "0" * 64
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert any("rubric digest mismatch" in reason for reason in decision.reason_codes)
    assert "rubric-digest-mismatch" in decision.reason_codes


def test_payload_digest_tampering_is_detected() -> None:
    document = compose_baseline()
    document["verdict"] = "approve"
    document["payload_digest"] = "sha256:" + "0" * 64
    findings = rr.verify_receipt(document, schema_path=SCHEMA_PATH)
    assert any("payload_digest mismatch" in reason for reason in findings)


def test_reviewed_through_sha_mismatch_is_a_finding() -> None:
    document = compose_baseline()
    document["coverage"]["reviewed_through_sha"] = C2
    document["payload_digest"] = rr.payload_digest(document)
    decision = admit(document)
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN
    assert any("does not cover the reviewed candidate" in reason for reason in decision.reason_codes)


# ---------------------------------------------------------------------------
# Identity axes (#97 lesson: F1/F2/F3-style independent axes)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("axis", "overrides"),
    [
        ("candidate_sha", {"candidate_sha": C2}),
        ("policy_revision", {"policy_revision": "review-policy/8"}),
        ("rubric_digest", {"rubric_digest": "sha256:" + "8" * 64}),
        ("plan_digest", {"plan_digest": "sha256:" + "8" * 64}),
        ("input_manifest_digest", {"input_manifest_digest": "sha256:" + "8" * 64}),
        ("base_sha", {"base_sha": "8" * 40}),
        ("repository", {"repository": "paulomac1000/other"}),
    ],
)
def test_each_identity_axis_independently_invalidates_currentness(axis: str, overrides: dict[str, str]) -> None:
    baseline = baseline_current()
    fields = {
        "repository": baseline.repository,
        "candidate_sha": baseline.candidate_sha,
        "policy_revision": baseline.policy_revision,
        "rubric_digest": baseline.rubric_digest,
        "plan_digest": baseline.plan_digest,
        "input_manifest_digest": baseline.input_manifest_digest,
        "base_sha": baseline.base_sha,
    }
    fields.update(overrides)
    mutated = rr.ReviewDependencies(**fields)
    assert rr.derive_currentness(baseline, mutated) is rr.Currentness.STALE, axis
    document = compose_baseline()
    assert admit(document, current=mutated).outcome is rr.AdmissionOutcome.NOT_CURRENT, axis


# ---------------------------------------------------------------------------
# Composition and re-derivation parity
# ---------------------------------------------------------------------------


def test_composition_self_check_refuses_schema_violations() -> None:
    with pytest.raises(ValueError):
        rr.compose_receipt(
            review_id="review-bad",
            review_generation=0,
            subject=baseline_subject(),
            producer=baseline_producer(),
            independence=baseline_independence(),
            policy_binding=baseline_policy_binding(),
            criteria=baseline_criteria(),
            coverage=baseline_coverage(),
            provider_operation=baseline_operation(),
            findings=baseline_ledger(),
            issued_verdict=rr.ReviewVerdict.APPROVE,
            evidence_refs=("diff:bundle-1",),
            reviewed_at=REVIEWED_AT,
        )


def test_structural_verify_with_policy_detects_forged_approval_without_schema() -> None:
    document = compose_baseline()
    document["criteria"][0]["verdict"] = "unknown"
    document["payload_digest"] = rr.payload_digest(document)
    findings = rr.verify_receipt(document, schema_path=None, policy=baseline_policy())
    assert any("verdict mismatch" in reason for reason in findings)
    assert any("required-criterion-correctness.behavior-unknown" in reason for reason in findings)


def test_cli_validates_a_receipt_file(tmp_path: Path) -> None:
    document = compose_baseline()
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps(document), encoding="utf-8")
    assert rr.main([str(receipt)]) == 0
    document["verdict"] = "approve"
    document["payload_digest"] = "sha256:" + "0" * 64
    receipt.write_text(json.dumps(document), encoding="utf-8")
    assert rr.main([str(receipt)]) == 1


def test_non_mapping_root_fails_closed() -> None:
    assert rr.verify_receipt(["not", "a", "receipt"]) == ["receipt root must be an object"]
    decision = rr.review_admission(
        ["not", "a", "receipt"],  # type: ignore[arg-type]
        policy=baseline_policy(),
        current_dependencies=baseline_current(),
        now=NOW,
    )
    assert decision.outcome is rr.AdmissionOutcome.NON_GREEN


def test_admission_requires_timezone_aware_now() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        rr.review_admission(
            compose_baseline(),
            policy=baseline_policy(),
            current_dependencies=baseline_current(),
            now=datetime(2026, 10, 27, 12, 0),
        )

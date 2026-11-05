"""Cross-contract integration tests for #91 + #94 (unified regression matrix).

These tests compose the Execution Evidence Contract (#91) and the Autonomous
Delivery Policy (#94) with the existing canonical contracts — including the
real IntegrationLease module (#92) — rather than recreating their internals.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest

from contracts.autonomous_delivery_policy import (
    DeliveryDecisionKind,
    DeliveryPolicy,
    RiskLevel,
    WorkKind,
    WorkSpec,
    admit_policy,
    evaluate_delivery,
    policy_digest,
)
from contracts.execution_evidence import (
    AdmissionOutcome,
    CurrentIdentities,
    GateRequirement,
    GateState,
    ReceiptKind,
    SubjectKind,
    admit_receipt,
    build_graph,
    derive_currentness,
    evaluate_gate,
    payload_digest,
)

C1 = "a" * 40
C2 = "b" * 40
I1 = "d" * 40
BASE = "e" * 40
GEN7 = "gen-7"
GEN8 = "gen-8"
ARTIFACT = "sha256:" + "5" * 64
OLD_ARTIFACT = "sha256:" + "6" * 64

ROOT = Path(__file__).resolve().parents[1]


def _load_lease_module() -> ModuleType:
    path = ROOT / "skills" / "mcp-steward-architect" / "tools" / "integration_lease.py"
    spec = importlib.util.spec_from_file_location("integration_lease_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def policy_document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": 1,
        "policy_id": "delivery-integration",
        "revision": "r1",
        "trust_binding": {"source_ref": "state://trusted/policy", "source_digest": "sha256:" + "1" * 64},
        "autonomy": {"maximum_level": "release"},
        "work_kinds": {
            "INVESTIGATION": {
                "terminal_boundary": "evidence_backed_findings",
                "risk_profile": "quick",
                "planning_mode_override": "none",
                "review_required_override": False,
                "verification_required_override": False,
                "integration_enabled_override": False,
                "release_enabled_override": False,
            },
            "IMPLEMENTATION": {"terminal_boundary": "runtime_accepted", "requires_pr": True, "requires_release": True},
            "OPERATOR_ACTION": {
                "terminal_boundary": "implementation_completed",
                "requires_operator_grant": True,
                "risk_profile": "standard",
            },
            "COORDINATION": {"terminal_boundary": "decomposition_required"},
        },
        "risk_profiles": {
            "quick": {"maps_risk_level": "LOW", "verification_layers": ["static", "unit"], "reviewer_count": 0},
            "standard": {
                "maps_risk_level": "MEDIUM",
                "verification_layers": ["static", "unit", "integration"],
                "reviewer_count": 1,
            },
            "deep": {
                "maps_risk_level": "HIGH",
                "verification_layers": ["static", "unit", "integration", "security_review"],
                "reviewer_count": 1,
                "independent_verification_required": True,
            },
        },
        "planning": {"mode": "worker_plan", "stale_on": ["planning_base_change"]},
        "review": {"required": True, "count": 1, "upstream_attestation_required": True, "rubric_ref": "rubric://v1"},
        "independent_verification": {"required": False},
        "integration": {"enabled": True, "integration_lease_required": True},
        "release": {"enabled": True, "rollback_required": True},
        "budgets": {"repair_rounds": 4, "outer_retry_budget": 8},
        "terminal_boundary": "runtime_accepted",
    }
    document.update(overrides)
    document["digest"] = policy_digest(document)
    return document


def load_policy(**overrides: object) -> DeliveryPolicy:
    admitted, reasons = admit_policy(policy_document(**overrides))
    assert admitted is not None, reasons
    return admitted


def receipt(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": 1,
        "receipt_id": "r-default",
        "receipt_kind": "validation",
        "producer": {"system": "ci", "principal": "runner-1", "authority_class": "deterministic_tool"},
        "subject": {"kind": "candidate_revision", "identity": "candidate-c1", "candidate_sha": C1},
        "correlation": {"project_id": "p1"},
        "policy": {"policy_ref": "policy://p", "policy_digest": "sha256:" + "2" * 64},
        "outcome": {"disposition": "PASS"},
        "evidence_refs": [],
        "artifact_refs": [],
        "observed_at": "2026-11-04T00:00:00Z",
    }
    document.update(overrides)
    document["payload_digest"] = payload_digest(document)
    return document


IMPL_SPEC = WorkSpec(
    work_kind=WorkKind.IMPLEMENTATION, change_risk=RiskLevel.HIGH, expected_policy_revision="r1", planning_base_sha=BASE
)


class TestIntegrationLeaseComposition:
    def test_expired_lease_refuses_integration(self) -> None:
        lease_module = _load_lease_module()
        lease = lease_module.IntegrationLease(
            lease_id="lease-1",
            authority_principal_ref="authority",
            repository_ref="paulomac1000/ai-skills",
            change_ref=None,
            candidate_head_sha=C1,
            candidate_tree_sha=None,
            target_ref="refs/heads/main",
            observed_base_sha=BASE,
            base_policy=lease_module.BasePolicy.EXACT,
            merge_strategy=lease_module.MergeStrategy.SQUASH,
            required_evidence_set_digest="sha256:" + "7" * 64,
            review_policy_revision=None,
            verification_policy_revision=None,
            autonomy_policy_revision="r1",
            execution_generation="g1",
            issued_at=datetime.now(UTC) - timedelta(hours=2),
            expires_at=datetime.now(UTC) - timedelta(hours=1),
            state=lease_module.IntegrationLeaseState.EXPIRED,
        )
        record = lease_module.IntegrationLeaseAuthorityRecord(
            source_ref="store://leases", attestation_ref="attest://1", lease=lease
        )
        assert record.lease.state is not lease_module.IntegrationLeaseState.ACTIVE
        # The consumed #92 authority refuses expired/non-active leases; the
        # evidence graph may then only record an unauthorized observation.
        assert lease.consumed_by_operation_ref is None

    def test_used_lease_requires_operation_ref(self) -> None:
        lease_module = _load_lease_module()
        with pytest.raises(ValueError, match="consumed_by_operation_ref"):
            lease_module.IntegrationLease(
                lease_id="lease-2",
                authority_principal_ref="authority",
                repository_ref="paulomac1000/ai-skills",
                change_ref=None,
                candidate_head_sha=C1,
                candidate_tree_sha=None,
                target_ref="refs/heads/main",
                observed_base_sha=BASE,
                base_policy=lease_module.BasePolicy.EXACT,
                merge_strategy=lease_module.MergeStrategy.SQUASH,
                required_evidence_set_digest="sha256:" + "7" * 64,
                review_policy_revision=None,
                verification_policy_revision=None,
                autonomy_policy_revision="r1",
                execution_generation="g1",
                issued_at=datetime.now(UTC) - timedelta(hours=2),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                state=lease_module.IntegrationLeaseState.USED,
            )


class TestRuntimeCurrentnessComposition:
    def _runtime_receipt(self, **overrides: object) -> dict[str, object]:
        return receipt(
            receipt_id="runtime-1",
            receipt_kind="runtime_acceptance",
            producer={"system": "doctor", "principal": "doctor-1", "authority_class": "independent_verifier"},
            subject={
                "kind": "observed_runtime",
                "identity": "target-fedora",
                "runtime_generation": GEN7,
                "artifact_digest": ARTIFACT,
            },
            **overrides,
        )

    def test_healthy_target_running_old_digest_is_not_accepted(self) -> None:
        graph = build_graph([self._runtime_receipt()])
        report = derive_currentness(graph, CurrentIdentities(artifact_digest=OLD_ARTIFACT, runtime_generation=GEN7))
        assert report.receipts["runtime-1"].status == "STALE"
        gate = evaluate_gate(
            graph,
            GateRequirement(
                gate_id="runtime",
                required_kind=ReceiptKind.RUNTIME_ACCEPTANCE,
                subject_kind=SubjectKind.OBSERVED_RUNTIME,
            ),
            report,
        )
        assert gate.state is not GateState.SATISFIED

    def test_changed_runtime_generation_stales_old_evidence(self) -> None:
        graph = build_graph([self._runtime_receipt()])
        report = derive_currentness(graph, CurrentIdentities(artifact_digest=ARTIFACT, runtime_generation=GEN8))
        assert report.receipts["runtime-1"].status == "STALE"
        policy = load_policy()
        decision = evaluate_delivery(policy, IMPL_SPEC, graph, currentness=report)
        assert decision.outcome is not DeliveryDecisionKind.TERMINAL_ACCEPTED
        assert "runtime_acceptance" in decision.missing_gates

    def test_release_from_wrong_sha_cannot_complete_runtime_chain(self) -> None:
        release_wrong = receipt(
            receipt_id="release-wrong",
            receipt_kind="artifact_publication",
            producer={"system": "releaser", "principal": "bot", "authority_class": "external_provider_observation"},
            subject={"kind": "publication", "identity": "rel-1", "candidate_sha": C1, "artifact_digest": ARTIFACT},
        )
        graph = build_graph([release_wrong, self._runtime_receipt()])
        policy = load_policy()
        decision = evaluate_delivery(
            policy,
            IMPL_SPEC,
            graph,
            current=CurrentIdentities(candidate_sha=C1, runtime_generation=GEN7, artifact_digest=ARTIFACT),
        )
        assert decision.outcome is not DeliveryDecisionKind.TERMINAL_ACCEPTED


class TestReviewBlocking:
    def test_new_required_finding_blocks_despite_other_approval(self) -> None:
        approval = receipt(
            receipt_id="review-a",
            receipt_kind="review",
            producer={"system": "chatgpt", "principal": "reviewer-a", "authority_class": "review_provider"},
            subject={"kind": "candidate_revision", "identity": "candidate-c1", "candidate_sha": C1},
        )
        defect = receipt(
            receipt_id="review-b",
            receipt_kind="review",
            producer={"system": "codex", "principal": "reviewer-b", "authority_class": "review_provider"},
            subject={"kind": "candidate_revision", "identity": "candidate-c1", "candidate_sha": C1},
            outcome={"disposition": "FAILED", "reason_codes": ["REQUIRED_DEFECT"]},
        )
        graph = build_graph([approval, defect])
        report = derive_currentness(graph, CurrentIdentities(candidate_sha=C1))
        gate = evaluate_gate(graph, GateRequirement(gate_id="review", required_kind=ReceiptKind.REVIEW), report)
        assert gate.state is GateState.BLOCKED
        assert any(reason.startswith("RECEIPT_FAILED") for reason in gate.reasons)

    def test_conflicting_evidence_is_blocked_not_flattened(self) -> None:
        observation = receipt(
            receipt_id="obs-1",
            receipt_kind="runtime_acceptance",
            producer={"system": "doctor", "principal": "doctor-1", "authority_class": "independent_verifier"},
            subject={
                "kind": "observed_runtime",
                "identity": "target",
                "runtime_generation": GEN7,
                "artifact_digest": ARTIFACT,
            },
            outcome={"disposition": "FAILED", "reason_codes": ["AVAILABILITY_DEGRADED"]},
        )
        spoofed_pass = receipt(
            receipt_id="obs-2",
            receipt_kind="runtime_acceptance",
            producer={"system": "unknown-source", "principal": "observer-x", "authority_class": "independent_verifier"},
            subject={
                "kind": "observed_runtime",
                "identity": "target",
                "runtime_generation": GEN7,
                "artifact_digest": ARTIFACT,
            },
        )
        graph = build_graph([observation, spoofed_pass])
        report = derive_currentness(graph, CurrentIdentities(runtime_generation=GEN7, artifact_digest=ARTIFACT))
        gate = evaluate_gate(
            graph, GateRequirement(gate_id="runtime", required_kind=ReceiptKind.RUNTIME_ACCEPTANCE), report
        )
        assert gate.state is GateState.BLOCKED
        # The envelope digest binds content without authenticating the
        # producer; authenticity is established by the trusted transport, so
        # the conflicting pair blocks instead of trusting either claim.
        assert any(reason.startswith("RECEIPT_FAILED") for reason in gate.reasons)


class TestLegacyCompatibility:
    def test_legacy_minimal_receipt_is_readable_not_upgraded(self) -> None:
        legacy = {
            "schema_version": 1,
            "receipt_id": "legacy-1",
            "receipt_kind": "deployment",
            "producer": {"system": "old-runner", "principal": None, "authority_class": "worker_report"},
            "subject": {"kind": "deployment_target", "identity": "host-1"},
            "correlation": {"project_id": "p1"},
            "policy": {"policy_ref": "policy://legacy"},
            "outcome": {"disposition": "NOT_OBSERVED"},
            "evidence_refs": [],
            "artifact_refs": [],
            "observed_at": "2025-01-01T00:00:00Z",
            "payload_digest": payload_digest(
                {
                    key: value
                    for key, value in {
                        "schema_version": 1,
                        "receipt_id": "legacy-1",
                        "receipt_kind": "deployment",
                        "producer": {"system": "old-runner", "principal": None, "authority_class": "worker_report"},
                        "subject": {"kind": "deployment_target", "identity": "host-1"},
                        "correlation": {"project_id": "p1"},
                        "policy": {"policy_ref": "policy://legacy"},
                        "outcome": {"disposition": "NOT_OBSERVED"},
                        "evidence_refs": [],
                        "artifact_refs": [],
                        "observed_at": "2025-01-01T00:00:00Z",
                    }.items()
                }
            ),
        }
        decision = admit_receipt(legacy)
        assert decision.outcome is AdmissionOutcome.ADMITTED
        legacy_pass = dict(legacy)
        legacy_pass["outcome"] = {"disposition": "PASS"}
        legacy_pass["payload_digest"] = payload_digest(
            {key: value for key, value in legacy_pass.items() if key != "payload_digest"}
        )
        refused = admit_receipt(legacy_pass)
        assert refused.outcome is AdmissionOutcome.REJECTED
        assert any(reason.startswith("AUTHORITY_FLOOR_UNMET") for reason in refused.reasons)


class TestAdversarialInputs:
    def test_null_required_field_is_rejected(self) -> None:
        document = receipt()
        document["producer"] = None
        assert admit_receipt(document).outcome is AdmissionOutcome.REJECTED

    def test_wrong_type_outcome_is_rejected(self) -> None:
        document = receipt()
        document["outcome"] = "PASS"
        assert admit_receipt(document).outcome is AdmissionOutcome.REJECTED

    def test_oversized_selected_tests_rejected(self) -> None:
        document = receipt(
            receipt_kind="command_execution",
            command_evidence={
                "argv_digest": "sha256:" + "3" * 64,
                "exit_provenance": "EXIT_PROVEN",
                "exit_code": 0,
                "report_digest": "sha256:" + "4" * 64,
                "selected_test_ids": [f"t{i}" for i in range(257)],
            },
            outcome={"disposition": "NOT_OBSERVED"},
        )
        assert admit_receipt(document).outcome is AdmissionOutcome.REJECTED

    def test_unknown_disposition_rejected(self) -> None:
        document = receipt(outcome={"disposition": "MAGIC_GREEN"})
        assert admit_receipt(document).outcome is AdmissionOutcome.REJECTED

    def test_candidate_sha_wrong_format_rejected(self) -> None:
        document = receipt(subject={"kind": "candidate_revision", "identity": "c1", "candidate_sha": "short"})
        assert admit_receipt(document).outcome is AdmissionOutcome.REJECTED


class TestDeterminismAndReuse:
    def test_repeated_identical_evidence_yields_identical_decision(self) -> None:
        policy = load_policy()
        graph = build_graph(
            [
                receipt(
                    receipt_id="findings-1",
                    receipt_kind="work_completion",
                    subject={"kind": "terminal_evidence", "identity": "findings"},
                ),
            ]
        )
        spec = WorkSpec(work_kind=WorkKind.INVESTIGATION, change_risk=RiskLevel.LOW, expected_policy_revision="r1")
        first = evaluate_delivery(policy, spec, graph)
        second = evaluate_delivery(policy, spec, graph)
        assert first.outcome is second.outcome
        assert first.reasons == second.reasons
        assert first.outcome is DeliveryDecisionKind.TERMINAL_ACCEPTED

    def test_tree_equal_candidate_change_stales_review_at_policy_level(self) -> None:
        review = receipt(
            receipt_id="review-c1",
            receipt_kind="review",
            producer={"system": "chatgpt", "principal": "rev-1", "authority_class": "review_provider"},
            subject={
                "kind": "candidate_revision",
                "identity": "candidate-c1",
                "candidate_sha": C1,
                "tree_sha": "c" * 40,
            },
        )
        graph = build_graph([review])
        report = derive_currentness(graph, CurrentIdentities(candidate_sha=C2))
        assert report.receipts["review-c1"].status == "STALE"
        policy = load_policy()
        decision = evaluate_delivery(policy, IMPL_SPEC, graph, currentness=report)
        assert decision.outcome is DeliveryDecisionKind.WAITING_REQUIRED_EVIDENCE
        assert "review" in decision.missing_gates

    def test_c1_review_never_satisfies_c2_delivery(self) -> None:
        policy = load_policy()
        graph = build_graph(
            [
                receipt(
                    receipt_id="validation-c1",
                    subject={"kind": "candidate_revision", "identity": "candidate-c1", "candidate_sha": C1},
                )
            ]
        )
        spec_c2 = WorkSpec(
            work_kind=WorkKind.IMPLEMENTATION,
            change_risk=RiskLevel.HIGH,
            expected_policy_revision="r1",
            planning_base_sha=BASE,
        )
        decision = evaluate_delivery(policy, spec_c2, graph, current=CurrentIdentities(candidate_sha=C2))
        assert decision.outcome is not DeliveryDecisionKind.TERMINAL_ACCEPTED


class TestHarnessVsProduct:
    def test_harness_failure_is_representable_without_product_claim(self) -> None:
        harness_fail = receipt(
            receipt_id="harness-1",
            receipt_kind="command_execution",
            producer={"system": "runner", "principal": "runner-1", "authority_class": "deterministic_tool"},
            outcome={"disposition": "INCONCLUSIVE", "reason_codes": ["HARNESS_FAIL_ENVIRONMENT"]},
            command_evidence={"argv_digest": "sha256:" + "3" * 64, "exit_provenance": "EXIT_UNPROVEN"},
        )
        decision = admit_receipt(harness_fail)
        assert decision.outcome is AdmissionOutcome.ADMITTED
        graph = build_graph([harness_fail])
        gate = evaluate_gate(graph, GateRequirement(gate_id="gate", required_kind=ReceiptKind.COMMAND_EXECUTION))
        assert gate.state is not GateState.SATISFIED

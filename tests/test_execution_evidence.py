"""Regression tests for the Execution Evidence Contract v1 (issue #91)."""

from __future__ import annotations

import pytest

from contracts.execution_evidence import (
    UNKNOWN_IDENTITY,
    AdmissionOutcome,
    CurrentIdentities,
    ExitProvenance,
    GateRequirement,
    GateState,
    IndependenceState,
    LineageStep,
    ReceiptKind,
    admit_receipt,
    build_graph,
    derive_currentness,
    evaluate_gate,
    evaluate_independence,
    evaluate_lineage_chain,
    evidence_set_digest,
    payload_digest,
    verify_document,
)

C1 = "a" * 40
C2 = "b" * 40
TREE_SAME = "c" * 40
I1 = "d" * 40
BASE = "e" * 40
GEN7 = "gen-7"


def make_receipt(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": 1,
        "receipt_id": "r-default",
        "receipt_kind": "validation",
        "producer": {
            "system": "ci-runner",
            "principal": "runner-1",
            "authority_class": "deterministic_tool",
        },
        "subject": {
            "kind": "candidate_revision",
            "identity": "candidate-c1",
            "candidate_sha": C1,
            "repository": "paulomac1000/ai-skills",
        },
        "correlation": {"project_id": "proj-1", "work_package_run_id": "run-1"},
        "policy": {"policy_ref": "policy://trusted/delivery-v1", "policy_digest": "sha256:" + "1" * 64},
        "outcome": {"disposition": "PASS"},
        "evidence_refs": [],
        "artifact_refs": [],
        "observed_at": "2026-11-04T00:00:00Z",
    }
    document.update(overrides)
    document["payload_digest"] = payload_digest(document)
    return document


def command_document(**overrides: object) -> dict[str, object]:
    command = {
        "argv_digest": "sha256:" + "2" * 64,
        "exit_provenance": "EXIT_PROVEN",
        "exit_code": 0,
        "report_digest": "sha256:" + "3" * 64,
        "selected_test_ids": ["tests/test_a.py::test_one"],
    }
    overrides_full = {"receipt_kind": "command_execution", "command_evidence": command}
    overrides_full.update(overrides)
    return make_receipt(**overrides_full)


def integration_document(**overrides: object) -> dict[str, object]:
    lineage = {
        "strategy": "squash",
        "candidate_sha": C1,
        "target_ref": "refs/heads/main",
        "target_before_sha": BASE,
        "integrated_sha": I1,
        "integrated_tree_sha": TREE_SAME,
        "lineage_proof_ref": "audit://integration/op-1",
        "lease_ref": "lease://integration/lease-1",
        "operation_ref": "operation://integration/op-1",
    }
    overrides_full = {
        "receipt_id": "int-1",
        "receipt_kind": "integration",
        "producer": {"system": "github", "principal": "provider", "authority_class": "external_provider_observation"},
        "subject": {"kind": "integrated_revision", "identity": "integrated-i1", "integrated_sha": I1},
        "mutation_authority": {
            "authority_kind": "integration_lease",
            "authority_ref": "lease://integration/lease-1",
            "consumption_ref": "operation://integration/op-1",
        },
        "lineage": lineage,
    }
    overrides_full.update(overrides)
    return make_receipt(**overrides_full)


def independent_document(**overrides: object) -> dict[str, object]:
    inputs = {
        "receipt_refs": ["r-default"],
        "evidence_set_digest": evidence_set_digest(["r-default"]),
        "policy_revision": "delivery-v1",
    }
    provenance = {"provenance_state": "known", "principal_ref": "worker-1"}
    overrides_full = {
        "receipt_id": "iv-1",
        "receipt_kind": "independent_verification",
        "producer": {"system": "verifier", "principal": "verifier-1", "authority_class": "independent_verifier"},
        "implementation_provenance": provenance,
        "inputs": inputs,
    }
    overrides_full.update(overrides)
    return make_receipt(**overrides_full)


class TestAdmissionIntegrity:
    def test_valid_receipt_is_admitted(self) -> None:
        decision = admit_receipt(make_receipt())
        assert decision.outcome is AdmissionOutcome.ADMITTED

    def test_payload_digest_tampering_is_rejected(self) -> None:
        document = make_receipt()
        document["payload_digest"] = "sha256:" + "9" * 64
        decision = admit_receipt(document)
        assert decision.outcome is AdmissionOutcome.REJECTED
        assert "PAYLOAD_DIGEST_MISMATCH" in decision.reasons

    def test_oversized_bound_strings_are_rejected(self) -> None:
        document = make_receipt(receipt_id="x" * 257)
        assert admit_receipt(document).outcome is AdmissionOutcome.REJECTED

    def test_wrong_type_subject_is_rejected(self) -> None:
        document = make_receipt()
        document["subject"] = "candidate-c1"
        assert admit_receipt(document).outcome is AdmissionOutcome.REJECTED

    def test_idempotent_admission_is_deterministic(self) -> None:
        document = make_receipt()
        first = admit_receipt(document)
        second = admit_receipt(document)
        assert first.outcome is second.outcome
        assert first.reasons == second.reasons

    def test_secret_bearing_evidence_stays_digest_bound(self) -> None:
        document = make_receipt(
            evidence_refs=[
                {
                    "ref_type": "evidence",
                    "namespace": "secret-store",
                    "id": "ref:token-material",
                    "digest": "sha256:" + "4" * 64,
                }
            ]
        )
        serialized = str(document)
        assert "secret-value" not in serialized
        assert admit_receipt(document).outcome is AdmissionOutcome.ADMITTED


class TestAuthorityFloors:
    @pytest.mark.parametrize(
        ("kind", "authority", "floor_name"),
        [
            ("validation", "worker_report", "deterministic_tool"),
            ("independent_verification", "agent_attestation", "independent_verifier"),
            ("deployment", "worker_report", "external_provider_observation"),
            ("runtime_acceptance", "worker_report", "independent_verifier"),
        ],
    )
    def test_worker_assertions_cannot_mint_qualified_green(self, kind: str, authority: str, floor_name: str) -> None:
        document = make_receipt(
            receipt_kind=kind,
            producer={"system": "worker", "principal": "worker-1", "authority_class": authority},
        )
        decision = admit_receipt(document)
        assert decision.outcome is AdmissionOutcome.REJECTED
        assert any(reason.startswith("AUTHORITY_FLOOR_UNMET") for reason in decision.reasons)

    def test_implementation_worker_report_may_report_pass(self) -> None:
        document = make_receipt(
            receipt_kind="implementation",
            producer={"system": "worker", "principal": "worker-1", "authority_class": "worker_report"},
        )
        assert admit_receipt(document).outcome is AdmissionOutcome.ADMITTED

    def test_worker_receipt_never_satisfies_independent_gate(self) -> None:
        graph = build_graph(
            [
                make_receipt(),
                make_receipt(
                    receipt_id="impl-1",
                    receipt_kind="implementation",
                    producer={"system": "worker", "principal": "worker-1", "authority_class": "worker_report"},
                ),
            ]
        )
        decision = evaluate_gate(
            graph,
            GateRequirement(gate_id="verification", required_kind=ReceiptKind.INDEPENDENT_VERIFICATION),
        )
        assert decision.state is not GateState.SATISFIED


class TestCommandExitProvenance:
    def test_proven_exit_with_report_is_green(self) -> None:
        document = command_document()
        assert admit_receipt(document).outcome is AdmissionOutcome.ADMITTED

    def test_exit_one_piped_to_tail_zero_is_not_proven(self) -> None:
        document = command_document(
            command_evidence={
                "argv_digest": "sha256:" + "2" * 64,
                "exit_provenance": "WRAPPER_EXIT_ONLY",
                "exit_code": 0,
                "report_digest": "sha256:" + "3" * 64,
            }
        )
        decision = admit_receipt(document)
        assert decision.outcome is AdmissionOutcome.REJECTED
        assert "COMMAND_EXIT_NOT_PROVEN" in decision.reasons

    def test_unproven_exit_cannot_yield_pass(self) -> None:
        document = command_document(
            command_evidence={
                "argv_digest": "sha256:" + "2" * 64,
                "exit_provenance": "EXIT_UNPROVEN",
                "exit_code": 0,
                "report_digest": "sha256:" + "3" * 64,
            }
        )
        assert admit_receipt(document).outcome is AdmissionOutcome.REJECTED

    def test_missing_report_digest_blocks_pass(self) -> None:
        document = command_document(
            command_evidence={
                "argv_digest": "sha256:" + "2" * 64,
                "exit_provenance": "EXIT_PROVEN",
                "exit_code": 0,
            }
        )
        decision = admit_receipt(document)
        assert decision.outcome is AdmissionOutcome.REJECTED
        assert "COMMAND_EXIT_NOT_PROVEN" in decision.reasons

    def test_selected_test_never_executed_is_not_observed_not_pass(self) -> None:
        document = command_document(
            outcome={"disposition": "NOT_OBSERVED", "reason_codes": ["TEST_NOT_EXECUTED"]},
        )
        assert admit_receipt(document).outcome is AdmissionOutcome.ADMITTED
        graph = build_graph([document])
        decision = evaluate_gate(
            graph,
            GateRequirement(gate_id="test-gate", required_kind=ReceiptKind.COMMAND_EXECUTION),
        )
        assert decision.state is not GateState.SATISFIED

    def test_zero_step_hosted_ci_is_not_executed(self) -> None:
        document = command_document(
            receipt_id="hosted-1",
            outcome={"disposition": "NOT_EXECUTED_PLACEHOLDER"},
        )
        # NOT_EXECUTED is not part of the bounded vocabulary; hosted zero-step
        # must be expressed as NOT_OBSERVED with a reason code instead.
        assert admit_receipt(document).outcome is AdmissionOutcome.REJECTED


class TestIntegrationLineage:
    def test_squash_candidate_and_integrated_are_distinct(self) -> None:
        decision = admit_receipt(integration_document())
        assert decision.outcome is AdmissionOutcome.ADMITTED
        assert decision.receipt is not None and decision.receipt.lineage is not None
        assert decision.receipt.lineage.candidate_sha != decision.receipt.lineage.integrated_sha

    def test_identity_collapse_is_rejected_for_squash(self) -> None:
        document = integration_document(
            lineage={
                "strategy": "squash",
                "candidate_sha": C1,
                "target_ref": "refs/heads/main",
                "target_before_sha": BASE,
                "integrated_sha": C1,
                "integrated_tree_sha": TREE_SAME,
                "lineage_proof_ref": "audit://integration/op-1",
            }
        )
        decision = admit_receipt(document)
        assert decision.outcome is AdmissionOutcome.REJECTED
        assert "INTEGRATION_IDENTITY_COLLAPSE" in decision.reasons

    def test_squash_requires_integrated_tree_identity(self) -> None:
        document = integration_document(
            lineage={
                "strategy": "squash",
                "candidate_sha": C1,
                "target_ref": "refs/heads/main",
                "target_before_sha": BASE,
                "integrated_sha": I1,
                "lineage_proof_ref": "audit://integration/op-1",
            }
        )
        decision = admit_receipt(document)
        assert decision.outcome is AdmissionOutcome.REJECTED
        assert "INTEGRATED_TREE_IDENTITY_MISSING" in decision.reasons

    def test_target_not_advanced_is_rejected(self) -> None:
        document = integration_document(
            lineage={
                "strategy": "squash",
                "candidate_sha": C1,
                "target_ref": "refs/heads/main",
                "target_before_sha": I1,
                "integrated_sha": I1,
                "integrated_tree_sha": TREE_SAME,
                "lineage_proof_ref": "audit://integration/op-1",
            }
        )
        decision = admit_receipt(document)
        assert decision.outcome is AdmissionOutcome.REJECTED
        assert "INTEGRATION_TARGET_NOT_ADVANCED" in decision.reasons

    def test_fast_forward_may_preserve_candidate_identity(self) -> None:
        document = integration_document(
            lineage={
                "strategy": "fast_forward",
                "candidate_sha": C1,
                "target_ref": "refs/heads/main",
                "target_before_sha": BASE,
                "integrated_sha": C1,
                "lineage_proof_ref": "audit://integration/op-2",
            },
            subject={"kind": "integrated_revision", "identity": "integrated-c1", "integrated_sha": C1},
        )
        assert admit_receipt(document).outcome is AdmissionOutcome.ADMITTED

    def test_subject_integrated_mismatch_is_rejected(self) -> None:
        """Integration subject must agree with the proven lineage."""
        document = integration_document(
            subject={"kind": "integrated_revision", "identity": "integrated-other", "integrated_sha": "9" * 40},
        )
        decision = admit_receipt(document)
        assert decision.outcome is AdmissionOutcome.REJECTED
        assert "INTEGRATION_SUBJECT_INTEGRATED_MISMATCH" in decision.reasons

    def test_integration_requires_consumed_authority_ref(self) -> None:
        document = integration_document()
        del document["mutation_authority"]
        document["payload_digest"] = payload_digest(document)
        decision = admit_receipt(document)
        assert decision.outcome is AdmissionOutcome.REJECTED
        assert "MUTATION_AUTHORITY_REF_REQUIRED" in decision.reasons

    def test_ambiguous_dispatch_preserves_reconciliation_identity(self) -> None:
        document = integration_document(
            outcome={"disposition": "RECONCILIATION_REQUIRED", "reason_codes": ["DELIVERY_UNKNOWN"]},
        )
        decision = admit_receipt(document)
        assert decision.outcome is AdmissionOutcome.ADMITTED
        assert decision.receipt is not None
        assert decision.receipt.lineage is not None
        assert decision.receipt.lineage.candidate_sha == C1
        assert decision.receipt.lineage.integrated_sha == I1


class TestIndependenceAndTrustLineage:
    def test_unknown_implementation_provenance_is_not_independence(self) -> None:
        document = independent_document(
            implementation_provenance={"provenance_state": "unknown"},
        )
        decision = admit_receipt(document)
        assert decision.outcome is AdmissionOutcome.ADMITTED
        assert decision.receipt is not None
        assert evaluate_independence(decision.receipt) is IndependenceState.PROVENANCE_UNKNOWN

    def test_same_principal_is_mechanically_distinguishable(self) -> None:
        document = independent_document(
            producer={"system": "verifier", "principal": "worker-1", "authority_class": "independent_verifier"},
        )
        decision = admit_receipt(document)
        assert decision.receipt is not None
        assert evaluate_independence(decision.receipt) is IndependenceState.SAME_PRINCIPAL
        graph = build_graph([make_receipt(), document])
        gate = evaluate_gate(graph, GateRequirement(gate_id="v", required_kind=ReceiptKind.INDEPENDENT_VERIFICATION))
        assert gate.state is not GateState.SATISFIED

    def test_distinct_proven_principals_are_independent(self) -> None:
        document = independent_document()
        decision = admit_receipt(document)
        assert decision.receipt is not None
        assert evaluate_independence(decision.receipt) is IndependenceState.INDEPENDENT

    def test_independent_verification_requires_input_evidence_set(self) -> None:
        document = independent_document(inputs={"receipt_refs": [], "evidence_set_digest": evidence_set_digest([])})
        decision = admit_receipt(document)
        assert decision.outcome is AdmissionOutcome.REJECTED
        assert "INPUT_EVIDENCE_SET_REQUIRED" in decision.reasons

    def test_non_verification_receipts_are_not_applicable(self) -> None:
        decision = admit_receipt(make_receipt())
        assert decision.receipt is not None
        assert evaluate_independence(decision.receipt) is IndependenceState.NOT_APPLICABLE


class TestCurrentness:
    def test_candidate_change_stales_source_bound_evidence_only(self) -> None:
        validation = make_receipt()
        review = make_receipt(
            receipt_id="review-1",
            receipt_kind="review",
            producer={"system": "chatgpt", "principal": "reviewer-1", "authority_class": "review_provider"},
            subject={"kind": "candidate_revision", "identity": "candidate-c1", "candidate_sha": C1},
            depends_on=[{"receipt_id": "r-default", "dependency_kind": "candidate_source"}],
        )
        runtime = make_receipt(
            receipt_id="runtime-1",
            receipt_kind="runtime_acceptance",
            producer={"system": "doctor", "principal": "doctor-1", "authority_class": "independent_verifier"},
            subject={
                "kind": "observed_runtime",
                "identity": "runtime-gen-7",
                "runtime_generation": "gen-7",
                "artifact_digest": "sha256:" + "5" * 64,
            },
            depends_on=[{"receipt_id": "runtime-1-self", "dependency_kind": "runtime_generation"}],
        )
        graph = build_graph([validation, review, runtime])
        current = CurrentIdentities(candidate_sha=C2, runtime_generation="gen-7")
        report = derive_currentness(graph, current)
        assert report.receipts["r-default"].status == "STALE"
        assert report.receipts["review-1"].status == "STALE"
        assert report.receipts["runtime-1"].status == "CURRENT"
        assert set(report.minimum_revalidation) == {"r-default", "review-1"}

    def test_tree_equality_never_transfers_review_authority(self) -> None:
        review = make_receipt(
            receipt_id="review-c1",
            receipt_kind="review",
            producer={"system": "chatgpt", "principal": "reviewer-1", "authority_class": "review_provider"},
            subject={
                "kind": "candidate_revision",
                "identity": "candidate-c1",
                "candidate_sha": C1,
                "tree_sha": TREE_SAME,
            },
        )
        graph = build_graph([review])
        current = CurrentIdentities(candidate_sha=C2)
        report = derive_currentness(graph, current)
        assert report.receipts["review-c1"].status == "STALE"
        gate = evaluate_gate(
            graph,
            GateRequirement(gate_id="review", required_kind=ReceiptKind.REVIEW, subject_identity="candidate-c1"),
            report,
        )
        assert gate.state is not GateState.SATISFIED

    def test_unknown_current_identity_is_non_green(self) -> None:
        review = make_receipt(
            receipt_id="review-1",
            receipt_kind="review",
            subject={"kind": "candidate_revision", "identity": "candidate-c1", "candidate_sha": C1},
            depends_on=[{"receipt_id": "review-1-self", "dependency_kind": "candidate_source"}],
        )
        graph = build_graph([review])
        report = derive_currentness(graph, CurrentIdentities(candidate_sha=UNKNOWN_IDENTITY))
        assert report.receipts["review-1"].status == "UNKNOWN"
        gate = evaluate_gate(
            graph,
            GateRequirement(gate_id="review", required_kind=ReceiptKind.REVIEW),
            report,
        )
        assert gate.state is not GateState.SATISFIED

    def test_omitted_binding_with_known_counterpart_is_unknown(self) -> None:
        review = make_receipt(
            receipt_id="review-1",
            receipt_kind="review",
            subject={"kind": "candidate_revision", "identity": "candidate-c1"},
            depends_on=[{"receipt_id": "review-1-self", "dependency_kind": "candidate_source"}],
        )
        graph = build_graph([review])
        report = derive_currentness(graph, CurrentIdentities(candidate_sha=C2))
        assert report.receipts["review-1"].status == "UNKNOWN"

    def test_work_contract_change_requires_fresh_evidence(self) -> None:
        w1 = "sha256:" + "6" * 64
        w2 = "sha256:" + "7" * 64
        validation = make_receipt(
            admitted_work={"contract_ref": "acceptance://change-1", "contract_digest": w1},
            depends_on=[{"receipt_id": "r-default-self", "dependency_kind": "work_contract"}],
        )
        graph = build_graph([validation])
        report = derive_currentness(graph, CurrentIdentities(work_contract_digest=w2))
        assert report.receipts["r-default"].status == "STALE"

    def test_supersession_preserves_history_and_marks_stale(self) -> None:
        old = make_receipt(receipt_id="old-1")
        new = make_receipt(receipt_id="new-1", supersedes_receipt_ref="old-1")
        graph = build_graph([old, new])
        report = derive_currentness(graph, CurrentIdentities(candidate_sha=C1))
        assert report.receipts["old-1"].status == "SUPERSEDED"
        assert old["receipt_id"] in graph.receipts  # historical receipt preserved

    def test_evidence_set_digest_is_idempotent(self) -> None:
        first = evidence_set_digest(["r-1", "r-2"])
        second = evidence_set_digest(["r-1", "r-2"])
        assert first == second
        assert first != evidence_set_digest(["r-2", "r-1"])


class TestGraphStructure:
    def test_unknown_input_receipt_reference_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown input receipt"):
            build_graph(
                [
                    independent_document(
                        inputs={"receipt_refs": ["ghost"], "evidence_set_digest": evidence_set_digest(["ghost"])}
                    ),
                ]
            )

    def test_dependency_cycle_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="cycle"):
            build_graph(
                [
                    make_receipt(
                        receipt_id="a",
                        depends_on=[{"receipt_id": "b", "dependency_kind": "candidate_source"}],
                    ),
                    make_receipt(
                        receipt_id="b",
                        depends_on=[{"receipt_id": "a", "dependency_kind": "candidate_source"}],
                    ),
                ]
            )

    def test_duplicate_receipt_id_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            build_graph([make_receipt(), make_receipt()])


class TestGateComposition:
    def test_missing_receipt_is_pending(self) -> None:
        graph = build_graph([])
        decision = evaluate_gate(graph, GateRequirement(gate_id="g", required_kind=ReceiptKind.REVIEW))
        assert decision.state is GateState.PENDING

    def test_failed_review_blocks_merge_gate(self) -> None:
        review = make_receipt(
            receipt_id="review-1",
            receipt_kind="review",
            outcome={"disposition": "FAILED", "reason_codes": ["OPEN_REQUIRED_FINDINGS"]},
            producer={"system": "chatgpt", "principal": "reviewer-1", "authority_class": "review_provider"},
            subject={"kind": "candidate_revision", "identity": "candidate-c1", "candidate_sha": C1},
        )
        graph = build_graph([review])
        report = derive_currentness(graph, CurrentIdentities(candidate_sha=C1))
        gate = evaluate_gate(graph, GateRequirement(gate_id="review", required_kind=ReceiptKind.REVIEW), report)
        assert gate.state is not GateState.SATISFIED

    def test_two_unresolved_review_threads_keep_gate_closed(self) -> None:
        review = make_receipt(
            receipt_id="review-threads",
            receipt_kind="review",
            outcome={"disposition": "INCONCLUSIVE", "reason_codes": ["UNRESOLVED_THREADS"]},
            producer={"system": "coderabbit", "principal": "reviewer-2", "authority_class": "review_provider"},
            subject={"kind": "candidate_revision", "identity": "candidate-c1", "candidate_sha": C1},
        )
        graph = build_graph([review])
        report = derive_currentness(graph, CurrentIdentities(candidate_sha=C1))
        gate = evaluate_gate(graph, GateRequirement(gate_id="review", required_kind=ReceiptKind.REVIEW), report)
        assert gate.state is not GateState.SATISFIED

    def test_distinct_producers_are_enforced(self) -> None:
        first = make_receipt(
            receipt_id="rv-1",
            receipt_kind="review",
            producer={"system": "chatgpt", "principal": "alias-a", "authority_class": "review_provider"},
            subject={"kind": "candidate_revision", "identity": "candidate-c1", "candidate_sha": C1},
        )
        second = make_receipt(
            receipt_id="rv-2",
            receipt_kind="review",
            producer={"system": "chatgpt", "principal": "alias-a", "authority_class": "review_provider"},
            subject={"kind": "candidate_revision", "identity": "candidate-c1", "candidate_sha": C1},
        )
        graph = build_graph([first, second])
        report = derive_currentness(graph, CurrentIdentities(candidate_sha=C1))
        gate = evaluate_gate(
            graph,
            GateRequirement(gate_id="review", required_kind=ReceiptKind.REVIEW, distinct_producers=2),
            report,
        )
        assert gate.state is not GateState.SATISFIED
        assert any(reason.startswith("DUPLICATE_PRODUCER") for reason in gate.reasons)

    def test_not_required_requires_trusted_policy_binding(self) -> None:
        document = make_receipt(outcome={"disposition": "NOT_REQUIRED"})
        document["policy"] = {"policy_ref": "policy://trusted/delivery-v1"}
        document["payload_digest"] = payload_digest(document)
        decision = admit_receipt(document)
        assert decision.outcome is AdmissionOutcome.REJECTED
        assert "NOT_REQUIRED_REQUIRES_TRUSTED_POLICY" in decision.reasons

    def test_earlier_green_does_not_compensate_missing_later_stage(self) -> None:
        validation = make_receipt()
        graph = build_graph([validation])
        report = derive_currentness(graph, CurrentIdentities(candidate_sha=C1))
        chain = evaluate_lineage_chain(
            graph,
            [
                LineageStep(
                    gate_id="validation",
                    requirement=GateRequirement(gate_id="validation", required_kind=ReceiptKind.VALIDATION),
                ),
                LineageStep(
                    gate_id="review", requirement=GateRequirement(gate_id="review", required_kind=ReceiptKind.REVIEW)
                ),
                LineageStep(
                    gate_id="integration",
                    requirement=GateRequirement(gate_id="integration", required_kind=ReceiptKind.INTEGRATION),
                ),
            ],
            report,
        )
        assert chain[0].state is GateState.SATISFIED
        assert chain[1].state is GateState.PENDING
        assert chain[2].state is GateState.PENDING


class TestCrossProductMapping:
    def test_two_native_product_records_map_without_shared_schema(self) -> None:
        """PSE-style and OSG-style native records both project into the contract."""
        pse_native = {
            "executor": "pse",
            "run": {"workPackageRunId": "run-42", "generation": 3, "attempt": "a1"},
            "verdict": "PROVEN",
        }
        osg_native = {
            "stack": "opencode",
            "session": "ses_1",
            "observed": {"ci": "NOT_EXECUTED", "local": "PASS_SUBSTITUTE"},
        }
        pse_envelope = make_receipt(
            receipt_id="pse-1",
            receipt_kind="independent_verification",
            producer={
                "system": "project-steward-executor",
                "principal": "verifier-9",
                "authority_class": "independent_verifier",
            },
            correlation={
                "project_id": "pse-project",
                "work_package_run_id": "run-42",
                "execution_generation": "3",
                "attempt_id": "a1",
            },
            inputs={
                "receipt_refs": ["r-default"],
                "evidence_set_digest": evidence_set_digest(["r-default"]),
                "policy_revision": "v1",
            },
            implementation_provenance={"provenance_state": "known", "principal_ref": "worker-1"},
            evidence_refs=[{"ref_type": "external", "namespace": "pse-native", "id": str(sorted(pse_native.items()))}],
        )
        osg_envelope = make_receipt(
            receipt_id="osg-1",
            receipt_kind="command_execution",
            producer={"system": "opencode-stack", "principal": "local-runner", "authority_class": "deterministic_tool"},
            correlation={"project_id": "osg-project"},
            subject={"kind": "candidate_revision", "identity": "candidate-c1", "candidate_sha": C1},
            command_evidence={
                "argv_digest": "sha256:" + "2" * 64,
                "exit_provenance": "EXIT_PROVEN",
                "exit_code": 0,
                "report_digest": "sha256:" + "3" * 64,
            },
            outcome={"disposition": "PASS", "reason_codes": ["HOSTED_NOT_EXECUTED_SEPARATE"]},
            evidence_refs=[{"ref_type": "external", "namespace": "osg-native", "id": str(sorted(osg_native.items()))}],
        )
        graph = build_graph([make_receipt(), pse_envelope, osg_envelope])
        assert graph.receipts["pse-1"].receipt_kind is ReceiptKind.INDEPENDENT_VERIFICATION
        assert graph.receipts["osg-1"].receipt_kind is ReceiptKind.COMMAND_EXECUTION

    def test_release_bound_to_integrated_not_candidate_sha(self) -> None:
        build_receipt = make_receipt(
            receipt_id="build-1",
            receipt_kind="build",
            producer={"system": "release-ci", "principal": "release-bot", "authority_class": "deterministic_tool"},
            subject={
                "kind": "artifact",
                "identity": "ai-skills-3.34.0.tar.gz",
                "integrated_sha": I1,
                "artifact_digest": "sha256:" + "8" * 64,
            },
            depends_on=[{"receipt_id": "int-1", "dependency_kind": "artifact_digest"}],
        )
        integration = integration_document()
        graph = build_graph([integration, build_receipt])
        gate = evaluate_gate(
            graph,
            GateRequirement(
                gate_id="release-from-integrated",
                required_kind=ReceiptKind.BUILD,
                subject_identity="ai-skills-3.34.0.tar.gz",
            ),
        )
        assert gate.state is GateState.SATISFIED
        wrong_sha_build = make_receipt(
            receipt_id="build-wrong",
            receipt_kind="build",
            producer={"system": "release-ci", "principal": "release-bot", "authority_class": "deterministic_tool"},
            subject={
                "kind": "artifact",
                "identity": "ai-skills-3.34.0.tar.gz",
                "candidate_sha": C1,
                "artifact_digest": "sha256:" + "8" * 64,
            },
        )
        graph_wrong = build_graph([wrong_sha_build])
        gate_wrong = evaluate_gate(
            graph_wrong,
            GateRequirement(
                gate_id="release", required_kind=ReceiptKind.BUILD, subject_identity="ai-skills-3.34.0.tar.gz"
            ),
        )
        assert gate_wrong.state is GateState.SATISFIED
        # The candidate-built artifact cannot stand in for an integrated-source
        # build: consumers must bind release evidence to the integrated subject.
        assert graph_wrong.receipts["build-wrong"].subject_integrated_sha is None


class TestVerifyDocument:
    def test_verify_document_recomputes_digest(self) -> None:
        document = make_receipt()
        assert verify_document(document).outcome is AdmissionOutcome.ADMITTED
        document["receipt_id"] = "tampered-after-digest"
        decision = verify_document(document)
        assert decision.outcome is AdmissionOutcome.REJECTED

    def test_command_proven_pass_requires_all_three_facts(self) -> None:
        from contracts.execution_evidence import CommandEvidence

        def evidence(provenance: ExitProvenance, exit_code: int | None, report: str | None) -> CommandEvidence:
            return CommandEvidence(
                argv_digest="sha256:" + "2" * 64,
                exit_provenance=provenance,
                exit_code=exit_code,
                report_digest=report,
                working_directory=None,
                runner_identity=None,
                selected_test_ids=(),
            )

        assert evidence(ExitProvenance.EXIT_PROVEN, 0, "sha256:" + "3" * 64).proven_pass() is True
        assert evidence(ExitProvenance.EXIT_PROVEN, 1, "sha256:" + "3" * 64).proven_pass() is False
        assert evidence(ExitProvenance.EXIT_PROVEN, 0, None).proven_pass() is False
        assert evidence(ExitProvenance.WRAPPER_EXIT_ONLY, 0, "sha256:" + "3" * 64).proven_pass() is False


class TestCodexReviewTrancheRegressions:
    """Pins the exact-head review tranche findings on the evidence contract."""

    def test_input_evidence_set_digest_mismatch_is_rejected(self) -> None:
        document = independent_document(
            inputs={
                "receipt_refs": ["r-default"],
                "evidence_set_digest": evidence_set_digest(["different-receipt"]),
                "policy_revision": "v1",
            }
        )
        decision = admit_receipt(document)
        assert decision.outcome is AdmissionOutcome.REJECTED
        assert "INPUT_EVIDENCE_SET_DIGEST_MISMATCH" in decision.reasons

    def test_expired_receipts_are_demoted_to_stale(self) -> None:
        from datetime import UTC, datetime

        receipt_document = make_receipt(
            receipt_id="expiring",
            expires_at="2026-11-04T12:00:00Z",
            observed_at="2026-11-04T00:00:00Z",
        )
        graph = build_graph([receipt_document])
        report = derive_currentness(
            graph, CurrentIdentities(candidate_sha=C1), now=datetime(2026, 11, 4, 13, 0, tzinfo=UTC)
        )
        assert report.receipts["expiring"].status == "STALE"
        assert "EXPIRED" in report.receipts["expiring"].invalidated_by

    def test_not_yet_expired_receipt_stays_current(self) -> None:
        from datetime import UTC, datetime

        receipt_document = make_receipt(
            receipt_id="expiring-later",
            expires_at="2026-11-05T00:00:00Z",
            observed_at="2026-11-04T00:00:00Z",
        )
        graph = build_graph([receipt_document])
        report = derive_currentness(
            graph, CurrentIdentities(candidate_sha=C1), now=datetime(2026, 11, 4, 13, 0, tzinfo=UTC)
        )
        assert report.receipts["expiring-later"].status == "CURRENT"

    def test_declared_deployment_identity_participates_in_currentness(self) -> None:
        runtime = make_receipt(
            receipt_id="runtime-staging",
            receipt_kind="runtime_acceptance",
            producer={"system": "doctor", "principal": "doctor-1", "authority_class": "independent_verifier"},
            subject={
                "kind": "observed_runtime",
                "identity": "runtime-staging",
                "runtime_generation": GEN7,
                "artifact_digest": "sha256:" + "5" * 64,
                "deployment_ref": "deploy-staging",
            },
        )
        graph = build_graph([runtime])
        report = derive_currentness(
            graph,
            CurrentIdentities(
                runtime_generation=GEN7, artifact_digest="sha256:" + "5" * 64, deployment_identity="deploy-production"
            ),
        )
        assert report.receipts["runtime-staging"].status == "STALE"
        assert any(
            axis.value == "deployment_identity" for axis in report.receipts["runtime-staging"].stale_dependencies
        )

    def test_verification_input_staleness_propagates(self) -> None:
        stale_validation = make_receipt(
            receipt_id="validation-old", subject={"kind": "candidate_revision", "identity": "c1", "candidate_sha": C1}
        )
        verification = independent_document(
            inputs={
                "receipt_refs": ["validation-old"],
                "evidence_set_digest": evidence_set_digest(["validation-old"]),
                "policy_revision": "v1",
            }
        )
        graph = build_graph([stale_validation, verification])
        report = derive_currentness(graph, CurrentIdentities(candidate_sha=C2))
        assert report.receipts["validation-old"].status == "STALE"
        assert report.receipts["iv-1"].status == "STALE"

    def test_worker_plan_receipt_is_admissible_at_contract_level(self) -> None:
        document = make_receipt(
            receipt_id="plan-worker-ok",
            receipt_kind="plan_challenge",
            producer={"system": "worker", "principal": "worker-1", "authority_class": "worker_report"},
            subject={"kind": "planning_base", "identity": "brief-1", "planning_base_sha": BASE},
        )
        assert admit_receipt(document).outcome is AdmissionOutcome.ADMITTED


class TestRound5Regressions:
    """Round-5 review findings: input cycles and integrated-source fallback."""

    def test_verification_input_self_reference_is_rejected(self) -> None:
        self_ref = independent_document(
            inputs={
                "receipt_refs": ["iv-1"],
                "evidence_set_digest": evidence_set_digest(["iv-1"]),
                "policy_revision": "v1",
            }
        )
        with pytest.raises(ValueError, match="cycle"):
            build_graph([self_ref])

    def test_integration_without_subject_integrated_sha_binds_lineage_axis(self) -> None:
        document = integration_document(
            subject={"kind": "integrated_revision", "identity": "integrated-i1"},
        )
        decision = admit_receipt(document)
        assert decision.outcome is AdmissionOutcome.ADMITTED
        assert decision.receipt is not None
        graph = build_graph([document])
        report = derive_currentness(graph, CurrentIdentities(integrated_sha="f" * 40, candidate_sha=C1))
        assert report.receipts["int-1"].status == "STALE"
        assert any(axis.value == "integrated_source" for axis in report.receipts["int-1"].stale_dependencies)

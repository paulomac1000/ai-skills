"""Regression tests for the Autonomous Delivery Policy v1 (issue #94)."""

from __future__ import annotations

import pytest

from contracts.autonomous_delivery_policy import (
    BudgetConsumption,
    CapabilityReport,
    DeliveryDecisionKind,
    DeliveryPolicy,
    PlanningMode,
    PolicyTransition,
    ReviewerDescriptor,
    ReviewerIndependence,
    RiskLevel,
    RiskProfileName,
    TerminalBoundary,
    WorkKind,
    WorkSpec,
    admit_policy,
    authority_satisfies,  # noqa: F401  (re-export sanity for consumers)
    check_budgets,
    compile_gates,
    evaluate_delivery,
    evaluate_reviewer_independence,
    narrow_budget,
    policy_digest,
    resolve_effective_policy,
)
from contracts.execution_evidence import (
    AdmissionOutcome,
    AuthorityClass,
    CurrentIdentities,
    DependencyKind,
    GateRequirement,
    GateState,
    ReceiptKind,
    admit_receipt,
    build_graph,
    derive_currentness,
    evaluate_gate,
    evidence_set_digest,
    payload_digest,
)

C1 = "a" * 40
C2 = "b" * 40
I1 = "d" * 40
BASE = "e" * 40
GEN7 = "gen-7"
ARTIFACT = "sha256:" + "5" * 64


def policy_document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": 1,
        "policy_id": "delivery-default",
        "revision": "r1",
        "trust_binding": {
            "source_ref": "state://trusted/delivery-policy",
            "source_digest": "sha256:" + "1" * 64,
            "established_by": "operator",
        },
        "autonomy": {"maximum_level": "release"},
        "work_kinds": {
            "INVESTIGATION": {
                "terminal_boundary": "evidence_backed_findings",
                "requires_pr": False,
                "requires_release": False,
                "risk_profile": "quick",
                "planning_mode_override": "none",
                "review_required_override": False,
                "verification_required_override": False,
                "integration_enabled_override": False,
                "release_enabled_override": False,
            },
            "IMPLEMENTATION": {
                "terminal_boundary": "runtime_accepted",
                "requires_pr": True,
                "requires_release": True,
                "requires_operator_grant": False,
            },
            "OPERATOR_ACTION": {
                "terminal_boundary": "implementation_completed",
                "requires_operator_grant": True,
                "risk_profile": "standard",
            },
            "COORDINATION": {"terminal_boundary": "decomposition_required"},
        },
        "risk_profiles": {
            "quick": {
                "maps_risk_level": "LOW",
                "verification_layers": ["static", "unit"],
                "reviewer_count": 0,
                "independent_verification_required": False,
            },
            "standard": {
                "maps_risk_level": "MEDIUM",
                "verification_layers": ["static", "unit", "integration", "exact_artifact"],
                "reviewer_count": 1,
                "independent_verification_required": False,
            },
            "deep": {
                "maps_risk_level": "HIGH",
                "verification_layers": [
                    "static",
                    "unit",
                    "integration",
                    "exact_artifact",
                    "security_review",
                    "semantic_review",
                ],
                "reviewer_count": 1,
                "independent_verification_required": True,
                "focus_areas": ["auth", "state_machines"],
            },
        },
        "planning": {
            "mode": "independent_challenge",
            "challenge_class": "review_provider",
            "max_revision_rounds": 3,
            "stale_on": ["planning_base_change", "task_brief_change"],
        },
        "review": {
            "required": True,
            "reviewer_class": "semantic_independent",
            "count": 1,
            "required_dimensions": ["model", "organization"],
            "upstream_attestation_required": True,
            "rubric_ref": "rubric://trusted/v1",
            "stale_on_candidate_change": True,
            "final_exact_head_required": True,
        },
        "independent_verification": {"required": False},
        "integration": {"enabled": True, "integration_lease_required": True, "allowed_strategies": ["squash"]},
        "integrated_acceptance": {"required": True, "required_before": ["release_publication", "deployment"]},
        "release": {"enabled": True, "deployment_lease_required": True, "rollback_required": True},
        "review_convergence": {"max_repair_rounds": 4, "final_full_review_required": True},
        "budgets": {"plan_revision_rounds": 3, "repair_rounds": 4, "outer_retry_budget": 8},
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
        "policy": {"policy_ref": "policy://delivery-default", "policy_digest": "sha256:" + "2" * 64},
        "outcome": {"disposition": "PASS"},
        "evidence_refs": [],
        "artifact_refs": [],
        "observed_at": "2026-11-04T00:00:00Z",
    }
    document.update(overrides)
    document["payload_digest"] = payload_digest(document)
    return document


def full_implementation_graph(**overrides: object) -> object:
    documents = [
        receipt(
            receipt_id="plan-1",
            receipt_kind="plan_challenge",
            producer={"system": "chatgpt", "principal": "challenge-1", "authority_class": "review_provider"},
            subject={"kind": "planning_base", "identity": "plan-brief-1", "planning_base_sha": BASE},
            depends_on=[{"receipt_id": "plan-1-self", "dependency_kind": "planning_base"}],
        ),
        receipt(receipt_id="validation-1"),
        receipt(
            receipt_id="review-1",
            receipt_kind="review",
            producer={"system": "chatgpt", "principal": "reviewer-1", "authority_class": "review_provider"},
            subject={"kind": "candidate_revision", "identity": "candidate-c1", "candidate_sha": C1},
        ),
        receipt(
            receipt_id="verification-1",
            receipt_kind="independent_verification",
            producer={"system": "verifier", "principal": "verifier-1", "authority_class": "independent_verifier"},
            implementation_provenance={"provenance_state": "known", "principal_ref": "worker-1"},
            inputs={
                "receipt_refs": ["validation-1"],
                "evidence_set_digest": evidence_set_digest(["validation-1"]),
                "policy_revision": "r1",
            },
        ),
        receipt(
            receipt_id="integration-1",
            receipt_kind="integration",
            producer={"system": "github", "principal": "provider", "authority_class": "external_provider_observation"},
            subject={"kind": "integrated_revision", "identity": "integrated-i1", "integrated_sha": I1},
            mutation_authority={
                "authority_kind": "integration_lease",
                "authority_ref": "lease://1",
                "consumption_ref": "op://1",
            },
            lineage={
                "strategy": "squash",
                "candidate_sha": C1,
                "target_ref": "refs/heads/main",
                "target_before_sha": BASE,
                "integrated_sha": I1,
                "integrated_tree_sha": "c" * 40,
                "lineage_proof_ref": "audit://op-1",
                "lease_ref": "lease://1",
                "operation_ref": "op://1",
            },
        ),
        receipt(
            receipt_id="integrated-validation-1",
            receipt_kind="validation",
            producer={"system": "ci", "principal": "runner-1", "authority_class": "deterministic_tool"},
            subject={"kind": "integrated_revision", "identity": "integrated-i1", "integrated_sha": I1},
        ),
        receipt(
            receipt_id="release-1",
            receipt_kind="artifact_publication",
            producer={
                "system": "github-releases",
                "principal": "release-bot",
                "authority_class": "external_provider_observation",
            },
            subject={
                "kind": "publication",
                "identity": "ai-skills-3.34.0",
                "integrated_sha": I1,
                "artifact_digest": ARTIFACT,
            },
        ),
        receipt(
            receipt_id="runtime-1",
            receipt_kind="runtime_acceptance",
            producer={"system": "doctor", "principal": "doctor-1", "authority_class": "independent_verifier"},
            subject={
                "kind": "observed_runtime",
                "identity": "runtime-fedora",
                "runtime_generation": GEN7,
                "artifact_digest": ARTIFACT,
            },
        ),
    ]
    documents.extend(overrides)  # type: ignore[arg-type]
    return build_graph(documents)


IMPL_SPEC = WorkSpec(
    work_kind=WorkKind.IMPLEMENTATION,
    change_risk=RiskLevel.HIGH,
    expected_policy_revision="r1",
    planning_base_sha=BASE,
)
DOCS_SPEC = WorkSpec(work_kind=WorkKind.INVESTIGATION, change_risk=RiskLevel.LOW, expected_policy_revision="r1")


class TestPolicyAdmission:
    def test_valid_policy_admits(self) -> None:
        policy, reasons = admit_policy(policy_document())
        assert policy is not None
        assert reasons == ()

    def test_digest_tampering_rejected(self) -> None:
        document = policy_document()
        document["revision"] = "tampered"
        policy, reasons = admit_policy(document)
        assert policy is None
        assert "POLICY_DIGEST_MISMATCH" in reasons

    def test_missing_trust_binding_rejected(self) -> None:
        document = policy_document()
        del document["trust_binding"]
        document["digest"] = policy_digest(document)
        policy, _reasons = admit_policy(document)
        assert policy is None


class TestGateCompilation:
    def test_investigation_may_complete_without_pr_or_release(self) -> None:
        compiled = compile_gates(load_policy(), DOCS_SPEC)
        assert compiled.terminal_boundary is TerminalBoundary.EVIDENCE_BACKED_FINDINGS
        assert not compiled.integration_required
        assert not compiled.release_required
        assert not compiled.review_required
        assert not compiled.validation_required

    def test_high_risk_always_compiles_to_deep_profile(self) -> None:
        compiled = compile_gates(load_policy(), IMPL_SPEC)
        assert compiled.risk_profile.name is RiskProfileName.DEEP
        assert compiled.verification_required is True

    def test_low_risk_uses_quick_profile_without_expensive_panel(self) -> None:
        compiled = compile_gates(load_policy(), DOCS_SPEC)
        assert compiled.risk_profile.name is RiskProfileName.QUICK
        assert compiled.risk_profile.reviewer_count == 0

    def test_operator_action_requires_grant_without_inheritance(self) -> None:
        spec = WorkSpec(work_kind=WorkKind.OPERATOR_ACTION, change_risk=RiskLevel.MEDIUM, expected_policy_revision="r1")
        compiled = compile_gates(load_policy(), spec)
        assert compiled.operator_grant_required is True

    def test_coordination_cannot_pretend_atomic_implementation(self) -> None:
        spec = WorkSpec(work_kind=WorkKind.COORDINATION, change_risk=RiskLevel.LOW, expected_policy_revision="r1")
        compiled = compile_gates(load_policy(), spec)
        assert compiled.decomposition_required is True

    def test_implement_only_autonomy_blocks_integration_authorization(self) -> None:
        document = policy_document(autonomy={"maximum_level": "implement_only"})
        document["digest"] = policy_digest(document)
        admitted, _ = admit_policy(document)
        assert admitted is not None
        compiled = compile_gates(admitted, IMPL_SPEC)
        assert compiled.integration_required is True
        assert compiled.integration_authorized is False


class TestAntiSelfApproval:
    def _candidate(self, **overrides: object) -> DeliveryPolicy:
        admitted, _ = admit_policy(policy_document(**overrides))
        assert admitted is not None
        return admitted

    WEAKENING_CASES: tuple[tuple[dict[str, object], dict[str, object], str], ...] = (
        ({}, {"review": {"required": False, "count": 0}}, "review.required"),
        (
            {"independent_verification": {"required": True}},
            {"independent_verification": {"required": False}},
            "independent_verification.required",
        ),
        (
            {"integration": {"enabled": False, "integration_lease_required": True}},
            {"integration": {"enabled": True, "integration_lease_required": True}},
            "integration.enabled",
        ),
        (
            {},
            {"review": {"rubric_ref": "rubric://candidate/weaker", "required": True, "count": 1}},
            "review.rubric_ref",
        ),
        (
            {"autonomy": {"maximum_level": "implement_only"}},
            {"autonomy": {"maximum_level": "release"}},
            "autonomy.maximum_level",
        ),
        (
            {"release": {"enabled": False, "rollback_required": True, "deployment_lease_required": True}},
            {"release": {"enabled": True, "rollback_required": True, "deployment_lease_required": True}},
            "release.enabled",
        ),
        (
            {"release": {"enabled": True, "rollback_required": True, "deployment_lease_required": True}},
            {"release": {"enabled": True, "rollback_required": False, "deployment_lease_required": True}},
            "release.rollback_required",
        ),
        (
            {
                "planning": {
                    "mode": "independent_challenge",
                    "challenge_class": "review_provider",
                    "max_revision_rounds": 3,
                }
            },
            {"planning": {"mode": "none"}},
            "planning.mode",
        ),
    )

    @pytest.mark.parametrize(("trusted_overrides", "candidate_overrides", "expected_axis"), list(WEAKENING_CASES))
    def test_weakening_transitions_fail_closed(
        self, trusted_overrides: dict[str, object], candidate_overrides: dict[str, object], expected_axis: str
    ) -> None:
        trusted = load_policy(**trusted_overrides)
        candidate = self._candidate(**candidate_overrides)
        decision = resolve_effective_policy(trusted, candidate, None)
        assert decision.outcome == "POLICY_SELF_MODIFICATION_BLOCKED"
        assert decision.policy is trusted
        assert decision.weakenings
        assert any(weak.startswith(expected_axis) for weak in decision.weakenings)

    def test_governed_operator_transition_may_apply(self) -> None:
        trusted = load_policy()
        candidate = self._candidate(review={"required": False, "count": 0})
        transition = PolicyTransition(
            authorized_by="operator",
            authority_class=AuthorityClass.OPERATOR,
            transition_ref="policy-transition://1",
            covers_policy_digest=candidate.digest,
        )
        decision = resolve_effective_policy(trusted, candidate, transition)
        assert decision.outcome == "GOVERNED_TRANSITION_APPLIED"
        assert decision.policy is candidate

    def test_non_operator_transition_authority_is_insufficient(self) -> None:
        trusted = load_policy()
        candidate = self._candidate(review={"required": False, "count": 0})
        transition = PolicyTransition(
            authorized_by="worker",
            authority_class=AuthorityClass.WORKER_REPORT,
            transition_ref="policy-transition://2",
            covers_policy_digest=candidate.digest,
        )
        decision = resolve_effective_policy(trusted, candidate, transition)
        assert decision.outcome == "TRANSITION_AUTHORITY_INSUFFICIENT"

    def test_transition_not_covering_candidate_is_rejected(self) -> None:
        trusted = load_policy()
        candidate = self._candidate(review={"required": False, "count": 0})
        transition = PolicyTransition(
            authorized_by="operator",
            authority_class=AuthorityClass.OPERATOR,
            transition_ref="policy-transition://3",
            covers_policy_digest="sha256:" + "9" * 64,
        )
        decision = resolve_effective_policy(trusted, candidate, transition)
        assert decision.outcome == "TRANSITION_DOES_NOT_COVER_CANDIDATE"


class TestDeliveryEvaluation:
    def test_low_risk_investigation_terminates_on_findings(self) -> None:
        policy = load_policy()
        graph = build_graph(
            [
                receipt(
                    receipt_id="findings-1",
                    receipt_kind="work_completion",
                    producer={"system": "worker", "principal": "worker-1", "authority_class": "worker_report"},
                    subject={"kind": "terminal_evidence", "identity": "investigation-findings"},
                ),
            ]
        )
        decision = evaluate_delivery(policy, DOCS_SPEC, graph)
        assert decision.outcome is DeliveryDecisionKind.TERMINAL_ACCEPTED
        assert decision.terminal_boundary is TerminalBoundary.EVIDENCE_BACKED_FINDINGS

    def test_full_implementation_chain_reaches_runtime_accepted(self) -> None:
        policy = load_policy()
        graph = full_implementation_graph()
        reviewers = [
            ReviewerDescriptor(
                principal="reviewer-1",
                model="m1",
                organization="o1",
                account="acc-1",
                transport="api",
                upstream_id="u1",
                upstream_attested=True,
            )
        ]
        decision = evaluate_delivery(
            policy,
            IMPL_SPEC,
            graph,
            current=CurrentIdentities(
                candidate_sha=C1, integrated_sha=I1, runtime_generation=GEN7, artifact_digest=ARTIFACT
            ),
            reviewers=reviewers,
        )
        assert decision.outcome is DeliveryDecisionKind.TERMINAL_ACCEPTED, decision.reasons

    def test_missing_required_review_is_not_terminal(self) -> None:
        policy = load_policy()
        graph = full_implementation_graph()
        # remove the review receipt from a fresh graph
        documents = [document for document in graph.documents.values() if document["receipt_id"] != "review-1"]  # type: ignore[index]
        rebuilt = build_graph(documents)
        decision = evaluate_delivery(
            policy,
            IMPL_SPEC,
            rebuilt,
            current=CurrentIdentities(
                candidate_sha=C1, integrated_sha=I1, runtime_generation=GEN7, artifact_digest=ARTIFACT
            ),
        )
        assert decision.outcome is DeliveryDecisionKind.WAITING_REQUIRED_EVIDENCE
        assert "review" in decision.missing_gates

    def test_worker_all_green_report_is_never_terminal(self) -> None:
        policy = load_policy()
        graph = build_graph(
            [
                receipt(
                    receipt_id="worker-claim",
                    receipt_kind="implementation",
                    producer={"system": "worker", "principal": "worker-1", "authority_class": "worker_report"},
                    outcome={"disposition": "PASS", "reason_codes": ["ALL_GREEN"]},
                ),
            ]
        )
        decision = evaluate_delivery(policy, IMPL_SPEC, graph)
        assert decision.outcome is not DeliveryDecisionKind.TERMINAL_ACCEPTED

    def test_stale_policy_reference_is_detected(self) -> None:
        policy = load_policy()
        spec = WorkSpec(work_kind=WorkKind.INVESTIGATION, change_risk=RiskLevel.LOW, expected_policy_revision="r0")
        decision = evaluate_delivery(policy, spec, build_graph([]))
        assert decision.outcome is DeliveryDecisionKind.POLICY_STALE

    def test_unavailable_reviewer_is_typed_blocker_not_pass(self) -> None:
        policy = load_policy()
        graph = full_implementation_graph()
        decision = evaluate_delivery(
            policy,
            IMPL_SPEC,
            graph,
            current=CurrentIdentities(
                candidate_sha=C1, integrated_sha=I1, runtime_generation=GEN7, artifact_digest=ARTIFACT
            ),
            capabilities=CapabilityReport({"review_provider": "quota"}),
        )
        assert decision.outcome is DeliveryDecisionKind.REQUIRED_CAPABILITY_UNAVAILABLE

    def test_zero_step_hosted_ci_is_not_validation_pass(self) -> None:
        policy = load_policy()
        graph = build_graph(
            [
                receipt(
                    receipt_id="hosted-1",
                    receipt_kind="command_execution",
                    producer={
                        "system": "github-actions",
                        "principal": "actions",
                        "authority_class": "deterministic_tool",
                    },
                    outcome={"disposition": "NOT_OBSERVED", "reason_codes": ["HOSTED_NOT_EXECUTED"]},
                    command_evidence={"argv_digest": "sha256:" + "3" * 64, "exit_provenance": "EXIT_UNPROVEN"},
                ),
            ]
        )
        decision = evaluate_delivery(policy, IMPL_SPEC, graph)
        assert decision.outcome is not DeliveryDecisionKind.TERMINAL_ACCEPTED
        assert "validation" in decision.missing_gates

    def test_local_substitute_cannot_self_authorize_hosted_gate(self) -> None:
        """A local PASS satisfies the deterministic gate only; the hosted
        substitute authorization is owned by the external-gate deviation
        contract and never minted by this evaluator."""
        policy = load_policy()
        graph = build_graph(
            [
                receipt(receipt_id="local-1"),
            ]
        )
        decision = evaluate_delivery(policy, IMPL_SPEC, graph)
        # The deterministic validation gate may be satisfied by a local
        # authorized run, but the remaining required hosted/integration gates
        # keep the delivery non-terminal.
        assert decision.gate_decisions["validation"].state.value == "SATISFIED"
        assert decision.outcome is not DeliveryDecisionKind.TERMINAL_ACCEPTED

    def test_earlier_green_never_compensates_missing_later_stage(self) -> None:
        policy = load_policy()
        graph = build_graph(
            [
                receipt(receipt_id="validation-1"),
                receipt(
                    receipt_id="review-1",
                    receipt_kind="review",
                    producer={"system": "chatgpt", "principal": "reviewer-1", "authority_class": "review_provider"},
                    subject={"kind": "candidate_revision", "identity": "candidate-c1", "candidate_sha": C1},
                ),
            ]
        )
        decision = evaluate_delivery(policy, IMPL_SPEC, graph)
        assert decision.gate_decisions["validation"].is_green
        assert not decision.gate_decisions["integration"].is_green
        assert decision.outcome is DeliveryDecisionKind.WAITING_REQUIRED_EVIDENCE

    def test_seven_of_eight_criteria_is_not_complete(self) -> None:
        policy = load_policy()
        graph = full_implementation_graph()
        documents = [document for document in graph.documents.values() if document["receipt_id"] != "runtime-1"]  # type: ignore[index]
        rebuilt = build_graph(documents)
        decision = evaluate_delivery(
            policy,
            IMPL_SPEC,
            rebuilt,
            current=CurrentIdentities(
                candidate_sha=C1, integrated_sha=I1, runtime_generation=GEN7, artifact_digest=ARTIFACT
            ),
        )
        assert decision.outcome is DeliveryDecisionKind.WAITING_REQUIRED_EVIDENCE
        assert "runtime_acceptance" in decision.missing_gates

    def test_coordination_yields_decomposition_not_completion(self) -> None:
        policy = load_policy()
        spec = WorkSpec(work_kind=WorkKind.COORDINATION, change_risk=RiskLevel.LOW, expected_policy_revision="r1")
        decision = evaluate_delivery(policy, spec, build_graph([]))
        assert decision.outcome is not DeliveryDecisionKind.TERMINAL_ACCEPTED
        assert decision.terminal_boundary is TerminalBoundary.DECOMPOSITION_REQUIRED

    def test_operator_action_requires_exact_grant(self) -> None:
        policy = load_policy()
        spec = WorkSpec(work_kind=WorkKind.OPERATOR_ACTION, change_risk=RiskLevel.MEDIUM, expected_policy_revision="r1")
        graph = build_graph(
            [
                receipt(
                    receipt_id="grant-1",
                    receipt_kind="capability_admission",
                    producer={"system": "control-plane", "principal": "operator", "authority_class": "operator"},
                    subject={"kind": "gate", "identity": "root-install"},
                ),
            ]
        )
        decision = evaluate_delivery(policy, spec, graph)
        assert decision.gate_decisions["operator_grant"].is_green


class TestPlanGate:
    def test_worker_reported_challenge_is_rejected_at_admission(self) -> None:
        worker_plan = receipt(
            receipt_id="plan-worker",
            receipt_kind="plan_challenge",
            producer={"system": "worker", "principal": "worker-1", "authority_class": "worker_report"},
            subject={"kind": "planning_base", "identity": "brief-1", "planning_base_sha": BASE},
        )
        with pytest.raises(ValueError, match="AUTHORITY_FLOOR_UNMET"):
            build_graph([worker_plan])

    def test_worker_cannot_self_accept_independent_challenge(self) -> None:
        policy = load_policy()
        same_principal = receipt(
            receipt_id="plan-self",
            receipt_kind="plan_challenge",
            producer={"system": "worker", "principal": "worker-1", "authority_class": "review_provider"},
            subject={"kind": "planning_base", "identity": "brief-1", "planning_base_sha": BASE},
        )
        implementation = receipt(
            receipt_id="impl-1",
            receipt_kind="implementation",
            producer={"system": "worker", "principal": "worker-1", "authority_class": "worker_report"},
            outcome={"disposition": "PASS"},
        )
        graph = build_graph([same_principal, implementation])
        decision = evaluate_delivery(policy, IMPL_SPEC, graph)
        assert not decision.gate_decisions["plan"].is_green
        assert "CHALLENGER_NOT_INDEPENDENT" in decision.gate_decisions["plan"].reasons

    def test_plan_stale_after_planning_base_change(self) -> None:
        policy = load_policy()
        graph = full_implementation_graph()
        moved_base = CurrentIdentities(
            candidate_sha=C1,
            planning_base_sha="f" * 40,
            integrated_sha=I1,
            runtime_generation=GEN7,
            artifact_digest=ARTIFACT,
        )
        decision = evaluate_delivery(policy, IMPL_SPEC, graph, current=moved_base)
        assert decision.outcome is DeliveryDecisionKind.PLAN_STALE

    def test_plan_revise_disposition_is_typed(self) -> None:
        policy = load_policy()
        graph = full_implementation_graph()
        decision = evaluate_delivery(policy, IMPL_SPEC, graph, plan_disposition="PLAN_REVISE")
        assert decision.outcome is DeliveryDecisionKind.PLAN_REVISE

    def test_planning_mode_none_needs_no_plan(self) -> None:
        policy = load_policy(planning={"mode": "none"})
        compiled = compile_gates(policy, DOCS_SPEC)
        assert compiled.planning_mode is PlanningMode.NONE


class TestReviewerIndependence:
    def test_shared_unattested_upstream_is_not_two_reviewers(self) -> None:
        reviewers = [
            ReviewerDescriptor(
                principal="alias-a",
                model="m1",
                organization="o1",
                account="acc-1",
                transport="api",
                upstream_id="shared",
                upstream_attested=False,
            ),
            ReviewerDescriptor(
                principal="alias-b",
                model="m1",
                organization="o1",
                account="acc-2",
                transport="api",
                upstream_id="shared",
                upstream_attested=False,
            ),
        ]
        report = evaluate_reviewer_independence(
            reviewers, ("model", "organization"), upstream_attestation_required=True
        )
        assert report.qualified_count == 0
        assert all(state is ReviewerIndependence.UNATTESTED_UPSTREAM for state in report.per_reviewer.values())

    def test_attested_distinct_providers_qualify(self) -> None:
        reviewers = [
            ReviewerDescriptor(
                principal="r1",
                model="m1",
                organization="o1",
                account="acc-1",
                transport="api",
                upstream_id="u1",
                upstream_attested=True,
            ),
            ReviewerDescriptor(
                principal="r2",
                model="m2",
                organization="o2",
                account="acc-2",
                transport="api",
                upstream_id="u2",
                upstream_attested=True,
            ),
        ]
        report = evaluate_reviewer_independence(
            reviewers, ("model", "organization"), upstream_attestation_required=True
        )
        assert report.qualified_count == 2

    def test_unknown_upstream_is_unknown_not_independence(self) -> None:
        reviewers = [
            ReviewerDescriptor(
                principal="r1",
                model="m1",
                organization="o1",
                account="acc-1",
                transport="api",
                upstream_id=None,
                upstream_attested=False,
            ),
        ]
        report = evaluate_reviewer_independence(
            reviewers, ("model", "organization"), upstream_attestation_required=True
        )
        assert report.qualified_count == 0


class TestBudgets:
    def test_budget_exhaustion_is_typed_not_pass(self) -> None:
        policy = load_policy()
        decision = evaluate_delivery(
            policy, IMPL_SPEC, build_graph([]), budget_consumed=BudgetConsumption(repair_rounds=5, outer_retry_used=1)
        )
        assert decision.outcome is DeliveryDecisionKind.REPAIR_BUDGET_EXHAUSTED
        assert not decision.is_green

    def test_child_cannot_enlarge_outer_budget(self) -> None:
        violations = narrow_budget(
            child=BudgetConsumption(outer_retry_used=10),
            parent=BudgetConsumption(outer_retry_used=8),
        )
        assert "CHILD_ENLARGED_OUTER_RETRY_BUDGET" in violations

    def test_child_may_narrow_budget(self) -> None:
        assert (
            narrow_budget(
                child=BudgetConsumption(outer_retry_used=3, repair_rounds=1),
                parent=BudgetConsumption(outer_retry_used=8, repair_rounds=4),
            )
            == ()
        )

    def test_within_budget_is_clean(self) -> None:
        assert check_budgets(load_policy(), BudgetConsumption(repair_rounds=4, outer_retry_used=8)) == ()


class TestReceiptAdmissionComposition:
    def test_admitted_policy_digest_matches_document(self) -> None:
        document = policy_document()
        policy, _ = admit_policy(document)
        assert policy is not None
        assert policy.digest == document["digest"]

    def test_full_graph_receipts_are_admitted(self) -> None:
        graph = full_implementation_graph()
        assert len(graph.receipts) >= 8
        assert all(
            admit_receipt(document).outcome is AdmissionOutcome.ADMITTED for document in graph.documents.values()
        )


class TestReviewConvergenceRegressions:
    """Regression tests for the exact-SHA review findings (C1 review round)."""

    def _policy_without_plan_receipt(self) -> object:
        policy = load_policy()
        graph = full_implementation_graph()
        documents = [document for document in graph.documents.values() if document["receipt_id"] != "plan-1"]  # type: ignore[index]
        return policy, build_graph(documents)

    def test_missing_plan_receipt_blocks_terminal_acceptance(self) -> None:
        """Finding 1: the planning gate participates in missing accounting."""
        policy, graph = self._policy_without_plan_receipt()
        reviewers = [
            ReviewerDescriptor(
                principal="reviewer-1",
                model="m1",
                organization="o1",
                account="acc-1",
                transport="api",
                upstream_id="u1",
                upstream_attested=True,
            )
        ]
        decision = evaluate_delivery(
            policy,
            IMPL_SPEC,
            graph,
            current=CurrentIdentities(
                candidate_sha=C1, integrated_sha=I1, runtime_generation=GEN7, artifact_digest=ARTIFACT
            ),
            reviewers=reviewers,
        )
        assert decision.outcome is not DeliveryDecisionKind.TERMINAL_ACCEPTED
        assert "plan" in decision.missing_gates

    def test_reviewer_independence_enforced_on_review_gate(self) -> None:
        """Finding 2: distinct principals sharing one unattested upstream never pass."""
        policy = load_policy()
        alias_a = receipt(
            receipt_id="review-a",
            receipt_kind="review",
            producer={"system": "chatgpt", "principal": "alias-a", "authority_class": "review_provider"},
            subject={"kind": "candidate_revision", "identity": "candidate-c1", "candidate_sha": C1},
        )
        alias_b = receipt(
            receipt_id="review-b",
            receipt_kind="review",
            producer={"system": "codex", "principal": "alias-b", "authority_class": "review_provider"},
            subject={"kind": "candidate_revision", "identity": "candidate-c1", "candidate_sha": C1},
        )
        graph = build_graph([alias_a, alias_b])
        reviewers = [
            ReviewerDescriptor(
                principal="alias-a",
                model="m1",
                organization="o1",
                account="a1",
                transport="api",
                upstream_id="shared",
                upstream_attested=False,
            ),
            ReviewerDescriptor(
                principal="alias-b",
                model="m1",
                organization="o1",
                account="a2",
                transport="api",
                upstream_id="shared",
                upstream_attested=False,
            ),
        ]
        decision = evaluate_delivery(
            policy, IMPL_SPEC, graph, current=CurrentIdentities(candidate_sha=C1), reviewers=reviewers
        )
        assert decision.gate_decisions["review"].state is not GateState.SATISFIED
        assert any(
            reason.startswith("INDEPENDENCE_UNQUALIFIED") or reason.startswith("INDEPENDENCE_QUALIFIED_COUNT")
            for reason in decision.gate_decisions["review"].reasons
        )

    def test_self_declared_not_required_cannot_satisfy_required_gate(self) -> None:
        """Finding 3: a receipt's own policy metadata never authorizes an exemption."""
        not_required = receipt(
            receipt_id="review-nr",
            receipt_kind="review",
            producer={"system": "chatgpt", "principal": "rev-1", "authority_class": "review_provider"},
            subject={"kind": "candidate_revision", "identity": "candidate-c1", "candidate_sha": C1},
            outcome={"disposition": "NOT_REQUIRED"},
            policy={"policy_ref": "policy://p", "policy_revision": "self-declared"},
        )
        decision = admit_receipt(not_required)
        assert decision.outcome is AdmissionOutcome.ADMITTED
        graph = build_graph([not_required])
        gate = evaluate_gate(
            graph,
            GateRequirement(gate_id="review", required_kind=ReceiptKind.REVIEW),
        )
        assert gate.state is not GateState.SATISFIED
        assert any(reason.startswith("NOT_REQUIRED_UNAUTHORIZED") for reason in gate.reasons)

    def test_work_kind_override_weakening_is_blocked(self) -> None:
        """Finding 4: per-kind overrides are compared at effective-gate level."""
        trusted = load_policy()

        document = policy_document()
        work_kinds = dict(document["work_kinds"])  # type: ignore[arg-type]
        impl = dict(work_kinds["IMPLEMENTATION"])  # type: ignore[index]
        impl["review_required_override"] = False
        work_kinds["IMPLEMENTATION"] = impl
        document["work_kinds"] = work_kinds
        document["digest"] = policy_digest(document)
        admitted, _ = admit_policy(document)
        assert admitted is not None
        decision = resolve_effective_policy(trusted, admitted, None)
        assert decision.outcome == "POLICY_SELF_MODIFICATION_BLOCKED"
        assert any(w.startswith("work_kinds.IMPLEMENTATION.review_required") for w in decision.weakenings)

    def test_missing_candidate_binding_cannot_satisfy_exact_head_review(self) -> None:
        """Finding 6: an unbound review receipt never qualifies for exact-head review."""
        unbound = receipt(
            receipt_id="review-unbound",
            receipt_kind="review",
            producer={"system": "chatgpt", "principal": "rev-1", "authority_class": "review_provider"},
            subject={"kind": "candidate_revision", "identity": "some-candidate"},
        )
        graph = build_graph([unbound])
        report = derive_currentness(graph, CurrentIdentities(candidate_sha=C1))
        gate = evaluate_gate(
            graph,
            GateRequirement(
                gate_id="review",
                required_kind=ReceiptKind.REVIEW,
                required_identity_axes=(DependencyKind.CANDIDATE_SOURCE,),
            ),
            report,
        )
        assert gate.state is not GateState.SATISFIED
        assert any(reason.startswith("MISSING_IDENTITY_AXIS") for reason in gate.reasons)


class TestCurrentnessOrderIndependence:
    def test_staleness_propagation_is_independent_of_insertion_order(self) -> None:
        """Finding 5: same graph, same identities, any permutation -> same result."""
        upstream = receipt(
            receipt_id="base-validation",
            subject={"kind": "candidate_revision", "identity": "candidate-c1", "candidate_sha": C1},
        )
        dependent = receipt(
            receipt_id="dependent",
            depends_on=[{"receipt_id": "base-validation", "dependency_kind": "candidate_source"}],
            subject={"kind": "candidate_revision", "identity": "candidate-c2", "candidate_sha": C2},
        )
        forward = derive_currentness(build_graph([upstream, dependent]), CurrentIdentities(candidate_sha=C2))
        reverse = derive_currentness(build_graph([dependent, upstream]), CurrentIdentities(candidate_sha=C2))
        assert forward.receipts["base-validation"].status == "STALE"
        assert reverse.receipts["base-validation"].status == "STALE"
        assert forward.receipts["dependent"].status == reverse.receipts["dependent"].status
        assert forward.receipts["dependent"].status == "STALE"
        assert sorted(forward.minimum_revalidation) == sorted(reverse.minimum_revalidation)


class TestRound2Regressions:
    """Round-2 review findings: per-kind profile selection and planning override."""

    def test_risk_profile_substitution_is_blocked(self) -> None:
        """Candidate pins IMPLEMENTATION risk_profile=quick while profiles unchanged."""
        trusted = load_policy()
        document = policy_document()
        work_kinds = dict(document["work_kinds"])  # type: ignore[arg-type]
        impl = dict(work_kinds["IMPLEMENTATION"])  # type: ignore[index]
        impl["risk_profile"] = "quick"
        work_kinds["IMPLEMENTATION"] = impl
        document["work_kinds"] = work_kinds
        document["digest"] = policy_digest(document)
        candidate, _ = admit_policy(document)
        assert candidate is not None
        decision = resolve_effective_policy(trusted, candidate, None)
        assert decision.outcome == "POLICY_SELF_MODIFICATION_BLOCKED"
        assert any("profile:deep->quick" in weakening for weakening in decision.weakenings)

    def test_work_kind_planning_override_eliminating_challenge_is_blocked(self) -> None:
        """Candidate sets IMPLEMENTATION planning_mode_override=none under a
        global independent_challenge policy without a governed transition."""
        trusted = load_policy()
        document = policy_document()
        work_kinds = dict(document["work_kinds"])  # type: ignore[arg-type]
        impl = dict(work_kinds["IMPLEMENTATION"])  # type: ignore[index]
        impl["planning_mode_override"] = "none"
        work_kinds["IMPLEMENTATION"] = impl
        document["work_kinds"] = work_kinds
        document["digest"] = policy_digest(document)
        candidate, _ = admit_policy(document)
        assert candidate is not None
        decision = resolve_effective_policy(trusted, candidate, None)
        assert decision.outcome == "POLICY_SELF_MODIFICATION_BLOCKED"
        assert any("planning:independent_challenge->none" in weakening for weakening in decision.weakenings)


class TestRound3Regressions:
    """Round-3 review finding: budget enlargement must be classified as weakening."""

    def test_budget_enlargement_without_transition_is_blocked(self) -> None:
        trusted = load_policy()
        document = policy_document()
        document["budgets"] = {"plan_revision_rounds": 3, "repair_rounds": 100, "outer_retry_budget": 100}
        document["digest"] = policy_digest(document)
        candidate, _ = admit_policy(document)
        assert candidate is not None
        decision = resolve_effective_policy(trusted, candidate, None)
        assert decision.outcome == "POLICY_SELF_MODIFICATION_BLOCKED"
        assert any(weakening.startswith("budgets.repair_rounds") for weakening in decision.weakenings)
        assert any(weakening.startswith("budgets.outer_retry_budget") for weakening in decision.weakenings)

    def test_budget_reduction_remains_permitted(self) -> None:
        trusted = load_policy()
        document = policy_document()
        document["budgets"] = {"plan_revision_rounds": 1, "repair_rounds": 2, "outer_retry_budget": 4}
        document["digest"] = policy_digest(document)
        candidate, _ = admit_policy(document)
        assert candidate is not None
        decision = resolve_effective_policy(trusted, candidate, None)
        assert decision.outcome == "CANDIDATE_COMPATIBLE"
        assert not any(weakening.startswith("budgets.") for weakening in decision.weakenings)

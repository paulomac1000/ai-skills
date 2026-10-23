"""Dependency-aware cost-ordered verification scheduling regressions.

Every scenario exercises the public planner path, not private helpers, so a
mutation that disables invalidation, preflight, or the final-gate restriction
makes the corresponding regression fail.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills/qa-change-verifier/tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import verification_schedule as schedule  # noqa: E402

CostClass = schedule.CostClass
DiscriminationClass = schedule.DiscriminationClass
DurationProfile = schedule.DurationProfile
EvidenceKind = schedule.EvidenceKind
EvidenceReceipt = schedule.EvidenceReceipt
FailureSubject = schedule.FailureSubject
ProbeValidity = schedule.ProbeValidity
ReleaseWorktreeState = schedule.ReleaseWorktreeState
ScheduleDecision = schedule.ScheduleDecision
SchedulePolicy = schedule.SchedulePolicy
ScheduleReason = schedule.ScheduleReason
TrustedEvidenceSnapshot = schedule.TrustedEvidenceSnapshot
VerificationNode = schedule.VerificationNode

CANDIDATE_A = "a" * 40
CANDIDATE_B = "b" * 40
BASE_X = "1" * 40
BASE_Y = "2" * 40
CONTRACT = "sha256:" + "c" * 64
POLICY_REVISION = "policy-rev-1"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


def _as_field(value: object) -> object:
    """Pass malformed scalars through unchanged; wrap real sequences in a tuple."""
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        return value
    return tuple(value)


def node(
    identifier: str,
    *,
    evidence_kind: EvidenceKind = EvidenceKind.UNIT,
    cost_class: CostClass = CostClass.MEDIUM,
    depends_on: Sequence[str] = (),
    criterion_refs: Sequence[str] = ("C1",),
    duration_profile_ref: str | None = None,
    validation_environment_ref: str | None = None,
    invalidates_on: Sequence[str] = (),
    required_before: Sequence[str] = (),
    reusable_evidence_ref: str | None = None,
    required: bool = True,
    candidate_bound: bool = False,
    base_bound: bool = False,
    discrimination_class: DiscriminationClass = DiscriminationClass.NONE,
    discriminates_between: Sequence[str] = (),
    exclusive_resource_class: str | None = None,
    failure_subject: FailureSubject | None = None,
    probe_validity: ProbeValidity | None = None,
    release_worktree: ReleaseWorktreeState | None = None,
) -> VerificationNode:
    """Build one bounded verification node for the scheduling fixtures."""
    return VerificationNode(
        id=identifier,
        criterion_refs=_as_field(criterion_refs),  # type: ignore[arg-type]
        evidence_kind=evidence_kind,
        depends_on=_as_field(depends_on),  # type: ignore[arg-type]
        cost_class=cost_class,
        duration_profile_ref=duration_profile_ref,
        validation_environment_ref=validation_environment_ref,
        invalidates_on=_as_field(invalidates_on),  # type: ignore[arg-type]
        required_before=_as_field(required_before),  # type: ignore[arg-type]
        reusable_evidence_ref=reusable_evidence_ref,
        required=required,
        candidate_bound=candidate_bound,
        base_bound=base_bound,
        discrimination_class=discrimination_class,
        discriminates_between=_as_field(discriminates_between),  # type: ignore[arg-type]
        exclusive_resource_class=exclusive_resource_class,
        failure_subject=failure_subject,
        probe_validity=probe_validity,
        release_worktree=release_worktree,
    )


def receipt(
    identifier: str,
    node_id: str,
    *,
    status: str = "PASS",
    candidate_revision: str = CANDIDATE_A,
    subject_refs: Sequence[str] = (),
    base_revision: str | None = BASE_X,
    contract_digest: str | None = CONTRACT,
    policy_revision: str = POLICY_REVISION,
    environment_ref: str | None = None,
    expires_at_epoch: int | None = None,
) -> EvidenceReceipt:
    """Build one trusted evidence receipt bound to exact identities."""
    return EvidenceReceipt(
        evidence_ref=identifier,
        node_id=node_id,
        status=status,
        candidate_revision=candidate_revision,
        subject_refs=tuple(subject_refs),
        base_revision=base_revision,
        contract_digest=contract_digest,
        policy_revision=policy_revision,
        environment_ref=environment_ref,
        expires_at_epoch=expires_at_epoch,
    )


def snapshot(*receipts: EvidenceReceipt, complete: bool = True) -> TrustedEvidenceSnapshot:
    """Build one trusted evidence snapshot from qualified receipts."""
    return TrustedEvidenceSnapshot(
        snapshot_ref="snapshot-1",
        complete=complete,
        receipts=tuple(receipts),
    )


def policy(
    *,
    hard_window_seconds: int | None = None,
    reconciliation_reserve_seconds: int = 0,
    duration_profiles: Mapping[str, DurationProfile] | None = None,
    allow_subject_bound_reuse: bool = True,
) -> SchedulePolicy:
    """Build one scheduling policy."""
    return SchedulePolicy(
        policy_revision=POLICY_REVISION,
        hard_window_seconds=hard_window_seconds,
        reconciliation_reserve_seconds=reconciliation_reserve_seconds,
        duration_profiles=dict(duration_profiles or {}),
        allow_subject_bound_reuse=allow_subject_bound_reuse,
    )


def decisions_by_id(result: schedule.VerificationSchedule) -> Mapping[str, schedule.NodeDecision]:
    """Index the schedule decisions by node identifier."""
    return {item.node_id: item for item in result.decisions}


def test_cheap_static_prerequisite_failure_keeps_the_expensive_gate_undispatched() -> None:
    """Scenario 1: a failing cheap prerequisite must not buy an expensive gate."""
    cheap = node(
        "static-schema",
        evidence_kind=EvidenceKind.SCHEMA,
        cost_class=CostClass.CHEAP,
        invalidates_on=("source",),
    )
    expensive = node(
        "full-gate",
        evidence_kind=EvidenceKind.FULL_GATE,
        cost_class=CostClass.EXPENSIVE,
        depends_on=("static-schema",),
        invalidates_on=("candidateRevision", "source"),
        candidate_bound=True,
    )
    failing = snapshot(
        receipt(
            "ev-static-schema",
            "static-schema",
            status="FAIL",
            subject_refs=("source:skills/example.py",),
        )
    )

    result = schedule.plan_verification_schedule(
        [cheap, expensive],
        policy=policy(),
        trusted_evidence=failing,
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )

    indexed = decisions_by_id(result)
    assert indexed["full-gate"].decision is ScheduleDecision.NON_DISPATCH
    assert indexed["full-gate"].reason is ScheduleReason.PREREQUISITE_FAILED
    assert indexed["static-schema"].decision is ScheduleDecision.NON_DISPATCH
    assert indexed["static-schema"].reason is ScheduleReason.OBSERVED_FAILURE

    corrected = snapshot(
        receipt(
            "ev-static-schema",
            "static-schema",
            subject_refs=("source:skills/example.py",),
        )
    )
    repaired = schedule.plan_verification_schedule(
        [cheap, expensive],
        policy=policy(),
        trusted_evidence=corrected,
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    repaired_indexed = decisions_by_id(repaired)
    assert repaired_indexed["static-schema"].decision is ScheduleDecision.REUSE_CURRENT
    assert repaired_indexed["full-gate"].decision is ScheduleDecision.RUN


def test_focused_failure_defers_the_full_gate_and_repair_restores_mandatory_execution() -> None:
    """Scenario 2: a failing focused regression defers the expensive gate."""
    focused = node(
        "focused-unit",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        invalidates_on=("source",),
    )
    full_gate = node(
        "full-gate",
        evidence_kind=EvidenceKind.FULL_GATE,
        cost_class=CostClass.EXPENSIVE,
        depends_on=("focused-unit",),
        required_before=("candidate_freeze",),
        invalidates_on=("candidateRevision", "source"),
        candidate_bound=True,
    )
    failing = snapshot(receipt("ev-focused", "focused-unit", status="FAIL", subject_refs=("source:skills/a.py",)))

    deferred = schedule.plan_verification_schedule(
        [focused, full_gate],
        policy=policy(),
        trusted_evidence=failing,
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    deferred_indexed = decisions_by_id(deferred)
    assert deferred_indexed["full-gate"].decision is ScheduleDecision.NON_DISPATCH
    assert deferred_indexed["full-gate"].reason is ScheduleReason.PREREQUISITE_FAILED
    assert "full-gate" in deferred.closure.missing_node_refs
    assert deferred.closure.complete is False

    repaired = schedule.plan_verification_schedule(
        [focused, full_gate],
        policy=policy(),
        trusted_evidence=snapshot(receipt("ev-focused", "focused-unit", subject_refs=("source:skills/a.py",))),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    repaired_indexed = decisions_by_id(repaired)
    assert repaired_indexed["focused-unit"].decision is ScheduleDecision.REUSE_CURRENT
    assert repaired_indexed["full-gate"].decision is ScheduleDecision.RUN
    assert repaired.closure.complete is True


def test_final_exact_candidate_gate_is_not_reused_for_a_later_source_revision() -> None:
    """Scenario 3: an exact-candidate gate never survives a candidate change."""
    final_gate = node(
        "final-full-gate",
        evidence_kind=EvidenceKind.FULL_GATE,
        cost_class=CostClass.EXPENSIVE,
        required_before=("candidate_freeze",),
        invalidates_on=("candidateRevision", "source"),
        candidate_bound=True,
    )
    focused = node(
        "focused-local",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        invalidates_on=("source",),
    )
    prior = snapshot(
        receipt(
            "ev-final",
            "final-full-gate",
            candidate_revision=CANDIDATE_A,
            subject_refs=("candidateRevision:" + CANDIDATE_A, "source:skills/a.py"),
        ),
        receipt(
            "ev-focused",
            "focused-local",
            candidate_revision=CANDIDATE_A,
            subject_refs=("source:skills/a.py",),
        ),
    )

    result = schedule.plan_verification_schedule(
        [final_gate, focused],
        policy=policy(),
        trusted_evidence=prior,
        changed_refs=("source:skills/b.py",),
        current_candidate_revision=CANDIDATE_B,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    indexed = decisions_by_id(result)
    assert indexed["final-full-gate"].decision is ScheduleDecision.RUN
    assert indexed["final-full-gate"].reused_evidence_ref is None
    # The focused check is bound to an unchanged subtree, so it stays reusable.
    assert indexed["focused-local"].decision is ScheduleDecision.REUSE_CURRENT
    assert indexed["focused-local"].reused_evidence_ref == "ev-focused"

    denied = schedule.plan_verification_schedule(
        [final_gate, focused],
        policy=policy(allow_subject_bound_reuse=False),
        trusted_evidence=prior,
        current_candidate_revision=CANDIDATE_B,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    denied_indexed = decisions_by_id(denied)
    assert denied_indexed["focused-local"].decision is ScheduleDecision.RUN


def test_provider_outage_keeps_current_full_gate_evidence_and_leaves_review_non_green() -> None:
    """Scenario 4: an external reviewer outage is not a product failure."""
    full_gate = node(
        "full-gate",
        evidence_kind=EvidenceKind.FULL_GATE,
        cost_class=CostClass.EXPENSIVE,
        required_before=("candidate_freeze",),
        invalidates_on=("candidateRevision", "source"),
        candidate_bound=True,
    )
    review = node(
        "semantic-review",
        evidence_kind=EvidenceKind.SEMANTIC_REVIEW,
        cost_class=CostClass.EXPENSIVE,
        invalidates_on=("candidateRevision",),
        candidate_bound=True,
    )
    current = snapshot(
        receipt(
            "ev-full-gate",
            "full-gate",
            subject_refs=("candidateRevision:" + CANDIDATE_A, "source:skills/a.py"),
        )
    )

    result = schedule.plan_verification_schedule(
        [full_gate, review],
        policy=policy(),
        trusted_evidence=current,
        external_gate_status={"semantic-review": "NOT_EXECUTED"},
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    indexed = decisions_by_id(result)
    assert indexed["full-gate"].decision is ScheduleDecision.REUSE_CURRENT
    assert indexed["semantic-review"].decision is ScheduleDecision.BLOCKED_UNKNOWN
    assert indexed["semantic-review"].reason is ScheduleReason.PROVIDER_NOT_EXECUTED
    assert "semantic-review" in result.closure.missing_node_refs
    assert result.closure.complete is False


def test_small_source_change_invalidates_only_the_dependent_closure() -> None:
    """Scenario 5: invalidation propagates through declared dependencies only."""
    changed = node(
        "changed-check",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        invalidates_on=("source",),
    )
    sibling = node(
        "sibling-check",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        invalidates_on=("source",),
    )
    dependent = node(
        "dependent-check",
        evidence_kind=EvidenceKind.FOCUSED_INTEGRATION,
        cost_class=CostClass.MEDIUM,
        depends_on=("changed-check",),
        invalidates_on=("source",),
    )
    unknown_coverage = node(
        "unknown-coverage",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        invalidates_on=("source",),
    )
    current = snapshot(
        receipt("ev-changed", "changed-check", subject_refs=("source:skills/a.py",)),
        receipt("ev-sibling", "sibling-check", subject_refs=("source:skills/b.py",)),
        receipt("ev-dependent", "dependent-check", subject_refs=("source:skills/a.py",)),
        receipt("ev-unknown", "unknown-coverage", subject_refs=()),
    )

    result = schedule.plan_verification_schedule(
        [changed, sibling, dependent, unknown_coverage],
        policy=policy(),
        trusted_evidence=current,
        changed_refs=("source:skills/a.py",),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    indexed = decisions_by_id(result)
    assert indexed["changed-check"].decision is ScheduleDecision.RUN
    assert indexed["dependent-check"].decision is ScheduleDecision.RUN
    assert indexed["sibling-check"].decision is ScheduleDecision.REUSE_CURRENT
    assert indexed["unknown-coverage"].decision is ScheduleDecision.RUN
    assert any("unknown-coverage" in finding for finding in result.findings)


def test_moved_base_yields_a_stale_candidate_decision_instead_of_a_wasted_run() -> None:
    """Scenario 6: a moved base requires a fresh base-bound plan."""
    expensive = node(
        "full-gate",
        evidence_kind=EvidenceKind.FULL_GATE,
        cost_class=CostClass.EXPENSIVE,
        required_before=("candidate_freeze",),
        invalidates_on=("candidateRevision", "targetBase"),
        candidate_bound=True,
        base_bound=True,
    )

    result = schedule.plan_verification_schedule(
        [expensive],
        policy=policy(),
        trusted_evidence=snapshot(),
        planned_base_revision=BASE_X,
        current_base_revision=BASE_Y,
        current_candidate_revision=CANDIDATE_A,
        current_contract_digest=CONTRACT,
    )
    indexed = decisions_by_id(result)
    assert indexed["full-gate"].decision is ScheduleDecision.NON_DISPATCH
    assert indexed["full-gate"].reason is ScheduleReason.STALE_CANDIDATE

    fresh = schedule.plan_verification_schedule(
        [expensive],
        policy=policy(),
        trusted_evidence=snapshot(),
        planned_base_revision=BASE_Y,
        current_base_revision=BASE_Y,
        current_candidate_revision=CANDIDATE_A,
        current_contract_digest=CONTRACT,
    )
    fresh_indexed = decisions_by_id(fresh)
    assert fresh_indexed["full-gate"].decision is ScheduleDecision.RUN


def test_known_duration_beyond_the_window_is_parked_and_unknown_duration_is_not() -> None:
    """Scenario 7: admission uses trusted duration only."""
    slow = node(
        "slow-gate",
        evidence_kind=EvidenceKind.FULL_GATE,
        cost_class=CostClass.EXPENSIVE,
        duration_profile_ref="profile-slow",
    )
    unknown = node(
        "unknown-gate",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.MEDIUM,
        duration_profile_ref="profile-unknown",
    )
    bounded = policy(
        hard_window_seconds=100,
        reconciliation_reserve_seconds=10,
        duration_profiles={
            "profile-slow": DurationProfile(ref="profile-slow", expected_seconds=600, measured=True),
            "profile-unknown": DurationProfile(ref="profile-unknown", expected_seconds=None, measured=False),
        },
    )

    result = schedule.plan_verification_schedule(
        [slow, unknown],
        policy=bounded,
        trusted_evidence=snapshot(),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    indexed = decisions_by_id(result)
    assert indexed["slow-gate"].decision is ScheduleDecision.NON_DISPATCH
    assert indexed["slow-gate"].reason is ScheduleReason.INSUFFICIENT_EXECUTION_WINDOW
    assert indexed["unknown-gate"].decision is ScheduleDecision.RUN
    assert indexed["unknown-gate"].duration_status == "UNKNOWN"


def test_malformed_and_cyclic_inputs_are_rejected_without_execution() -> None:
    """Scenario 8: invalid graphs fail closed with typed findings."""
    cyclic = [
        node("a", depends_on=("b",)),
        node("b", depends_on=("a",)),
    ]
    findings = schedule.validate_verification_schedule(cyclic, policy())
    assert any("cycle" in finding for finding in findings)

    missing = schedule.validate_verification_schedule([node("a", depends_on=("ghost",))], policy())
    assert any("unknown dependency" in finding for finding in missing)

    duplicate = schedule.validate_verification_schedule([node("a"), node("a")], policy())
    assert any("duplicate" in finding for finding in duplicate)

    result = schedule.plan_verification_schedule(
        cyclic,
        policy=policy(),
        trusted_evidence=snapshot(),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    assert result.accepted is False
    assert result.decisions == ()


def test_release_worktree_head_mismatch_precedes_the_full_gate() -> None:
    """Scenario 9: a cheap release preflight precedes the expensive gate."""
    preflight = node(
        "release-worktree-preflight",
        evidence_kind=EvidenceKind.STATIC,
        cost_class=CostClass.CHEAP,
        release_worktree=ReleaseWorktreeState(
            head_revision=CANDIDATE_A,
            committed_digest="sha256:" + "d" * 64,
            worktree_digest="sha256:" + "e" * 64,
        ),
    )
    full_gate = node(
        "full-gate",
        evidence_kind=EvidenceKind.FULL_GATE,
        cost_class=CostClass.EXPENSIVE,
        depends_on=("release-worktree-preflight",),
        required_before=("candidate_freeze",),
        invalidates_on=("candidateRevision",),
        candidate_bound=True,
    )
    focused = node(
        "focused-unit",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        invalidates_on=("source",),
    )

    dirty = schedule.plan_verification_schedule(
        [preflight, full_gate, focused],
        policy=policy(),
        trusted_evidence=snapshot(),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    dirty_indexed = decisions_by_id(dirty)
    assert dirty_indexed["release-worktree-preflight"].decision is ScheduleDecision.NON_DISPATCH
    assert dirty_indexed["release-worktree-preflight"].reason is ScheduleReason.RELEASE_WORKTREE_HEAD_MISMATCH
    assert dirty_indexed["full-gate"].decision is ScheduleDecision.NON_DISPATCH
    assert dirty_indexed["full-gate"].reason is ScheduleReason.PREREQUISITE_FAILED
    # An unrelated genuine defect still runs and fails correctly.
    assert dirty_indexed["focused-unit"].decision is ScheduleDecision.RUN

    corrected = node(
        "release-worktree-preflight",
        evidence_kind=EvidenceKind.STATIC,
        cost_class=CostClass.CHEAP,
        release_worktree=ReleaseWorktreeState(
            head_revision=CANDIDATE_A,
            committed_digest="sha256:" + "d" * 64,
            worktree_digest="sha256:" + "d" * 64,
        ),
    )
    clean = schedule.plan_verification_schedule(
        [corrected, full_gate, focused],
        policy=policy(),
        trusted_evidence=snapshot(),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    clean_indexed = decisions_by_id(clean)
    assert clean_indexed["release-worktree-preflight"].decision is ScheduleDecision.RUN
    assert clean_indexed["full-gate"].decision is ScheduleDecision.RUN


def test_environment_contract_and_expiry_changes_cannot_qualify_reuse() -> None:
    """Scenario 10: reuse needs a current, environment-bound, unexpired receipt."""
    hermetic = node(
        "hermetic-unit",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        validation_environment_ref="env:hermetic-py312",
        invalidates_on=("source", "environment"),
    )
    live = node(
        "live-check",
        evidence_kind=EvidenceKind.LIVE,
        cost_class=CostClass.EXPENSIVE,
        validation_environment_ref="env:live-service",
        invalidates_on=("source", "environment"),
    )
    expired = node(
        "expired-check",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        invalidates_on=("source",),
    )
    current = snapshot(
        receipt(
            "ev-hermetic",
            "hermetic-unit",
            subject_refs=("source:skills/a.py", "environment:hermetic-py312"),
            environment_ref="env:hermetic-py312",
        ),
        receipt(
            "ev-live",
            "live-check",
            subject_refs=("source:skills/a.py", "environment:live-service"),
            environment_ref="env:live-service",
        ),
        receipt(
            "ev-expired",
            "expired-check",
            subject_refs=("source:skills/a.py",),
            expires_at_epoch=1000,
        ),
    )

    unchanged = schedule.plan_verification_schedule(
        [hermetic, live, expired],
        policy=policy(),
        trusted_evidence=current,
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
        now_epoch=500,
    )
    unchanged_indexed = decisions_by_id(unchanged)
    assert unchanged_indexed["hermetic-unit"].decision is ScheduleDecision.REUSE_CURRENT
    assert unchanged_indexed["live-check"].decision is ScheduleDecision.REUSE_CURRENT
    assert unchanged_indexed["expired-check"].decision is ScheduleDecision.REUSE_CURRENT

    moved_environment = schedule.plan_verification_schedule(
        [hermetic, live, expired],
        policy=policy(),
        trusted_evidence=current,
        changed_refs=("environment:live-service",),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
        now_epoch=500,
    )
    moved_indexed = decisions_by_id(moved_environment)
    assert moved_indexed["live-check"].decision is ScheduleDecision.RUN
    assert moved_indexed["hermetic-unit"].decision is ScheduleDecision.REUSE_CURRENT

    expired_now = schedule.plan_verification_schedule(
        [hermetic, live, expired],
        policy=policy(),
        trusted_evidence=current,
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
        now_epoch=2000,
    )
    expired_indexed = decisions_by_id(expired_now)
    assert expired_indexed["expired-check"].decision is ScheduleDecision.RUN


def test_caller_supplied_pass_text_cannot_certify_reuse() -> None:
    """Scenario 10: reuse needs a trusted typed receipt, not a caller string."""
    unit = node(
        "unit-check",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        invalidates_on=("source",),
    )
    result = schedule.plan_verification_schedule(
        [unit],
        policy=policy(),
        trusted_evidence=None,
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    indexed = decisions_by_id(result)
    assert indexed["unit-check"].decision is ScheduleDecision.RUN
    assert indexed["unit-check"].reused_evidence_ref is None


def test_ordering_is_stable_under_input_permutation_and_respects_dependencies() -> None:
    """Scenario 11: dependency order beats cost, and input order is irrelevant."""
    cheap_child = node(
        "cheap-child",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        depends_on=("expensive-parent",),
    )
    expensive_parent = node(
        "expensive-parent",
        evidence_kind=EvidenceKind.FOCUSED_INTEGRATION,
        cost_class=CostClass.EXPENSIVE,
    )
    material = node(
        "material-probe",
        evidence_kind=EvidenceKind.STATIC,
        cost_class=CostClass.CHEAP,
        discrimination_class=DiscriminationClass.MATERIAL,
        discriminates_between=("pass", "fail"),
    )
    informational = node(
        "informational-probe",
        evidence_kind=EvidenceKind.STATIC,
        cost_class=CostClass.CHEAP,
        discrimination_class=DiscriminationClass.NONE,
    )

    forward = schedule.plan_verification_schedule(
        [expensive_parent, cheap_child, material, informational],
        policy=policy(),
        trusted_evidence=snapshot(),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    reversed_order = schedule.plan_verification_schedule(
        [informational, material, cheap_child, expensive_parent],
        policy=policy(),
        trusted_evidence=snapshot(),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    assert forward.order == reversed_order.order
    assert forward.order.index("expensive-parent") < forward.order.index("cheap-child")
    assert forward.order.index("material-probe") < forward.order.index("informational-probe")


def test_unrelated_provider_status_change_waits_without_redundant_validation() -> None:
    """Scenario 12: provider state changes never manufacture approval."""
    full_gate = node(
        "full-gate",
        evidence_kind=EvidenceKind.FULL_GATE,
        cost_class=CostClass.EXPENSIVE,
        required_before=("candidate_freeze",),
        invalidates_on=("candidateRevision", "source"),
        candidate_bound=True,
    )
    review = node(
        "semantic-review",
        evidence_kind=EvidenceKind.SEMANTIC_REVIEW,
        cost_class=CostClass.EXPENSIVE,
        invalidates_on=("candidateRevision",),
        candidate_bound=True,
    )
    current = snapshot(
        receipt(
            "ev-full-gate",
            "full-gate",
            subject_refs=("candidateRevision:" + CANDIDATE_A, "source:skills/a.py"),
        )
    )

    first = schedule.plan_verification_schedule(
        [full_gate, review],
        policy=policy(),
        trusted_evidence=current,
        external_gate_status={"semantic-review": "AVAILABLE"},
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    first_indexed = decisions_by_id(first)
    assert first_indexed["full-gate"].decision is ScheduleDecision.REUSE_CURRENT
    assert first_indexed["semantic-review"].decision is ScheduleDecision.RUN

    second = schedule.plan_verification_schedule(
        [full_gate, review],
        policy=policy(),
        trusted_evidence=current,
        external_gate_status={"semantic-review": "UNAVAILABLE"},
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    second_indexed = decisions_by_id(second)
    assert second_indexed["full-gate"].decision is ScheduleDecision.REUSE_CURRENT
    assert second_indexed["semantic-review"].decision is ScheduleDecision.BLOCKED_UNKNOWN
    assert second.closure.complete is False


def test_failure_subject_preflight_blocks_speculative_repair() -> None:
    """The failure-subject preflight composes with evidence identity."""
    repair = node(
        "repair-focused",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        failure_subject=FailureSubject(
            reported_candidate_ref=CANDIDATE_A,
            reported_workflow_ref="workflow-1",
            current_candidate_ref=CANDIDATE_B,
            current_workflow_ref="workflow-2",
        ),
    )
    mismatch = schedule.plan_verification_schedule(
        [repair],
        policy=policy(),
        trusted_evidence=snapshot(),
        current_candidate_revision=CANDIDATE_B,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    mismatch_indexed = decisions_by_id(mismatch)
    assert mismatch_indexed["repair-focused"].decision is ScheduleDecision.NON_DISPATCH
    assert mismatch_indexed["repair-focused"].reason is ScheduleReason.FAILURE_SUBJECT_MISMATCH

    unknown = node(
        "repair-focused",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        failure_subject=FailureSubject(
            reported_candidate_ref=CANDIDATE_A,
            reported_workflow_ref=None,
            current_candidate_ref=CANDIDATE_A,
            current_workflow_ref="workflow-2",
        ),
    )
    unknown_result = schedule.plan_verification_schedule(
        [unknown],
        policy=policy(),
        trusted_evidence=snapshot(),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    unknown_indexed = decisions_by_id(unknown_result)
    assert unknown_indexed["repair-focused"].decision is ScheduleDecision.BLOCKED_UNKNOWN
    assert unknown_indexed["repair-focused"].reason is ScheduleReason.FAILURE_SUBJECT_UNKNOWN


def test_invalid_probe_validity_cannot_authorize_a_dependent_repair() -> None:
    """An invalid or unknown probe cannot authorize consequential work."""
    repair = node(
        "credential-rotation",
        evidence_kind=EvidenceKind.OTHER,
        cost_class=CostClass.MEDIUM,
        depends_on=("credential-probe",),
    )
    probe = node(
        "credential-probe",
        evidence_kind=EvidenceKind.OTHER,
        cost_class=CostClass.CHEAP,
        probe_validity=ProbeValidity(validity="INVALID"),
    )
    result = schedule.plan_verification_schedule(
        [repair, probe],
        policy=policy(),
        trusted_evidence=snapshot(),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    indexed = decisions_by_id(result)
    assert indexed["credential-probe"].decision is ScheduleDecision.NON_DISPATCH
    assert indexed["credential-probe"].reason is ScheduleReason.PROBE_VALIDITY_INVALID
    assert indexed["credential-rotation"].decision is ScheduleDecision.NON_DISPATCH
    assert indexed["credential-rotation"].reason is ScheduleReason.PREREQUISITE_FAILED


def test_exclusive_resource_classes_are_serialized_and_reported() -> None:
    """Heavy suites sharing one exclusive resource class never overlap."""
    first = node(
        "heavy-one",
        evidence_kind=EvidenceKind.FULL_GATE,
        cost_class=CostClass.EXPENSIVE,
        exclusive_resource_class="host-exclusive",
    )
    second = node(
        "heavy-two",
        evidence_kind=EvidenceKind.FULL_GATE,
        cost_class=CostClass.EXPENSIVE,
        exclusive_resource_class="host-exclusive",
    )
    result = schedule.plan_verification_schedule(
        [first, second],
        policy=policy(),
        trusted_evidence=snapshot(),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    assert "host-exclusive" in result.serialized_resource_classes
    assert result.order.index("heavy-one") < result.order.index("heavy-two")


def test_incomplete_or_duplicate_evidence_snapshots_fail_closed() -> None:
    """Incomplete coverage and ambiguous evidence never certify reuse."""
    unit = node(
        "unit-check",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        invalidates_on=("source",),
    )
    incomplete = schedule.plan_verification_schedule(
        [unit],
        policy=policy(),
        trusted_evidence=snapshot(
            receipt("ev-unit", "unit-check", subject_refs=("source:skills/a.py",)),
            complete=False,
        ),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    incomplete_indexed = decisions_by_id(incomplete)
    assert incomplete_indexed["unit-check"].decision is ScheduleDecision.RUN

    duplicate = schedule.validate_verification_schedule([unit], policy())
    assert duplicate == ()

    conflicting = schedule.plan_verification_schedule(
        [unit],
        policy=policy(),
        trusted_evidence=snapshot(
            receipt("ev-one", "unit-check", subject_refs=("source:skills/a.py",)),
            receipt("ev-two", "unit-check", subject_refs=("source:skills/b.py",)),
        ),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    assert conflicting.accepted is False
    assert any("duplicate evidence" in finding for finding in conflicting.findings)


def test_unknown_evidence_or_policy_identities_are_rejected() -> None:
    """Unknown duration profile and unknown receipt target are typed findings."""
    unit = node(
        "unit-check",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        duration_profile_ref="profile-missing",
    )
    findings = schedule.validate_verification_schedule([unit], policy())
    assert any("duration profile" in finding for finding in findings)

    result = schedule.plan_verification_schedule(
        [node("unit-check", evidence_kind=EvidenceKind.UNIT, cost_class=CostClass.CHEAP)],
        policy=policy(),
        trusted_evidence=snapshot(receipt("ev-ghost", "not-a-node")),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    assert result.accepted is False
    assert any("unknown node" in finding for finding in result.findings)


def test_oversized_graphs_are_rejected_without_execution() -> None:
    """Bounded input shapes reject oversized graphs instead of processing them."""
    oversized = [node(f"node-{index}") for index in range(300)]
    findings = schedule.validate_verification_schedule(oversized, policy())
    assert any("too many" in finding for finding in findings)


def test_optional_zero_discrimination_nodes_are_elided_without_weakening_required_evidence() -> None:
    """Optional nodes with no decision value may be deferred safely."""
    required_check = node(
        "required-check",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        required=True,
    )
    optional_probe = node(
        "optional-probe",
        evidence_kind=EvidenceKind.STATIC,
        cost_class=CostClass.CHEAP,
        required=False,
        discrimination_class=DiscriminationClass.NONE,
    )
    result = schedule.plan_verification_schedule(
        [optional_probe, required_check],
        policy=policy(),
        trusted_evidence=snapshot(),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    indexed = decisions_by_id(result)
    assert indexed["optional-probe"].decision is ScheduleDecision.NON_DISPATCH
    assert indexed["optional-probe"].reason is ScheduleReason.OPTIONAL_ZERO_DISCRIMINATION
    assert indexed["required-check"].decision is ScheduleDecision.RUN
    assert result.closure.complete is True


def test_risk_only_planner_behavior_is_unchanged() -> None:
    """Existing risk-only callers keep their signatures and behavior."""
    planner = _load("qa_plan_verification_risk_only", TOOLS / "plan_verification.py")
    plan = planner.plan_verification(planner.ChangeRisk(change_surface="docs", blast_radius="local"))
    assert plan.risk is planner.RiskLevel.LOW
    assert plan.required_layers == ("static", "unit")
    assert plan.acceptance_contract_digest is None


@pytest.mark.parametrize("identifier", ["", " ", "x" * 200])
def test_malformed_node_identifiers_are_rejected(identifier: str) -> None:
    """Node identifiers are bounded non-empty strings."""
    findings = schedule.validate_verification_schedule([node(identifier)], policy())
    assert findings


def test_malformed_node_shapes_fail_closed_with_typed_findings() -> None:
    """Malformed node fields never reach execution."""
    malformed = [
        "not-a-node",
        VerificationNode(id="bad-kinds", evidence_kind="static", cost_class="cheap"),
        VerificationNode(id="bad-deps", depends_on=("ghost", "ghost")),
        VerificationNode(id="bad-refs", criterion_refs=5),
        VerificationNode(id="bad-boundary", required_before=("not-a-boundary",)),
        VerificationNode(id="bad-kind-ref", invalidates_on=("",)),
        VerificationNode(id="bad-resource", exclusive_resource_class=""),
        VerificationNode(id="bad-probe", probe_validity=ProbeValidity(validity="BOGUS")),
        VerificationNode(id="bad-failure-subject", failure_subject="not-a-record"),
        VerificationNode(id="bad-worktree", release_worktree="not-a-record"),
        VerificationNode(id="bad-discrimination", discrimination_class="material"),
    ]
    findings = schedule.validate_verification_schedule(malformed, policy())
    assert findings
    assert any("VerificationNode records" in finding for finding in findings)
    assert any("invalid evidence kind" in finding for finding in findings)
    assert any("invalid cost class" in finding for finding in findings)
    assert any("depends_on must be unique" in finding for finding in findings)
    assert any("unknown dependency" in finding for finding in findings)
    assert any("criterion_refs must be an array" in finding for finding in findings)
    assert any("unknown required_before boundary" in finding for finding in findings)
    assert any("invalidates_on must be an array of strings" in finding for finding in findings)
    assert any("invalid exclusive resource class" in finding for finding in findings)
    assert any("unknown probe validity class" in finding for finding in findings)
    assert any("invalid failure subject precondition" in finding for finding in findings)
    assert any("invalid release worktree precondition" in finding for finding in findings)
    assert any("invalid discrimination class" in finding for finding in findings)


def test_bounded_graph_shapes_are_rejected() -> None:
    """Depth, edge count, and input shape bounds fail closed."""
    deep = [node(f"deep-{index}", depends_on=(f"deep-{index - 1}",)) for index in range(1, 40)]
    deep_findings = schedule.validate_verification_schedule(deep, policy())
    assert any("dependency depth" in finding for finding in deep_findings)

    wide = [node(f"wide-{index}", depends_on=tuple(f"wide-{other}" for other in range(30))) for index in range(40)]
    wide_findings = schedule.validate_verification_schedule(wide, policy())
    assert any("too many dependency edges" in finding for finding in wide_findings)

    assert schedule.validate_verification_schedule("not-a-list", policy())  # type: ignore[arg-type]
    assert schedule.validate_verification_schedule([node("a")], "not-a-policy")  # type: ignore[arg-type]


def test_untrusted_evidence_shapes_are_rejected() -> None:
    """Only a trusted typed snapshot can authorize reuse."""
    unit = node(
        "unit-check",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        invalidates_on=("source",),
    )
    untyped = schedule.plan_verification_schedule(
        [unit],
        policy=policy(),
        trusted_evidence={"passed": True},  # type: ignore[arg-type]
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    assert untyped.accepted is False
    assert any("TrustedEvidenceSnapshot" in finding for finding in untyped.findings)

    bad_status = schedule.plan_verification_schedule(
        [unit],
        policy=policy(),
        trusted_evidence=snapshot(receipt("ev-unit", "unit-check", status="LIKELY")),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    assert bad_status.accepted is False
    assert any("unknown status" in finding for finding in bad_status.findings)

    bad_gate = schedule.plan_verification_schedule(
        [unit],
        policy=policy(),
        trusted_evidence=snapshot(),
        external_gate_status={"unit-check": "MAYBE"},
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    assert bad_gate.accepted is False
    assert any("unknown status" in finding for finding in bad_gate.findings)


def test_material_discrimination_requires_declared_alternatives() -> None:
    """A material discriminator without alternatives is a typed finding."""
    findings = schedule.validate_verification_schedule(
        [node("probe", discrimination_class=DiscriminationClass.MATERIAL)],
        policy(),
    )
    assert any("material discrimination without alternatives" in finding for finding in findings)


def test_self_dependency_and_duplicate_dependencies_are_rejected() -> None:
    """A node may not depend on itself and may not repeat a dependency."""
    findings = schedule.validate_verification_schedule(
        [node("self", depends_on=("self",)), node("other", depends_on=("other", "other"))],
        policy(),
    )
    assert any("depends on itself" in finding for finding in findings)
    assert any("depends_on must be unique" in finding for finding in findings)


def test_missing_contract_digest_does_not_qualify_evidence() -> None:
    """F1: Missing contract identity must not qualify evidence under another contract."""
    unit = node(
        "unit-check",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        invalidates_on=("source",),
    )
    # Receipt has a contract digest, but current_contract_digest is None
    # This should NOT qualify as reusable (fail-open bug in v3.30.0)
    result = schedule.plan_verification_schedule(
        [unit],
        policy=policy(),
        trusted_evidence=snapshot(
            receipt("ev-unit", "unit-check", contract_digest=CONTRACT, subject_refs=("source:skills/a.py",))
        ),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=None,  # Missing contract identity
    )
    indexed = decisions_by_id(result)
    # Should NOT reuse - missing contract identity is a mismatch
    assert indexed["unit-check"].decision is ScheduleDecision.RUN
    assert indexed["unit-check"].reason is ScheduleReason.EVIDENCE_CONTRACT_MISMATCH


def test_missing_now_epoch_does_not_qualify_expiring_evidence() -> None:
    """F1: Missing current time must not qualify expiring evidence."""
    unit = node(
        "unit-check",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        invalidates_on=("source",),
    )
    # Receipt expires in the past, but now_epoch is None
    # This should NOT qualify as reusable (fail-open bug in v3.30.0)
    result = schedule.plan_verification_schedule(
        [unit],
        policy=policy(),
        trusted_evidence=snapshot(
            receipt("ev-unit", "unit-check", subject_refs=("source:skills/a.py",), expires_at_epoch=1000)
        ),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
        now_epoch=None,  # Missing current time
    )
    indexed = decisions_by_id(result)
    # Should NOT reuse - can't verify expiry without current time
    assert indexed["unit-check"].decision is ScheduleDecision.RUN
    assert indexed["unit-check"].reason is ScheduleReason.EVIDENCE_EXPIRED


def test_hard_window_charges_only_executable_nodes() -> None:
    """F2: Hard window should only charge budget for nodes that actually RUN."""
    # P: 600s (expensive, doesn't fit in 100s window)
    # C: depends on P, 60s (cheap)
    # I: independent, 60s (cheap)
    # Hard window: 100s
    # Expected: P parked, C deferred (depends on P), I eligible to RUN
    p = node(
        "P",
        evidence_kind=EvidenceKind.FULL_GATE,
        cost_class=CostClass.EXPENSIVE,
        duration_profile_ref="profile-p",
    )
    c = node(
        "C",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        depends_on=("P",),
        duration_profile_ref="profile-c",
    )
    i = node(
        "I",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        duration_profile_ref="profile-i",
    )
    bounded = policy(
        hard_window_seconds=100,
        reconciliation_reserve_seconds=10,
        duration_profiles={
            "profile-p": DurationProfile(ref="profile-p", expected_seconds=600, measured=True),
            "profile-c": DurationProfile(ref="profile-c", expected_seconds=60, measured=True),
            "profile-i": DurationProfile(ref="profile-i", expected_seconds=60, measured=True),
        },
    )

    result = schedule.plan_verification_schedule(
        [p, c, i],
        policy=bounded,
        trusted_evidence=snapshot(),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    indexed = decisions_by_id(result)
    # P should be PARKED (doesn't fit)
    assert indexed["P"].decision is ScheduleDecision.NON_DISPATCH
    assert indexed["P"].reason is ScheduleReason.INSUFFICIENT_EXECUTION_WINDOW
    # C should be DEFER (depends on P which is parked)
    assert indexed["C"].decision is ScheduleDecision.DEFER_UNTIL_DEPENDENCY
    assert indexed["C"].reason is ScheduleReason.PREREQUISITE_PENDING
    # I should RUN (independent, fits in window)
    assert indexed["I"].decision is ScheduleDecision.RUN
    # Window should only charge for I (60s), not for P (600s) or C (deferred)
    assert result.order == ("I",)


def test_malformed_depends_on_fails_closed() -> None:
    """F3: depends_on=5 (non-sequence) fails closed with typed finding."""
    findings = schedule.validate_verification_schedule(
        [node("bad", depends_on=5)],  # type: ignore[arg-type]
        policy(),
    )
    assert any("depends_on must be an array of strings" in finding for finding in findings)


def test_malformed_discriminates_between_fails_closed() -> None:
    """F3: non-sequence discriminates_between fails closed."""
    findings = schedule.validate_verification_schedule(
        [node("bad", discriminates_between="not-a-sequence")],  # type: ignore[arg-type]
        policy(),
    )
    assert any("discriminates_between must be an array of strings" in finding for finding in findings)


def test_malformed_required_before_fails_closed() -> None:
    """F3: malformed required_before fails closed."""
    findings = schedule.validate_verification_schedule(
        [node("bad", required_before=5)],  # type: ignore[arg-type]
        policy(),
    )
    assert any("required_before must be an array of strings" in finding for finding in findings)


def test_malformed_invalidates_on_fails_closed() -> None:
    """F3: malformed invalidates_on fails closed."""
    findings = schedule.validate_verification_schedule(
        [node("bad", invalidates_on=5)],  # type: ignore[arg-type]
        policy(),
    )
    assert any("invalidates_on must be an array of strings" in finding for finding in findings)


def test_non_string_exclusive_resource_class_fails_closed() -> None:
    """F3: non-string exclusive_resource_class fails closed."""
    findings = schedule.validate_verification_schedule(
        [node("bad", exclusive_resource_class=5)],  # type: ignore[arg-type]
        policy(),
    )
    assert any("exclusive resource class" in finding for finding in findings)


def test_plan_rejects_malformed_input_with_zero_dispatch() -> None:
    """F3: Malformed input produces zero dispatch, no uncaught exception."""
    result = schedule.plan_verification_schedule(
        [node("bad", depends_on=5)],  # type: ignore[arg-type]
        policy=policy(),
        trusted_evidence=snapshot(),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    assert result.accepted is False
    assert result.decisions == ()
    assert result.order == ()
    assert any("depends_on must be an array of strings" in finding for finding in result.findings)


def test_unhashable_duration_profile_ref_fails_closed() -> None:
    """Reviewer finding 1: a non-string duration reference must not raise."""
    malformed = node("bad", duration_profile_ref=[])  # type: ignore[arg-type]
    findings = schedule.validate_verification_schedule([malformed], policy())
    assert any("duration_profile_ref" in finding for finding in findings)

    result = schedule.plan_verification_schedule(
        [malformed],
        policy=policy(),
        trusted_evidence=snapshot(),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    assert result.accepted is False
    assert result.decisions == ()
    assert any("duration_profile_ref" in finding for finding in result.findings)


def test_both_missing_contract_identity_never_qualifies_reuse() -> None:
    """Reviewer finding 2: neither side naming a contract is not a match."""
    unit = node(
        "unit-check",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        invalidates_on=("source",),
    )
    result = schedule.plan_verification_schedule(
        [unit],
        policy=policy(),
        trusted_evidence=snapshot(
            receipt("ev-unit", "unit-check", contract_digest=None, subject_refs=("source:skills/a.py",))
        ),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=None,
    )
    indexed = decisions_by_id(result)
    assert indexed["unit-check"].decision is ScheduleDecision.RUN
    assert indexed["unit-check"].reason is ScheduleReason.EVIDENCE_CONTRACT_MISMATCH


def test_unhashable_external_gate_status_fails_closed() -> None:
    """Same family: an unhashable gate status must produce a finding, not a raise."""
    unit = node("unit-check", evidence_kind=EvidenceKind.UNIT, cost_class=CostClass.CHEAP)
    result = schedule.plan_verification_schedule(
        [unit],
        policy=policy(),
        trusted_evidence=snapshot(),
        external_gate_status={"unit-check": ["AVAILABLE"]},  # type: ignore[dict-item]
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    assert result.accepted is False
    assert any("status must be a string" in finding for finding in result.findings)


def test_unhashable_probe_validity_fails_closed() -> None:
    """Same family: an unhashable probe validity must produce a finding, not a raise."""
    findings = schedule.validate_verification_schedule(
        [node("bad", probe_validity=ProbeValidity(validity=["INVALID"]))],  # type: ignore[arg-type]
        policy(),
    )
    assert any("probe validity" in finding for finding in findings)


def test_malformed_receipt_fields_fail_closed() -> None:
    """Same family: malformed receipt identities are findings, never crashes."""
    unit = node("unit-check", evidence_kind=EvidenceKind.UNIT, cost_class=CostClass.CHEAP)
    result = schedule.plan_verification_schedule(
        [unit],
        policy=policy(),
        trusted_evidence=snapshot(
            EvidenceReceipt(
                evidence_ref="ev-bad",
                node_id=["unit-check"],  # type: ignore[list-item]
                status=["PASS"],  # type: ignore[list-item]
                candidate_revision=CANDIDATE_A,
                subject_refs=(1,),  # type: ignore[list-item]
                expires_at_epoch="soon",  # type: ignore[assignment]
            )
        ),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    assert result.accepted is False
    assert result.decisions == ()


def test_malformed_policy_fields_fail_closed() -> None:
    """Same family: malformed policy shapes are findings, never crashes."""
    unit = node("unit-check", evidence_kind=EvidenceKind.UNIT, cost_class=CostClass.CHEAP)
    malformed_policy = SchedulePolicy(
        policy_revision=POLICY_REVISION,
        hard_window_seconds="soon",  # type: ignore[assignment]
        reconciliation_reserve_seconds="ten",  # type: ignore[assignment]
        duration_profiles=[("profile-x", DurationProfile(ref="profile-x"))],  # type: ignore[arg-type]
    )
    result = schedule.plan_verification_schedule(
        [unit],
        policy=malformed_policy,
        trusted_evidence=snapshot(),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    assert result.accepted is False
    assert result.decisions == ()


def test_grandchild_cannot_consume_window_behind_a_parked_prerequisite() -> None:
    """CodeRabbit #196: a parked node's child must defer before its grandchild runs."""
    parked = node(
        "P",
        evidence_kind=EvidenceKind.FULL_GATE,
        cost_class=CostClass.EXPENSIVE,
        duration_profile_ref="profile-p",
    )
    child = node(
        "B",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        depends_on=("P",),
        duration_profile_ref="profile-b",
    )
    grandchild = node(
        "C",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        depends_on=("B",),
        duration_profile_ref="profile-c",
    )
    independent = node(
        "I",
        evidence_kind=EvidenceKind.UNIT,
        cost_class=CostClass.CHEAP,
        duration_profile_ref="profile-i",
    )
    bounded = policy(
        hard_window_seconds=100,
        reconciliation_reserve_seconds=10,
        duration_profiles={
            "profile-p": DurationProfile(ref="profile-p", expected_seconds=600, measured=True),
            "profile-b": DurationProfile(ref="profile-b", expected_seconds=60, measured=True),
            "profile-c": DurationProfile(ref="profile-c", expected_seconds=60, measured=True),
            "profile-i": DurationProfile(ref="profile-i", expected_seconds=60, measured=True),
        },
    )

    result = schedule.plan_verification_schedule(
        [parked, child, grandchild, independent],
        policy=bounded,
        trusted_evidence=snapshot(),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    indexed = decisions_by_id(result)
    assert indexed["P"].decision is ScheduleDecision.NON_DISPATCH
    assert indexed["P"].reason is ScheduleReason.INSUFFICIENT_EXECUTION_WINDOW
    assert indexed["B"].decision is ScheduleDecision.DEFER_UNTIL_DEPENDENCY
    assert indexed["C"].decision is ScheduleDecision.DEFER_UNTIL_DEPENDENCY
    # The independent sibling keeps the budget the deferred chain must not spend.
    assert indexed["I"].decision is ScheduleDecision.RUN
    assert result.order == ("I",)


def test_oversized_duration_profile_mapping_is_rejected_without_iteration() -> None:
    """CodeRabbit #196: an oversized profile mapping yields one bounded finding."""
    oversized = policy(
        duration_profiles={
            f"profile-{index}": DurationProfile(ref=f"profile-{index}", expected_seconds=1) for index in range(400)
        }
    )
    findings = schedule.validate_verification_schedule([node("a")], oversized)
    assert any("too many duration profiles" in finding for finding in findings)
    assert sum(1 for finding in findings if "duration profile" in finding) == 1


def test_non_mapping_duration_profiles_fail_closed_before_membership() -> None:
    """CodeRabbit #196: a non-mapping profiles value must not raise on lookup."""
    malformed_policy = SchedulePolicy(
        policy_revision=POLICY_REVISION,
        duration_profiles=5,  # type: ignore[dict-item]
    )
    probe = node("probe", duration_profile_ref="profile-x")
    findings = schedule.validate_verification_schedule([probe], malformed_policy)
    assert any("duration_profiles must be a mapping" in finding for finding in findings)

    result = schedule.plan_verification_schedule(
        [probe],
        policy=malformed_policy,
        trusted_evidence=snapshot(),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    assert result.accepted is False
    assert result.decisions == ()


def test_unhashable_node_id_fails_closed_without_raising() -> None:
    """Supervisory inspection: a non-string id must not crash graph construction."""
    malformed = node([])  # type: ignore[arg-type]
    findings = schedule.validate_verification_schedule([malformed], policy())
    assert any("node id must be a non-empty string" in finding for finding in findings)

    result = schedule.plan_verification_schedule(
        [malformed],
        policy=policy(),
        trusted_evidence=snapshot(),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    assert result.accepted is False
    assert result.decisions == ()
    assert any("node id must be a non-empty string" in finding for finding in result.findings)


def test_mixed_string_and_nonstring_node_ids_fail_closed() -> None:
    """Supervisory inspection: one malformed id poisons nothing and raises nothing."""
    mixed = [node("valid"), node(["bad"])]  # type: ignore[list-item]
    findings = schedule.validate_verification_schedule(mixed, policy())
    assert any("node id must be a non-empty string" in finding for finding in findings)
    assert any("unknown dependency" not in finding for finding in findings)

    result = schedule.plan_verification_schedule(
        mixed,
        policy=policy(),
        trusted_evidence=snapshot(),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    assert result.accepted is False
    assert result.decisions == ()


def test_non_sequence_receipts_fail_closed() -> None:
    """Supervisory inspection: a non-container receipts field must not raise."""
    unit = node("unit-check", evidence_kind=EvidenceKind.UNIT, cost_class=CostClass.CHEAP)
    malformed_snapshot = TrustedEvidenceSnapshot(snapshot_ref="snapshot-1", complete=True, receipts=5)  # type: ignore[arg-type]
    result = schedule.plan_verification_schedule(
        [unit],
        policy=policy(),
        trusted_evidence=malformed_snapshot,
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    assert result.accepted is False
    assert result.decisions == ()
    assert any("receipts" in finding for finding in result.findings)


def test_non_boolean_required_cannot_elide_a_node() -> None:
    """Supervisory inspection: an invalid required shape is a finding, never silent optionality."""
    probe = VerificationNode(
        id="probe",
        criterion_refs=("C1",),
        evidence_kind=EvidenceKind.STATIC,
        cost_class=CostClass.CHEAP,
        required=0,  # type: ignore[arg-type]
    )
    findings = schedule.validate_verification_schedule([probe], policy())
    assert any("required must be boolean" in finding for finding in findings)

    result = schedule.plan_verification_schedule(
        [probe],
        policy=policy(),
        trusted_evidence=snapshot(),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    assert result.accepted is False
    assert result.decisions == ()


def test_non_boolean_binding_flags_are_rejected() -> None:
    """Same family: candidate_bound and base_bound must be boolean or rejected."""
    findings = schedule.validate_verification_schedule(
        [
            node("a", candidate_bound=1),  # type: ignore[arg-type]
            node("b", base_bound="yes"),  # type: ignore[arg-type]
        ],
        policy(),
    )
    assert any("candidate_bound must be boolean" in finding for finding in findings)
    assert any("base_bound must be boolean" in finding for finding in findings)


def test_properly_typed_positive_control_still_schedules() -> None:
    """Positive control: the repairs keep a well-formed plan fully dispatchable."""
    cheap = node(
        "static-schema",
        evidence_kind=EvidenceKind.SCHEMA,
        cost_class=CostClass.CHEAP,
        invalidates_on=("source",),
    )
    gate = node(
        "full-gate",
        evidence_kind=EvidenceKind.FULL_GATE,
        cost_class=CostClass.EXPENSIVE,
        depends_on=("static-schema",),
        required_before=("candidate_freeze",),
        invalidates_on=("candidateRevision", "source"),
        candidate_bound=True,
    )
    result = schedule.plan_verification_schedule(
        [cheap, gate],
        policy=policy(),
        trusted_evidence=snapshot(),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    assert result.accepted is True
    indexed = decisions_by_id(result)
    assert indexed["static-schema"].decision is ScheduleDecision.RUN
    assert indexed["full-gate"].decision is ScheduleDecision.RUN
    assert result.order == ("static-schema", "full-gate")
    assert result.closure.complete is True


def test_malformed_duration_profile_record_fails_closed() -> None:
    """Independent review: profile ref and measured are part of the typed boundary."""
    malformed_policy = SchedulePolicy(
        policy_revision=POLICY_REVISION,
        duration_profiles={
            "profile-x": DurationProfile(ref=[], expected_seconds=60, measured="yes"),  # type: ignore[arg-type]
        },
    )
    probe = node("probe", duration_profile_ref="profile-x")
    findings = schedule.validate_verification_schedule([probe], malformed_policy)
    assert any("ref must be a non-empty string" in finding for finding in findings)
    assert any("measured must be boolean" in finding for finding in findings)

    result = schedule.plan_verification_schedule(
        [probe],
        policy=malformed_policy,
        trusted_evidence=snapshot(),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    assert result.accepted is False
    assert result.decisions == ()


def test_duration_profile_ref_must_match_its_mapping_key() -> None:
    """Independent review: a profile bound under one key cannot claim another identity."""
    malformed_policy = SchedulePolicy(
        policy_revision=POLICY_REVISION,
        duration_profiles={
            "profile-x": DurationProfile(ref="profile-y", expected_seconds=60, measured=True),
        },
    )
    findings = schedule.validate_verification_schedule(
        [node("probe", duration_profile_ref="profile-x")],
        malformed_policy,
    )
    assert any("ref must match" in finding for finding in findings)


def test_oversized_duration_profile_key_is_rejected_with_bounded_finding() -> None:
    """Independent review: profile keys carry the reference-length bound."""
    oversized_key = "k" * 600
    malformed_policy = SchedulePolicy(
        policy_revision=POLICY_REVISION,
        duration_profiles={
            oversized_key: DurationProfile(ref=oversized_key, expected_seconds=60, measured=True),
        },
    )
    findings = schedule.validate_verification_schedule(
        [node("probe", duration_profile_ref=oversized_key)],
        malformed_policy,
    )
    assert any("keys exceed the bounded length" in finding for finding in findings)
    assert all(len(finding) < 400 for finding in findings)


def test_non_string_profile_key_yields_bounded_diagnostics() -> None:
    """Independent review: repr() of malformed keys never enters a finding."""
    oversized = "X" * 100_000
    malformed_policy = SchedulePolicy(
        policy_revision=POLICY_REVISION,
        duration_profiles={(oversized,): object()},  # type: ignore[dict-item]
    )
    findings = schedule.validate_verification_schedule([node("a")], malformed_policy)
    assert findings
    assert all(len(finding) < 400 for finding in findings)
    assert all(oversized not in finding for finding in findings)

    result = schedule.plan_verification_schedule(
        [node("a")],
        policy=malformed_policy,
        trusted_evidence=snapshot(),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    assert result.accepted is False
    assert result.decisions == ()
    assert all(len(finding) < 400 for finding in result.findings)


def test_oversized_receipt_identities_fail_closed_with_bounded_findings() -> None:
    """Independent review: receipt identity fields carry the reference-length bound."""
    oversized_ref = "e" * 100_000
    unit = node("unit-check", evidence_kind=EvidenceKind.UNIT, cost_class=CostClass.CHEAP)
    malformed_receipt = EvidenceReceipt(
        evidence_ref=oversized_ref,
        node_id="unit-check",
        status="PASS",
        candidate_revision=CANDIDATE_A,
        subject_refs=("source:skills/a.py",),
        policy_revision=POLICY_REVISION,
        contract_digest=CONTRACT,
    )
    result = schedule.plan_verification_schedule(
        [unit],
        policy=policy(),
        trusted_evidence=snapshot(malformed_receipt),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    assert result.accepted is False
    assert result.decisions == ()
    assert any("exceed the bounded length" in finding for finding in result.findings)
    assert all(len(finding) < 400 for finding in result.findings)
    assert all(oversized_ref not in finding for finding in result.findings)


def test_oversized_receipt_optional_fields_fail_closed() -> None:
    """Same family: optional receipt references carry the same bound."""
    oversized_digest = "sha256:" + "c" * 100_000
    unit = node("unit-check", evidence_kind=EvidenceKind.UNIT, cost_class=CostClass.CHEAP)
    malformed_receipt = EvidenceReceipt(
        evidence_ref="ev-unit",
        node_id="unit-check",
        status="PASS",
        candidate_revision=CANDIDATE_A,
        subject_refs=("source:skills/a.py",),
        policy_revision=POLICY_REVISION,
        contract_digest=oversized_digest,
    )
    result = schedule.plan_verification_schedule(
        [unit],
        policy=policy(),
        trusted_evidence=snapshot(malformed_receipt),
        current_candidate_revision=CANDIDATE_A,
        current_base_revision=BASE_X,
        current_contract_digest=CONTRACT,
    )
    assert result.accepted is False
    assert result.decisions == ()
    assert any("exceed the bounded length" in finding for finding in result.findings)

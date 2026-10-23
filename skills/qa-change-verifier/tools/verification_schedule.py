"""Dependency-aware, cost-ordered verification scheduling and minimum rerun planning.

This module owns execution **order** and **minimum rerun set** derivation for a
verification plan. It deliberately does not evaluate acceptance, classify
product failure, grant waivers, or authorize mutation: those owners stay
unchanged, and the scheduler only consumes their trusted outputs.

The planner is pure and deterministic. It never executes a candidate command,
never reads a repository, and never promotes a scheduling recommendation into a
pass, a waiver, a reviewer verdict, or a release decision.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

MAX_NODES = 256
MAX_EDGES = 1024
MAX_DEPTH = 32
MAX_IDENTIFIER_LENGTH = 128
MAX_REFERENCE_LENGTH = 512
MAX_CRITERION_REFS = 64
MAX_SUBJECT_REFS = 64
MAX_DISCRIMINATIONS = 32

REQUIRED_BEFORE_BOUNDARIES = frozenset(
    {
        "mutation",
        "candidate_freeze",
        "integration",
        "release",
        "runtime_acceptance",
    }
)
EVIDENCE_STATUSES = frozenset({"PASS", "FAIL", "UNKNOWN", "NOT_EXECUTED"})
EXTERNAL_GATE_STATUSES = frozenset({"AVAILABLE", "NOT_EXECUTED", "UNAVAILABLE"})
PROBE_VALIDITIES = frozenset({"ADMITTED", "VALIDATED", "INVALID", "UNKNOWN"})


class EvidenceKind(StrEnum):
    """Provider-neutral verification evidence kinds."""

    STATIC = "static"
    SCHEMA = "schema"
    UNIT = "unit"
    FOCUSED_INTEGRATION = "focused_integration"
    FULL_GATE = "full_gate"
    SEMANTIC_REVIEW = "semantic_review"
    LIVE = "live"
    OTHER = "other"


class CostClass(StrEnum):
    """Relative execution cost of one verification node."""

    CHEAP = "cheap"
    MEDIUM = "medium"
    EXPENSIVE = "expensive"


class DiscriminationClass(StrEnum):
    """How much a node's outcome can change the remaining verification work."""

    NONE = "none"
    WEAK = "weak"
    MATERIAL = "material"


class ScheduleDecision(StrEnum):
    """The next legal action for one verification node."""

    RUN = "RUN"
    REUSE_CURRENT = "REUSE_CURRENT"
    DEFER_UNTIL_DEPENDENCY = "DEFER_UNTIL_DEPENDENCY"
    NON_DISPATCH = "NON_DISPATCH"
    BLOCKED_UNKNOWN = "BLOCKED_UNKNOWN"


class ScheduleReason(StrEnum):
    """Typed reason attached to every scheduling decision."""

    EVIDENCE_CURRENT = "EVIDENCE_CURRENT"
    EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"
    PREREQUISITE_FAILED = "PREREQUISITE_FAILED"
    PREREQUISITE_PENDING = "PREREQUISITE_PENDING"
    PREREQUISITE_UNKNOWN = "PREREQUISITE_UNKNOWN"
    OBSERVED_FAILURE = "OBSERVED_FAILURE"
    EVIDENCE_INVALIDATED = "EVIDENCE_INVALIDATED"
    EVIDENCE_CANDIDATE_MISMATCH = "EVIDENCE_CANDIDATE_MISMATCH"
    EVIDENCE_BASE_MISMATCH = "EVIDENCE_BASE_MISMATCH"
    EVIDENCE_CONTRACT_MISMATCH = "EVIDENCE_CONTRACT_MISMATCH"
    EVIDENCE_POLICY_MISMATCH = "EVIDENCE_POLICY_MISMATCH"
    EVIDENCE_ENVIRONMENT_MISMATCH = "EVIDENCE_ENVIRONMENT_MISMATCH"
    EVIDENCE_EXPIRED = "EVIDENCE_EXPIRED"
    EVIDENCE_COVERAGE_UNKNOWN = "EVIDENCE_COVERAGE_UNKNOWN"
    EVIDENCE_SUBJECT_CHANGED = "EVIDENCE_SUBJECT_CHANGED"
    EVIDENCE_STATUS_NON_GREEN = "EVIDENCE_STATUS_NON_GREEN"
    DECLARED_EVIDENCE_MISMATCH = "DECLARED_EVIDENCE_MISMATCH"
    PROVIDER_NOT_EXECUTED = "PROVIDER_NOT_EXECUTED"
    STALE_CANDIDATE = "STALE_CANDIDATE"
    INSUFFICIENT_EXECUTION_WINDOW = "INSUFFICIENT_EXECUTION_WINDOW"
    FAILURE_SUBJECT_MISMATCH = "FAILURE_SUBJECT_MISMATCH"
    FAILURE_SUBJECT_UNKNOWN = "FAILURE_SUBJECT_UNKNOWN"
    PROBE_VALIDITY_INVALID = "PROBE_VALIDITY_INVALID"
    PROBE_VALIDITY_UNKNOWN = "PROBE_VALIDITY_UNKNOWN"
    RELEASE_WORKTREE_HEAD_MISMATCH = "RELEASE_WORKTREE_HEAD_MISMATCH"
    OPTIONAL_ZERO_DISCRIMINATION = "OPTIONAL_ZERO_DISCRIMINATION"


_NEXT_ACTIONS: Mapping[ScheduleReason, str] = {
    ScheduleReason.EVIDENCE_CURRENT: "reuse the current qualified evidence",
    ScheduleReason.EVIDENCE_REQUIRED: "dispatch the node to produce current evidence",
    ScheduleReason.PREREQUISITE_FAILED: "repair the failed prerequisite, then re-plan",
    ScheduleReason.PREREQUISITE_PENDING: "wait for the pending prerequisite, then re-plan",
    ScheduleReason.PREREQUISITE_UNKNOWN: "resolve the unknown prerequisite state, then re-plan",
    ScheduleReason.OBSERVED_FAILURE: "repair the failing node, then re-plan",
    ScheduleReason.EVIDENCE_INVALIDATED: "rerun the invalidated node on the current candidate",
    ScheduleReason.EVIDENCE_CANDIDATE_MISMATCH: "produce fresh evidence for the current candidate",
    ScheduleReason.EVIDENCE_BASE_MISMATCH: "produce fresh evidence against the current base",
    ScheduleReason.EVIDENCE_CONTRACT_MISMATCH: "produce fresh evidence for the current contract",
    ScheduleReason.EVIDENCE_POLICY_MISMATCH: "produce fresh evidence under the current policy",
    ScheduleReason.EVIDENCE_ENVIRONMENT_MISMATCH: "produce fresh evidence in the current environment",
    ScheduleReason.EVIDENCE_EXPIRED: "produce fresh evidence because the prior receipt expired",
    ScheduleReason.EVIDENCE_COVERAGE_UNKNOWN: "declare the missing dependency coverage, then re-plan",
    ScheduleReason.EVIDENCE_SUBJECT_CHANGED: "rerun the node because a bound subject changed",
    ScheduleReason.EVIDENCE_STATUS_NON_GREEN: "produce a current green receipt for the node",
    ScheduleReason.DECLARED_EVIDENCE_MISMATCH: "produce the declared evidence reference",
    ScheduleReason.PROVIDER_NOT_EXECUTED: "wait for the external gate; keep unrelated evidence current",
    ScheduleReason.STALE_CANDIDATE: "re-plan against the current base revision",
    ScheduleReason.INSUFFICIENT_EXECUTION_WINDOW: "obtain a longer admitted window, then re-plan",
    ScheduleReason.FAILURE_SUBJECT_MISMATCH: "reconcile the reported failure subject before repairing",
    ScheduleReason.FAILURE_SUBJECT_UNKNOWN: "establish the failure subject identity before repairing",
    ScheduleReason.PROBE_VALIDITY_INVALID: "use a valid probe or a typed semantic producer",
    ScheduleReason.PROBE_VALIDITY_UNKNOWN: "establish probe validity before repairing",
    ScheduleReason.RELEASE_WORKTREE_HEAD_MISMATCH: (
        "commit or correct the release worktree so HEAD and the working tree agree, then re-plan"
    ),
    ScheduleReason.OPTIONAL_ZERO_DISCRIMINATION: "run the node only when it becomes decision-relevant",
}


@dataclass(frozen=True)
class DurationProfile:
    """A trusted measured or declared duration for one verification node."""

    ref: str
    expected_seconds: int | None = None
    measured: bool = False


@dataclass(frozen=True)
class SchedulePolicy:
    """Policy-owned scheduling constraints for one plan."""

    policy_revision: str
    hard_window_seconds: int | None = None
    reconciliation_reserve_seconds: int = 0
    duration_profiles: Mapping[str, DurationProfile] = field(default_factory=dict)
    allow_subject_bound_reuse: bool = True


@dataclass(frozen=True)
class EvidenceReceipt:
    """One trusted evidence receipt bound to exact identities."""

    evidence_ref: str
    node_id: str
    status: str
    candidate_revision: str
    subject_refs: tuple[str, ...] = ()
    base_revision: str | None = None
    contract_digest: str | None = None
    policy_revision: str = ""
    environment_ref: str | None = None
    expires_at_epoch: int | None = None


@dataclass(frozen=True)
class TrustedEvidenceSnapshot:
    """A complete trusted snapshot of current evidence receipts."""

    snapshot_ref: str
    complete: bool
    receipts: tuple[EvidenceReceipt, ...] = ()


@dataclass(frozen=True)
class FailureSubject:
    """Reported-versus-current identity for a possibly stale failure."""

    reported_candidate_ref: str
    current_candidate_ref: str
    reported_workflow_ref: str | None = None
    current_workflow_ref: str | None = None


@dataclass(frozen=True)
class ProbeValidity:
    """The validity class of a diagnostic probe observation."""

    validity: str


@dataclass(frozen=True)
class ReleaseWorktreeState:
    """The committed-versus-working-tree identity of a release artifact."""

    head_revision: str
    committed_digest: str
    worktree_digest: str


@dataclass(frozen=True)
class VerificationNode:
    """One bounded verification node in a dependency-aware plan."""

    id: str
    criterion_refs: tuple[str, ...] = ()
    evidence_kind: EvidenceKind = EvidenceKind.OTHER
    depends_on: tuple[str, ...] = ()
    cost_class: CostClass = CostClass.MEDIUM
    duration_profile_ref: str | None = None
    validation_environment_ref: str | None = None
    invalidates_on: tuple[str, ...] = ()
    required_before: tuple[str, ...] = ()
    reusable_evidence_ref: str | None = None
    required: bool = True
    candidate_bound: bool = False
    base_bound: bool = False
    discrimination_class: DiscriminationClass = DiscriminationClass.NONE
    discriminates_between: tuple[str, ...] = ()
    exclusive_resource_class: str | None = None
    failure_subject: FailureSubject | None = None
    probe_validity: ProbeValidity | None = None
    release_worktree: ReleaseWorktreeState | None = None


@dataclass(frozen=True)
class NodeDecision:
    """The scheduled next action for one verification node."""

    node_id: str
    decision: ScheduleDecision
    reason: ScheduleReason
    next_action: str
    depends_on: tuple[str, ...] = ()
    blocked_by: tuple[str, ...] = ()
    invalidated_by: tuple[str, ...] = ()
    reused_evidence_ref: str | None = None
    duration_status: str = "NOT_APPLICABLE"
    estimated_seconds: int | None = None


@dataclass(frozen=True)
class VerificationClosure:
    """Bounded closure metadata for the required verification node set."""

    required_node_refs: tuple[str, ...]
    executed_node_refs: tuple[str, ...]
    reusable_current_evidence_refs: tuple[str, ...]
    scheduled_node_refs: tuple[str, ...]
    missing_node_refs: tuple[str, ...]
    complete: bool


@dataclass(frozen=True)
class VerificationSchedule:
    """A deterministic, bounded verification schedule."""

    accepted: bool
    decisions: tuple[NodeDecision, ...]
    order: tuple[str, ...]
    closure: VerificationClosure
    findings: tuple[str, ...] = ()
    serialized_resource_classes: tuple[str, ...] = ()


class _State(StrEnum):
    """Internal resolution states used while building the schedule."""

    RUN = "RUN"
    REUSE = "REUSE"
    FAIL = "FAIL"
    EXTERNAL_PENDING = "EXTERNAL_PENDING"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"
    ELIDED = "ELIDED"
    PARKED = "PARKED"
    DEFER = "DEFER"


@dataclass(frozen=True)
class _Resolution:
    """One resolved node state with its typed reason."""

    state: _State
    reason: ScheduleReason
    reused_evidence_ref: str | None = None
    blocked_by: tuple[str, ...] = ()
    invalidated_by: tuple[str, ...] = ()


def _strings(value: object) -> tuple[str, ...] | None:
    """Return a tuple of non-empty strings, or None when the shape is invalid."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None
    items = list(value)
    if not all(isinstance(item, str) and item.strip() for item in items):
        return None
    return tuple(items)


def _subject_kind(reference: str) -> str:
    """Return the invalidation kind of one concrete subject reference."""
    head, separator, _ = reference.partition(":")
    return head if separator else head


def _duration_rank(node: VerificationNode, policy: SchedulePolicy) -> tuple[int, int]:
    """Rank a node by known duration so unknown timing never outranks known timing."""
    if node.duration_profile_ref is None:
        return (1, 0)
    profile = policy.duration_profiles.get(node.duration_profile_ref)
    if profile is None or profile.expected_seconds is None:
        return (1, 0)
    return (0, profile.expected_seconds)


def _sort_key(node: VerificationNode, policy: SchedulePolicy) -> tuple[int, int, tuple[int, int], str]:
    """Return the deterministic ready-set ordering key for one node."""
    discrimination = {
        DiscriminationClass.MATERIAL: 0,
        DiscriminationClass.WEAK: 1,
        DiscriminationClass.NONE: 2,
    }[node.discrimination_class]
    cost = {
        CostClass.CHEAP: 0,
        CostClass.MEDIUM: 1,
        CostClass.EXPENSIVE: 2,
    }[node.cost_class]
    return (discrimination, cost, _duration_rank(node, policy), node.id)


def _validate_policy(policy: SchedulePolicy) -> tuple[str, ...]:
    """Return bounded typed findings for a malformed policy record."""
    findings: list[str] = []
    if not isinstance(policy.policy_revision, str) or not policy.policy_revision.strip():
        findings.append("schedule policy policy_revision must be a non-empty string")
    elif len(policy.policy_revision) > MAX_REFERENCE_LENGTH:
        findings.append("schedule policy policy_revision exceeds the bounded length")
    window = policy.hard_window_seconds
    if window is not None and (type(window) is not int or window < 0):
        findings.append("schedule policy hard_window_seconds must be a non-negative integer or null")
    reserve = policy.reconciliation_reserve_seconds
    if type(reserve) is not int or reserve < 0:
        findings.append("schedule policy reconciliation_reserve_seconds must be a non-negative integer")
    profiles = policy.duration_profiles
    if not isinstance(profiles, Mapping):
        findings.append("schedule policy duration_profiles must be a mapping")  # type: ignore[unreachable]
    elif len(profiles) > MAX_NODES:
        findings.append(
            f"schedule policy has too many duration profiles: {len(profiles)} exceeds the bound {MAX_NODES}"
        )
    else:
        for reference, profile in profiles.items():
            if not isinstance(reference, str) or not reference.strip():
                findings.append("schedule policy duration profile keys must be non-empty strings")
            if not isinstance(profile, DurationProfile):
                findings.append(f"schedule policy duration profile {reference!r} must be a DurationProfile record")  # type: ignore[unreachable]
            elif profile.expected_seconds is not None and (
                type(profile.expected_seconds) is not int or profile.expected_seconds < 0
            ):
                findings.append(
                    f"schedule policy duration profile {reference!r} expected_seconds must be a non-negative integer or null"
                )
    if type(policy.allow_subject_bound_reuse) is not bool:
        findings.append("schedule policy allow_subject_bound_reuse must be boolean")  # type: ignore[unreachable]
    return tuple(findings)


def validate_verification_schedule(
    nodes: Sequence[VerificationNode],
    policy: SchedulePolicy,
) -> tuple[str, ...]:
    """Return bounded typed findings for an invalid schedule request."""
    findings: list[str] = []
    raw_nodes: object = nodes
    if not isinstance(raw_nodes, Sequence) or isinstance(raw_nodes, (str, bytes, bytearray)):
        return ("verification nodes must be an array of VerificationNode records",)
    items = list(raw_nodes)
    if len(items) > MAX_NODES:
        return (f"verification plan has too many nodes: {len(items)} exceeds the bound {MAX_NODES}",)
    if not isinstance(policy, SchedulePolicy):
        return ("schedule policy must be a SchedulePolicy record",)  # type: ignore[unreachable]
    findings.extend(_validate_policy(policy))

    identifiers: set[str] = set()
    edge_count = 0
    for item in items:
        if not isinstance(item, VerificationNode):
            findings.append("verification nodes must be VerificationNode records")
            continue
        identifier = item.id
        if not isinstance(identifier, str) or not identifier.strip():
            findings.append("verification node id must be a non-empty string")
            continue
        if len(identifier) > MAX_IDENTIFIER_LENGTH:
            findings.append(
                f"verification node id must be at most {MAX_IDENTIFIER_LENGTH} characters: {identifier[:32]}"
            )
            continue
        if identifier in identifiers:
            findings.append(f"duplicate verification node id: {identifier}")
            continue
        identifiers.add(identifier)

        criterion_refs = _strings(item.criterion_refs)
        if criterion_refs is None:
            findings.append(f"verification node {identifier} criterion_refs must be an array of strings")
        elif len(criterion_refs) > MAX_CRITERION_REFS:
            findings.append(f"verification node {identifier} criterion_refs exceed the bounded count")
        elif any(len(ref) > MAX_REFERENCE_LENGTH for ref in criterion_refs):
            findings.append(f"verification node {identifier} criterion_refs exceed the bounded length")

        depends_on = _strings(item.depends_on)
        if depends_on is None:
            findings.append(f"verification node {identifier} depends_on must be an array of strings")
            depends_on = ()
        else:
            if len(set(depends_on)) != len(depends_on):
                findings.append(f"verification node {identifier} depends_on must be unique")
            if identifier in depends_on:
                findings.append(f"verification node {identifier} depends on itself")
            if any(len(reference) > MAX_IDENTIFIER_LENGTH for reference in depends_on):
                findings.append(f"verification node {identifier} dependency reference is too long")
            edge_count += len(depends_on)

        if not isinstance(item.evidence_kind, EvidenceKind):
            findings.append(f"verification node {identifier} has an invalid evidence kind")  # type: ignore[unreachable]
        if not isinstance(item.cost_class, CostClass):
            findings.append(f"verification node {identifier} has an invalid cost class")  # type: ignore[unreachable]
        if not isinstance(item.discrimination_class, DiscriminationClass):
            findings.append(f"verification node {identifier} has an invalid discrimination class")  # type: ignore[unreachable]
        if item.discrimination_class is DiscriminationClass.MATERIAL and not item.discriminates_between:
            findings.append(f"verification node {identifier} declares material discrimination without alternatives")
        discriminates_between = _strings(item.discriminates_between)
        if discriminates_between is None:
            findings.append(f"verification node {identifier} discriminates_between must be an array of strings")
        elif len(discriminates_between) > MAX_DISCRIMINATIONS:
            findings.append(f"verification node {identifier} discriminates_between exceeds the bounded count")
        elif any(len(ref) > MAX_REFERENCE_LENGTH for ref in discriminates_between):
            findings.append(f"verification node {identifier} discriminates_between exceeds the bounded length")

        required_before = _strings(item.required_before)
        if required_before is None:
            findings.append(f"verification node {identifier} required_before must be an array of strings")
        else:
            for boundary in required_before:
                if boundary not in REQUIRED_BEFORE_BOUNDARIES:
                    findings.append(
                        f"verification node {identifier} has an unknown required_before boundary: {boundary}"
                    )

        invalidates_on = _strings(item.invalidates_on)
        if invalidates_on is None:
            findings.append(f"verification node {identifier} invalidates_on must be an array of strings")
        else:
            for kind in invalidates_on:
                if not isinstance(kind, str) or not kind.strip() or len(kind) > MAX_REFERENCE_LENGTH:
                    findings.append(f"verification node {identifier} has an invalid invalidation kind")
        duration_profile_ref = item.duration_profile_ref
        if duration_profile_ref is not None:
            if not isinstance(duration_profile_ref, str) or not duration_profile_ref.strip():
                findings.append(f"verification node {identifier} duration_profile_ref must be a non-empty string")
            elif len(duration_profile_ref) > MAX_REFERENCE_LENGTH:
                findings.append(f"verification node {identifier} duration_profile_ref exceeds the bounded length")
            elif not isinstance(policy.duration_profiles, Mapping):
                # The malformed-profiles finding is already recorded by the
                # policy validation above; never probe a non-mapping here.
                # Runtime defense: frozen dataclasses do not enforce types.
                findings.append(  # type: ignore[unreachable]
                    f"verification node {identifier} duration profile lookup skipped: policy profiles are malformed"
                )
            elif duration_profile_ref not in policy.duration_profiles:
                findings.append(
                    f"verification node {identifier} references an unknown duration profile: {duration_profile_ref}"
                )
        if not isinstance(item.required, bool):
            # Runtime defense: frozen dataclasses do not enforce field types.
            findings.append(f"verification node {identifier} required must be boolean")  # type: ignore[unreachable]
        if not isinstance(item.candidate_bound, bool):
            findings.append(f"verification node {identifier} candidate_bound must be boolean")  # type: ignore[unreachable]
        if not isinstance(item.base_bound, bool):
            findings.append(f"verification node {identifier} base_bound must be boolean")  # type: ignore[unreachable]
        if item.exclusive_resource_class is not None:
            if not isinstance(item.exclusive_resource_class, str) or not item.exclusive_resource_class.strip():
                findings.append(f"verification node {identifier} has an invalid exclusive resource class")
        if item.failure_subject is not None and not isinstance(item.failure_subject, FailureSubject):
            findings.append(f"verification node {identifier} has an invalid failure subject precondition")  # type: ignore[unreachable]
        if item.probe_validity is not None:
            if not isinstance(item.probe_validity, ProbeValidity):
                findings.append(f"verification node {identifier} has an invalid probe validity precondition")  # type: ignore[unreachable]
            elif not isinstance(item.probe_validity.validity, str):
                findings.append(f"verification node {identifier} has an invalid probe validity class")  # type: ignore[unreachable]
            elif item.probe_validity.validity not in PROBE_VALIDITIES:
                findings.append(f"verification node {identifier} has an unknown probe validity class")
        if item.release_worktree is not None and not isinstance(item.release_worktree, ReleaseWorktreeState):
            findings.append(f"verification node {identifier} has an invalid release worktree precondition")  # type: ignore[unreachable]

    if edge_count > MAX_EDGES:
        findings.append(f"verification plan has too many dependency edges: {edge_count} exceeds {MAX_EDGES}")

    for item in items:
        if not isinstance(item, VerificationNode):
            continue
        for reference in _strings(item.depends_on) or ():
            if reference not in identifiers:
                findings.append(f"verification node {item.id} references an unknown dependency: {reference}")

    cycle = _find_cycle(items)
    if cycle:
        findings.append("verification plan contains a dependency cycle: " + " -> ".join(cycle))
    depth = _maximum_depth(items)
    if depth > MAX_DEPTH:
        findings.append(f"verification plan exceeds the bounded dependency depth: {depth} exceeds {MAX_DEPTH}")
    return tuple(sorted(set(findings)))


def _find_cycle(nodes: Sequence[VerificationNode]) -> tuple[str, ...]:
    """Return one dependency cycle, or an empty tuple when the graph is acyclic.

    Only nodes with valid string identifiers enter the graph; the validator
    has already recorded a finding for every malformed identifier, so a
    non-string id can never reach the membership test here.
    """
    by_id = {item.id: item for item in nodes if isinstance(item, VerificationNode) and isinstance(item.id, str)}
    visited: set[str] = set()
    stack: list[str] = []

    def visit(identifier: str) -> tuple[str, ...]:
        if identifier in stack:
            start = stack.index(identifier)
            return tuple(stack[start:] + [identifier])
        if identifier in visited:
            return ()
        visited.add(identifier)
        stack.append(identifier)
        item = by_id.get(identifier)
        if item is not None:
            for reference in _strings(item.depends_on) or ():
                found = visit(reference)
                if found:
                    return found
        stack.pop()
        return ()

    for identifier in sorted(by_id):
        found = visit(identifier)
        if found:
            return found
    return ()


def _maximum_depth(nodes: Sequence[VerificationNode]) -> int:
    """Return the longest dependency chain length in the plan.

    Mirrors the cycle finder's identifier guard: malformed identifiers are
    already validator findings and never enter the graph.
    """
    by_id = {item.id: item for item in nodes if isinstance(item, VerificationNode) and isinstance(item.id, str)}
    memo: dict[str, int] = {}

    def depth(identifier: str) -> int:
        if identifier in memo:
            return memo[identifier]
        memo[identifier] = 0
        item = by_id.get(identifier)
        value = 0
        if item is not None:
            for reference in _strings(item.depends_on) or ():
                value = max(value, depth(reference) + 1)
        memo[identifier] = value
        return value

    return max((depth(identifier) for identifier in by_id), default=0)


def _index_receipts(
    trusted_evidence: TrustedEvidenceSnapshot | None,
    nodes: Sequence[VerificationNode],
) -> tuple[dict[str, EvidenceReceipt], list[str]]:
    """Index trusted receipts by node and report ambiguous or unknown bindings."""
    findings: list[str] = []
    receipts: dict[str, EvidenceReceipt] = {}
    if trusted_evidence is None:
        return receipts, findings
    if not isinstance(trusted_evidence, TrustedEvidenceSnapshot):
        return receipts, ["trusted evidence must be a TrustedEvidenceSnapshot record"]  # type: ignore[unreachable]
    if not isinstance(trusted_evidence.complete, bool):
        return receipts, ["trusted evidence snapshot completeness must be boolean"]  # type: ignore[unreachable]
    if not isinstance(trusted_evidence.snapshot_ref, str) or not trusted_evidence.snapshot_ref.strip():
        return receipts, ["trusted evidence snapshot_ref must be a non-empty string"]
    if len(trusted_evidence.snapshot_ref) > MAX_REFERENCE_LENGTH:
        return receipts, ["trusted evidence snapshot_ref exceeds the bounded length"]
    raw_receipts: object = trusted_evidence.receipts
    if not isinstance(raw_receipts, Sequence) or isinstance(raw_receipts, (str, bytes, bytearray)):
        return receipts, ["trusted evidence receipts must be an array of EvidenceReceipt records"]
    # Malformed identifiers are validator findings; they never enter this set,
    # so an unhashable id cannot crash receipt indexing.
    known = {item.id for item in nodes if isinstance(item, VerificationNode) and isinstance(item.id, str)}
    for receipt in raw_receipts:
        if not isinstance(receipt, EvidenceReceipt):
            findings.append("trusted evidence receipts must be EvidenceReceipt records")
            continue
        shape_findings: list[str] = []
        for field_name, value in (
            ("evidence_ref", receipt.evidence_ref),
            ("node_id", receipt.node_id),
            ("status", receipt.status),
            ("candidate_revision", receipt.candidate_revision),
            ("policy_revision", receipt.policy_revision),
        ):
            if not isinstance(value, str) or not value.strip():
                shape_findings.append(f"trusted evidence {field_name} must be a non-empty string")
        subject_refs = _strings(receipt.subject_refs)
        if subject_refs is None:
            shape_findings.append(f"trusted evidence {receipt.evidence_ref} subject_refs must be an array of strings")
        elif len(subject_refs) > MAX_SUBJECT_REFS:
            shape_findings.append(f"trusted evidence {receipt.evidence_ref} subject_refs exceed the bounded count")
        elif any(len(reference) > MAX_REFERENCE_LENGTH for reference in subject_refs):
            shape_findings.append(f"trusted evidence {receipt.evidence_ref} subject_refs exceed the bounded length")
        for optional_field, optional_value in (
            ("base_revision", receipt.base_revision),
            ("contract_digest", receipt.contract_digest),
            ("environment_ref", receipt.environment_ref),
        ):
            if optional_value is not None and (not isinstance(optional_value, str) or not optional_value.strip()):
                shape_findings.append(f"trusted evidence {optional_field} must be a non-empty string or null")
        expires_at = receipt.expires_at_epoch
        if expires_at is not None and type(expires_at) is not int:
            shape_findings.append(
                f"trusted evidence {receipt.evidence_ref} expires_at_epoch must be an integer or null"
            )
        if shape_findings:
            findings.extend(shape_findings)
            continue
        assert isinstance(receipt.node_id, str) and isinstance(receipt.status, str)
        if receipt.node_id not in known:
            findings.append(f"trusted evidence {receipt.evidence_ref} targets an unknown node: {receipt.node_id}")
            continue
        if receipt.node_id in receipts:
            findings.append(f"duplicate evidence receipts for node: {receipt.node_id}")
            continue
        if receipt.status not in EVIDENCE_STATUSES:
            findings.append(f"trusted evidence {receipt.evidence_ref} has an unknown status: {receipt.status}")
            continue
        receipts[receipt.node_id] = receipt
    return receipts, findings


def _qualify(
    node: VerificationNode,
    receipt: EvidenceReceipt | None,
    *,
    policy: SchedulePolicy,
    changed_refs: set[str],
    current_candidate_revision: str,
    current_base_revision: str | None,
    current_contract_digest: str | None,
    now_epoch: int | None,
) -> tuple[str, ScheduleReason | None, tuple[str, ...]]:
    """Return (status, reason, invalidated_by) for one node's receipt."""
    if receipt is None:
        return ("ABSENT", None, ())
    if receipt.status in {"UNKNOWN", "NOT_EXECUTED"}:
        return ("ABSENT", ScheduleReason.EVIDENCE_STATUS_NON_GREEN, ())

    if node.candidate_bound and receipt.candidate_revision != current_candidate_revision:
        return ("STALE", ScheduleReason.EVIDENCE_CANDIDATE_MISMATCH, ())
    if (
        not node.candidate_bound
        and receipt.candidate_revision != current_candidate_revision
        and not policy.allow_subject_bound_reuse
    ):
        return ("STALE", ScheduleReason.EVIDENCE_CANDIDATE_MISMATCH, ())
    if node.base_bound and receipt.base_revision != current_base_revision:
        return ("STALE", ScheduleReason.EVIDENCE_BASE_MISMATCH, ())
    if current_contract_digest is None or receipt.contract_digest != current_contract_digest:
        # Evidence qualifies only under the exact current acceptance-contract
        # identity: a missing digest on either side is never a match.
        return ("STALE", ScheduleReason.EVIDENCE_CONTRACT_MISMATCH, ())
    if receipt.policy_revision != policy.policy_revision:
        return ("STALE", ScheduleReason.EVIDENCE_POLICY_MISMATCH, ())
    if node.validation_environment_ref is not None and receipt.environment_ref != node.validation_environment_ref:
        return ("STALE", ScheduleReason.EVIDENCE_ENVIRONMENT_MISMATCH, ())
    if receipt.expires_at_epoch is not None:
        if now_epoch is None:
            return ("STALE", ScheduleReason.EVIDENCE_EXPIRED, ())
        if receipt.expires_at_epoch <= now_epoch:
            return ("STALE", ScheduleReason.EVIDENCE_EXPIRED, ())
    if node.reusable_evidence_ref is not None and receipt.evidence_ref != node.reusable_evidence_ref:
        return ("STALE", ScheduleReason.DECLARED_EVIDENCE_MISMATCH, ())

    declared_kinds = {kind.partition(":")[0] for kind in node.invalidates_on}
    covered_kinds = {_subject_kind(reference) for reference in receipt.subject_refs}
    if declared_kinds - covered_kinds:
        return ("STALE", ScheduleReason.EVIDENCE_COVERAGE_UNKNOWN, ())

    changed = tuple(sorted(set(receipt.subject_refs) & changed_refs))
    if changed:
        return ("STALE", ScheduleReason.EVIDENCE_SUBJECT_CHANGED, changed)
    return (receipt.status, None, ())


def _failure_subject_state(node: VerificationNode) -> str:
    """Compare a reported failure subject with the current one."""
    subject = node.failure_subject
    if subject is None:
        return "MATCH"
    if subject.reported_candidate_ref != subject.current_candidate_ref:
        return "MISMATCH"
    if subject.reported_workflow_ref is None or subject.current_workflow_ref is None:
        return "UNKNOWN"
    if subject.reported_workflow_ref != subject.current_workflow_ref:
        return "MISMATCH"
    return "MATCH"


def plan_verification_schedule(
    nodes: Sequence[VerificationNode],
    *,
    policy: SchedulePolicy,
    trusted_evidence: TrustedEvidenceSnapshot | None = None,
    changed_refs: Sequence[str] = (),
    external_gate_status: Mapping[str, str] | None = None,
    planned_base_revision: str | None = None,
    current_base_revision: str | None = None,
    current_candidate_revision: str = "",
    current_contract_digest: str | None = None,
    now_epoch: int | None = None,
) -> VerificationSchedule:
    """Return the deterministic schedule for one verification plan."""
    blocking = list(validate_verification_schedule(nodes, policy))
    notes: list[str] = []
    receipts, receipt_findings = _index_receipts(trusted_evidence, nodes)
    blocking.extend(receipt_findings)
    if trusted_evidence is not None and isinstance(trusted_evidence, TrustedEvidenceSnapshot):
        if not trusted_evidence.complete:
            notes.append("trusted evidence snapshot is incomplete; reuse is not available")
    if external_gate_status is not None:
        if not isinstance(external_gate_status, Mapping):
            blocking.append("external gate status must be a mapping of node id to status")  # type: ignore[unreachable]
        else:
            for identifier, status in external_gate_status.items():
                if not isinstance(identifier, str) or not identifier.strip():
                    blocking.append("external gate status keys must be non-empty node identifiers")
                elif not isinstance(status, str):
                    blocking.append(f"external gate {identifier} status must be a string")  # type: ignore[unreachable]
                elif status not in EXTERNAL_GATE_STATUSES:
                    blocking.append(f"external gate {identifier} has an unknown status: {status}")
    if blocking:
        return _rejected(tuple(sorted(set(blocking))))

    items = [item for item in nodes if isinstance(item, VerificationNode)]
    by_id = {item.id: item for item in items}
    changed = {reference for reference in changed_refs if isinstance(reference, str) and reference.strip()}
    reuse_allowed = True
    if trusted_evidence is not None and isinstance(trusted_evidence, TrustedEvidenceSnapshot):
        reuse_allowed = trusted_evidence.complete

    qualifications: dict[str, tuple[str, ScheduleReason | None, tuple[str, ...]]] = {}
    for item in items:
        if not reuse_allowed:
            qualifications[item.id] = ("ABSENT", ScheduleReason.EVIDENCE_STATUS_NON_GREEN, ())
            continue
        status, reason, own_invalidated_by = _qualify(
            item,
            receipts.get(item.id),
            policy=policy,
            changed_refs=changed,
            current_candidate_revision=current_candidate_revision,
            current_base_revision=current_base_revision,
            current_contract_digest=current_contract_digest,
            now_epoch=now_epoch,
        )
        qualifications[item.id] = (status, reason, own_invalidated_by)
        if reason is ScheduleReason.EVIDENCE_COVERAGE_UNKNOWN:
            notes.append(f"{item.id}: current evidence does not declare coverage for every declared invalidation kind")

    invalidated: set[str] = {item.id for item in items if qualifications[item.id][0] == "STALE"}
    progressing = True
    while progressing:
        progressing = False
        for item in items:
            if item.id in invalidated:
                continue
            if any(reference in invalidated for reference in item.depends_on):
                invalidated.add(item.id)
                progressing = True

    invalidated_by: dict[str, tuple[str, ...]] = {}
    for item in items:
        own = qualifications[item.id][2]
        inherited = tuple(reference for reference in item.depends_on if reference in invalidated)
        invalidated_by[item.id] = tuple(sorted(set(own) | set(inherited)))

    dependents: dict[str, list[str]] = {item.id: [] for item in items}
    for item in items:
        for reference in item.depends_on:
            if reference in dependents:
                dependents[reference].append(item.id)

    memo: dict[str, _Resolution] = {}

    def resolve(identifier: str) -> _Resolution:
        if identifier in memo:
            return memo[identifier]
        item = by_id[identifier]
        memo[identifier] = _Resolution(_State.UNKNOWN, ScheduleReason.PREREQUISITE_UNKNOWN)
        dependency_results = [resolve(reference) for reference in item.depends_on]
        status, reason, _own_invalidated = qualifications[identifier]
        resolution = _resolve_node(
            item,
            dependency_results=dependency_results,
            status=status,
            reason=reason,
            evidence_ref=receipts[identifier].evidence_ref if identifier in receipts else None,
            invalidated=identifier in invalidated,
            invalidated_by=invalidated_by[identifier],
            policy=policy,
            external_gate_status=external_gate_status or {},
            planned_base_revision=planned_base_revision,
            current_base_revision=current_base_revision,
            dependents=dependents.get(identifier, ()),
        )
        memo[identifier] = resolution
        return resolution

    for item in items:
        resolve(item.id)

    candidate_order = _order_nodes(items, memo, policy)

    # First, propagate DEFER for external/pending dependencies (no window accounting yet)
    progressing = True
    while progressing:
        progressing = False
        for item in items:
            if memo[item.id].state is not _State.RUN:
                continue
            blocking_dependencies = tuple(
                reference
                for reference in item.depends_on
                if memo[reference].state in {_State.EXTERNAL_PENDING, _State.DEFER}
            )
            if blocking_dependencies:
                memo[item.id] = _Resolution(
                    _State.DEFER,
                    ScheduleReason.PREREQUISITE_PENDING,
                    blocked_by=blocking_dependencies,
                    invalidated_by=invalidated_by[item.id],
                )
                progressing = True

    # Now apply window accounting ONLY to nodes that are still RUN and whose
    # dependencies are all satisfied, so a parked prerequisite never makes its
    # dependents consume window budget they cannot legally spend. A skipped
    # dependent is deferred immediately, so its own dependents see the blocked
    # state instead of probing budget behind it.
    remaining_window = policy.hard_window_seconds
    for identifier in candidate_order:
        if memo[identifier].state is not _State.RUN:
            continue
        blocking_dependencies = tuple(
            reference
            for reference in by_id[identifier].depends_on
            if memo[reference].state in {_State.PARKED, _State.EXTERNAL_PENDING, _State.DEFER}
        )
        if blocking_dependencies:
            memo[identifier] = _Resolution(
                _State.DEFER,
                ScheduleReason.PREREQUISITE_PENDING,
                blocked_by=blocking_dependencies,
                invalidated_by=invalidated_by[identifier],
            )
            continue
        if remaining_window is None:
            continue
        item = by_id[identifier]
        profile = policy.duration_profiles.get(item.duration_profile_ref) if item.duration_profile_ref else None
        if profile is None or profile.expected_seconds is None:
            continue
        needed = profile.expected_seconds + policy.reconciliation_reserve_seconds
        if needed > remaining_window:
            memo[identifier] = _Resolution(
                _State.PARKED,
                ScheduleReason.INSUFFICIENT_EXECUTION_WINDOW,
                invalidated_by=invalidated_by[identifier],
            )
            continue
        remaining_window -= profile.expected_seconds

    # Re-propagate DEFER for nodes whose dependencies were PARKED
    progressing = True
    while progressing:
        progressing = False
        for item in items:
            if memo[item.id].state is not _State.RUN:
                continue
            blocking_dependencies = tuple(
                reference
                for reference in item.depends_on
                if memo[reference].state in {_State.PARKED, _State.EXTERNAL_PENDING, _State.DEFER}
            )
            if blocking_dependencies:
                memo[item.id] = _Resolution(
                    _State.DEFER,
                    ScheduleReason.PREREQUISITE_PENDING,
                    blocked_by=blocking_dependencies,
                    invalidated_by=invalidated_by[item.id],
                )
                progressing = True

    order = tuple(identifier for identifier in candidate_order if memo[identifier].state is _State.RUN)
    decisions: list[NodeDecision] = []
    for identifier in _decision_order(items, order):
        item = by_id[identifier]
        resolution = memo[identifier]
        decisions.append(
            NodeDecision(
                node_id=identifier,
                decision=_decision_of(resolution.state),
                reason=resolution.reason,
                next_action=_NEXT_ACTIONS.get(
                    resolution.reason,
                    "dispatch the node" if resolution.state is _State.RUN else "re-plan",
                ),
                depends_on=item.depends_on,
                blocked_by=resolution.blocked_by,
                invalidated_by=resolution.invalidated_by,
                reused_evidence_ref=resolution.reused_evidence_ref,
                duration_status=_duration_status(item, policy),
                estimated_seconds=_estimated_seconds(item, policy),
            )
        )

    required = tuple(item.id for item in items if item.required)
    executed = tuple(
        item.id for item in items if qualifications[item.id][0] in {"PASS", "FAIL"} and item.id not in invalidated
    )
    reused = tuple(item.id for item in items if memo[item.id].state is _State.REUSE)
    scheduled = tuple(item.id for item in items if memo[item.id].state is _State.RUN)
    missing = tuple(
        identifier
        for identifier in required
        if identifier not in executed and identifier not in reused and identifier not in scheduled
    )
    closure = VerificationClosure(
        required_node_refs=required,
        executed_node_refs=executed,
        reusable_current_evidence_refs=reused,
        scheduled_node_refs=scheduled,
        missing_node_refs=missing,
        complete=not missing,
    )
    resource_classes = sorted(
        {
            item.exclusive_resource_class
            for item in items
            if item.exclusive_resource_class is not None
            and sum(1 for other in items if other.exclusive_resource_class == item.exclusive_resource_class) > 1
        }
    )
    return VerificationSchedule(
        accepted=True,
        decisions=tuple(decisions),
        order=order,
        closure=closure,
        findings=tuple(sorted(set(blocking) | set(notes))),
        serialized_resource_classes=tuple(resource_classes),
    )


def _rejected(findings: tuple[str, ...]) -> VerificationSchedule:
    """Return a rejected schedule that never dispatches anything."""
    return VerificationSchedule(
        accepted=False,
        decisions=(),
        order=(),
        closure=VerificationClosure((), (), (), (), (), False),
        findings=findings,
    )


def _resolve_node(
    item: VerificationNode,
    *,
    dependency_results: Sequence[_Resolution],
    status: str,
    reason: ScheduleReason | None,
    evidence_ref: str | None,
    invalidated: bool,
    invalidated_by: tuple[str, ...],
    policy: SchedulePolicy,
    external_gate_status: Mapping[str, str],
    planned_base_revision: str | None,
    current_base_revision: str | None,
    dependents: Sequence[str],
) -> _Resolution:
    """Resolve one node's state from its dependencies, evidence and preconditions."""
    failed = tuple(
        reference
        for reference, result in zip(item.depends_on, dependency_results, strict=True)
        if result.state in {_State.FAIL, _State.BLOCKED}
    )
    if failed:
        return _Resolution(
            _State.BLOCKED,
            ScheduleReason.PREREQUISITE_FAILED,
            blocked_by=failed,
            invalidated_by=invalidated_by,
        )
    pending = tuple(
        reference
        for reference, result in zip(item.depends_on, dependency_results, strict=True)
        if result.state in {_State.PARKED, _State.EXTERNAL_PENDING, _State.DEFER}
    )
    if pending:
        return _Resolution(
            _State.DEFER,
            ScheduleReason.PREREQUISITE_PENDING,
            blocked_by=pending,
            invalidated_by=invalidated_by,
        )
    unknown = tuple(
        reference
        for reference, result in zip(item.depends_on, dependency_results, strict=True)
        if result.state is _State.UNKNOWN
    )
    if unknown:
        return _Resolution(
            _State.UNKNOWN,
            ScheduleReason.PREREQUISITE_UNKNOWN,
            blocked_by=unknown,
            invalidated_by=invalidated_by,
        )

    if (
        item.base_bound
        and planned_base_revision is not None
        and current_base_revision is not None
        and planned_base_revision != current_base_revision
    ):
        return _Resolution(
            _State.BLOCKED,
            ScheduleReason.STALE_CANDIDATE,
            invalidated_by=invalidated_by,
        )

    if status == "PASS" and not invalidated:
        return _Resolution(
            _State.REUSE,
            ScheduleReason.EVIDENCE_CURRENT,
            reused_evidence_ref=evidence_ref,
            invalidated_by=invalidated_by,
        )
    if status == "FAIL" and not invalidated:
        return _Resolution(
            _State.FAIL,
            ScheduleReason.OBSERVED_FAILURE,
            invalidated_by=invalidated_by,
        )

    external = external_gate_status.get(item.id)
    if external in {"NOT_EXECUTED", "UNAVAILABLE"}:
        return _Resolution(
            _State.EXTERNAL_PENDING,
            ScheduleReason.PROVIDER_NOT_EXECUTED,
            invalidated_by=invalidated_by,
        )

    if item.failure_subject is not None:
        subject_state = _failure_subject_state(item)
        if subject_state == "MISMATCH":
            return _Resolution(
                _State.BLOCKED,
                ScheduleReason.FAILURE_SUBJECT_MISMATCH,
                invalidated_by=invalidated_by,
            )
        if subject_state == "UNKNOWN":
            return _Resolution(
                _State.UNKNOWN,
                ScheduleReason.FAILURE_SUBJECT_UNKNOWN,
                invalidated_by=invalidated_by,
            )

    if item.probe_validity is not None:
        validity = item.probe_validity.validity
        if validity == "INVALID":
            return _Resolution(
                _State.BLOCKED,
                ScheduleReason.PROBE_VALIDITY_INVALID,
                invalidated_by=invalidated_by,
            )
        if validity == "UNKNOWN":
            return _Resolution(
                _State.UNKNOWN,
                ScheduleReason.PROBE_VALIDITY_UNKNOWN,
                invalidated_by=invalidated_by,
            )

    if item.release_worktree is not None:
        if item.release_worktree.committed_digest != item.release_worktree.worktree_digest:
            return _Resolution(
                _State.BLOCKED,
                ScheduleReason.RELEASE_WORKTREE_HEAD_MISMATCH,
                invalidated_by=invalidated_by,
            )

    if (
        not item.required
        and item.discrimination_class is DiscriminationClass.NONE
        and not dependents
        and not item.required_before
    ):
        return _Resolution(
            _State.ELIDED,
            ScheduleReason.OPTIONAL_ZERO_DISCRIMINATION,
            invalidated_by=invalidated_by,
        )

    if status == "STALE":
        return _Resolution(
            _State.RUN,
            reason or ScheduleReason.EVIDENCE_INVALIDATED,
            invalidated_by=invalidated_by,
        )
    return _Resolution(
        _State.RUN,
        ScheduleReason.EVIDENCE_REQUIRED,
        invalidated_by=invalidated_by,
    )


def _duration_status(item: VerificationNode, policy: SchedulePolicy) -> str:
    """Return the trusted duration status of one node."""
    if item.duration_profile_ref is None:
        return "NOT_APPLICABLE"
    profile = policy.duration_profiles.get(item.duration_profile_ref)
    if profile is None or profile.expected_seconds is None:
        return "UNKNOWN"
    return "KNOWN"


def _estimated_seconds(item: VerificationNode, policy: SchedulePolicy) -> int | None:
    """Return the trusted expected duration of one node, when known."""
    if item.duration_profile_ref is None:
        return None
    profile = policy.duration_profiles.get(item.duration_profile_ref)
    if profile is None:
        return None
    return profile.expected_seconds


def _order_nodes(
    items: Sequence[VerificationNode],
    memo: Mapping[str, _Resolution],
    policy: SchedulePolicy,
) -> tuple[str, ...]:
    """Return the deterministic dispatch order of the runnable nodes."""
    by_id = {item.id: item for item in items}
    remaining = {item.id for item in items if memo[item.id].state is _State.RUN}
    placed: set[str] = set()
    order: list[str] = []
    while remaining:
        ready = [
            identifier
            for identifier in remaining
            if all(
                reference in placed or memo[reference].state is _State.REUSE
                for reference in by_id[identifier].depends_on
            )
        ]
        if not ready:
            break
        chosen = min(ready, key=lambda identifier: _sort_key(by_id[identifier], policy))
        order.append(chosen)
        placed.add(chosen)
        remaining.discard(chosen)
    return tuple(order)


def _decision_order(items: Sequence[VerificationNode], order: Sequence[str]) -> tuple[str, ...]:
    """Return the deterministic reporting order of every scheduled node."""
    placed = set(order)
    return tuple(list(order) + sorted(item.id for item in items if item.id not in placed))


def _decision_of(state: _State) -> ScheduleDecision:
    """Map one internal state to its public scheduling decision."""
    if state is _State.RUN:
        return ScheduleDecision.RUN
    if state is _State.REUSE:
        return ScheduleDecision.REUSE_CURRENT
    if state is _State.DEFER:
        return ScheduleDecision.DEFER_UNTIL_DEPENDENCY
    if state in {_State.BLOCKED, _State.FAIL, _State.ELIDED, _State.PARKED}:
        return ScheduleDecision.NON_DISPATCH
    return ScheduleDecision.BLOCKED_UNKNOWN

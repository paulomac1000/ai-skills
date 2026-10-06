"""Provider-neutral autonomous repository integration authority helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class IntegrationLeaseState(StrEnum):
    ACTIVE = "ACTIVE"
    USED = "USED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class BasePolicy(StrEnum):
    EXACT = "exact"
    COMPATIBLE_ADVANCE = "compatible_advance"
    MERGE_QUEUE = "merge_queue"


class MergeStrategy(StrEnum):
    MERGE = "merge"
    SQUASH = "squash"
    REBASE = "rebase"
    FF_ONLY = "ff_only"


class IntegrationAdmissionDisposition(StrEnum):
    INTEGRATION_ADMITTED = "INTEGRATION_ADMITTED"
    STALE_CANDIDATE = "STALE_CANDIDATE"
    BASE_ADVANCED_COMPATIBLE = "BASE_ADVANCED_COMPATIBLE"
    BASE_TOPOLOGY_CHANGED = "BASE_TOPOLOGY_CHANGED"
    EVIDENCE_STALE = "EVIDENCE_STALE"
    LOST_AUTHORITY = "LOST_AUTHORITY"
    PROVIDER_BLOCKED = "PROVIDER_BLOCKED"
    LEASE_NOT_ACTIVE = "LEASE_NOT_ACTIVE"
    LEASE_EXPIRED = "LEASE_EXPIRED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class IntegrationOperationState(StrEnum):
    RESERVED = "RESERVED"
    DISPATCHED = "DISPATCHED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    INTEGRATED = "INTEGRATED"
    NOT_INTEGRATED = "NOT_INTEGRATED"


class DispatchObservation(StrEnum):
    ACKNOWLEDGED = "ACKNOWLEDGED"
    REJECTED = "REJECTED"
    DELIVERY_UNKNOWN = "DELIVERY_UNKNOWN"


def _require(value: str, name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{name} must be non-empty")


def _require_utc(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError(f"{name} must be timezone-aware UTC")


@dataclass(frozen=True)
class IntegrationLease:
    lease_id: str
    authority_principal_ref: str
    repository_ref: str
    change_ref: str | None
    candidate_head_sha: str
    candidate_tree_sha: str | None
    target_ref: str
    observed_base_sha: str
    base_policy: BasePolicy
    merge_strategy: MergeStrategy
    required_evidence_set_digest: str
    review_policy_revision: str | None
    verification_policy_revision: str | None
    autonomy_policy_revision: str
    execution_generation: str
    issued_at: datetime
    expires_at: datetime
    state: IntegrationLeaseState = IntegrationLeaseState.ACTIVE
    consumed_by_operation_ref: str | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.lease_id, "lease_id"),
            (self.authority_principal_ref, "authority_principal_ref"),
            (self.repository_ref, "repository_ref"),
            (self.candidate_head_sha, "candidate_head_sha"),
            (self.target_ref, "target_ref"),
            (self.observed_base_sha, "observed_base_sha"),
            (self.required_evidence_set_digest, "required_evidence_set_digest"),
            (self.autonomy_policy_revision, "autonomy_policy_revision"),
            (self.execution_generation, "execution_generation"),
        ):
            _require(value, name)
        if self.change_ref is not None:
            _require(self.change_ref, "change_ref")
        if self.candidate_tree_sha is not None:
            _require(self.candidate_tree_sha, "candidate_tree_sha")
        if self.review_policy_revision is not None:
            _require(self.review_policy_revision, "review_policy_revision")
        if self.verification_policy_revision is not None:
            _require(self.verification_policy_revision, "verification_policy_revision")
        _require_utc(self.issued_at, "issued_at")
        _require_utc(self.expires_at, "expires_at")
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be after issued_at")
        if self.state is IntegrationLeaseState.USED:
            if self.consumed_by_operation_ref is None:
                raise ValueError("used lease requires consumed_by_operation_ref")
            _require(self.consumed_by_operation_ref, "consumed_by_operation_ref")
        elif self.consumed_by_operation_ref is not None:
            raise ValueError("only a used lease may bind consumed_by_operation_ref")


@dataclass(frozen=True)
class IntegrationEvidenceSnapshot:
    evidence_set_digest: str
    review_ref: str | None
    review_current: bool
    verification_ref: str | None
    verification_current: bool
    review_policy_revision: str | None
    verification_policy_revision: str | None

    def __post_init__(self) -> None:
        _require(self.evidence_set_digest, "evidence_set_digest")
        for value, name in (
            (self.review_ref, "review_ref"),
            (self.verification_ref, "verification_ref"),
            (self.review_policy_revision, "review_policy_revision"),
            (self.verification_policy_revision, "verification_policy_revision"),
        ):
            if value is not None:
                _require(value, name)


@dataclass(frozen=True)
class IntegrationRepositoryState:
    repository_ref: str
    change_ref: str | None
    current_head_sha: str
    current_tree_sha: str | None
    current_target_ref: str
    current_base_sha: str
    base_advance_compatible: bool | None
    provider_allows_integration: bool | None
    execution_generation: str
    current_autonomy_policy_revision: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.repository_ref, "repository_ref"),
            (self.current_head_sha, "current_head_sha"),
            (self.current_target_ref, "current_target_ref"),
            (self.current_base_sha, "current_base_sha"),
            (self.execution_generation, "execution_generation"),
            (self.current_autonomy_policy_revision, "current_autonomy_policy_revision"),
        ):
            _require(value, name)
        if self.change_ref is not None:
            _require(self.change_ref, "change_ref")
        if self.current_tree_sha is not None:
            _require(self.current_tree_sha, "current_tree_sha")


@dataclass(frozen=True)
class IntegrationAdmission:
    disposition: IntegrationAdmissionDisposition
    lease_id: str
    operation_may_dispatch: bool
    reason: str


@dataclass(frozen=True)
class IntegrationOperation:
    operation_ref: str
    lease_id: str
    repository_ref: str
    change_ref: str | None
    candidate_sha: str
    candidate_tree_sha: str | None
    target_ref: str
    target_before_sha: str
    merge_strategy: MergeStrategy
    evidence_set_digest: str
    review_policy_revision: str | None
    verification_policy_revision: str | None
    autonomy_policy_revision: str
    execution_generation: str
    state: IntegrationOperationState = IntegrationOperationState.RESERVED

    def __post_init__(self) -> None:
        for value, name in (
            (self.operation_ref, "operation_ref"),
            (self.lease_id, "lease_id"),
            (self.repository_ref, "repository_ref"),
            (self.candidate_sha, "candidate_sha"),
            (self.target_ref, "target_ref"),
            (self.target_before_sha, "target_before_sha"),
            (self.evidence_set_digest, "evidence_set_digest"),
            (self.autonomy_policy_revision, "autonomy_policy_revision"),
            (self.execution_generation, "execution_generation"),
        ):
            _require(value, name)
        if self.change_ref is not None:
            _require(self.change_ref, "change_ref")
        if self.candidate_tree_sha is not None:
            _require(self.candidate_tree_sha, "candidate_tree_sha")
        if self.review_policy_revision is not None:
            _require(self.review_policy_revision, "review_policy_revision")
        if self.verification_policy_revision is not None:
            _require(self.verification_policy_revision, "verification_policy_revision")


@dataclass(frozen=True)
class IntegrationObservation:
    change_ref: str | None
    observed_candidate_sha: str | None
    target_ref: str
    target_before_sha: str
    target_after_sha: str | None
    integrated: bool | None
    integrated_sha: str | None

    def __post_init__(self) -> None:
        _require(self.target_ref, "target_ref")
        _require(self.target_before_sha, "target_before_sha")
        for value, name in (
            (self.change_ref, "change_ref"),
            (self.observed_candidate_sha, "observed_candidate_sha"),
            (self.target_after_sha, "target_after_sha"),
            (self.integrated_sha, "integrated_sha"),
        ):
            if value is not None:
                _require(value, name)


@dataclass(frozen=True)
class IntegrationResult:
    lease_ref: str
    operation_ref: str
    repository_ref: str
    change_ref: str | None
    candidate_sha: str
    candidate_tree_sha: str | None
    integrated_sha: str
    target_ref: str
    observed_target_before: str
    observed_target_after: str
    merge_strategy: MergeStrategy
    evidence_set_digest: str
    review_policy_revision: str | None
    verification_policy_revision: str | None
    autonomy_policy_revision: str
    lineage_proof_ref: str



def _evidence_current(lease: IntegrationLease, evidence: IntegrationEvidenceSnapshot) -> bool:
    if evidence.evidence_set_digest != lease.required_evidence_set_digest:
        return False
    if lease.review_policy_revision is not None:
        if (
            evidence.review_ref is None
            or not evidence.review_current
            or evidence.review_policy_revision != lease.review_policy_revision
        ):
            return False
    if lease.verification_policy_revision is not None:
        if (
            evidence.verification_ref is None
            or not evidence.verification_current
            or evidence.verification_policy_revision != lease.verification_policy_revision
        ):
            return False
    return True


def admit_integration(
    lease: IntegrationLease,
    *,
    acting_principal_ref: str,
    now: datetime,
    repository: IntegrationRepositoryState,
    evidence: IntegrationEvidenceSnapshot,
) -> IntegrationAdmission:
    """Re-read exact authority/candidate/base/evidence facts immediately before integration."""
    _require(acting_principal_ref, "acting_principal_ref")
    _require_utc(now, "now")
    if lease.state is not IntegrationLeaseState.ACTIVE:
        return IntegrationAdmission(
            IntegrationAdmissionDisposition.LEASE_NOT_ACTIVE,
            lease.lease_id,
            False,
            f"lease state is {lease.state.value}",
        )
    if now >= lease.expires_at:
        return IntegrationAdmission(
            IntegrationAdmissionDisposition.LEASE_EXPIRED,
            lease.lease_id,
            False,
            "lease expired before mutation admission",
        )
    if acting_principal_ref != lease.authority_principal_ref:
        return IntegrationAdmission(
            IntegrationAdmissionDisposition.LOST_AUTHORITY,
            lease.lease_id,
            False,
            "acting principal is not the lease authority principal",
        )
    if repository.execution_generation != lease.execution_generation:
        return IntegrationAdmission(
            IntegrationAdmissionDisposition.LOST_AUTHORITY,
            lease.lease_id,
            False,
            "execution generation changed",
        )
    if repository.current_autonomy_policy_revision != lease.autonomy_policy_revision:
        return IntegrationAdmission(
            IntegrationAdmissionDisposition.LOST_AUTHORITY,
            lease.lease_id,
            False,
            "autonomy policy revision changed",
        )
    if repository.repository_ref != lease.repository_ref:
        return IntegrationAdmission(
            IntegrationAdmissionDisposition.LOST_AUTHORITY,
            lease.lease_id,
            False,
            "repository identity changed",
        )
    if repository.change_ref != lease.change_ref:
        return IntegrationAdmission(
            IntegrationAdmissionDisposition.STALE_CANDIDATE,
            lease.lease_id,
            False,
            "change identity changed",
        )
    if repository.current_target_ref != lease.target_ref:
        return IntegrationAdmission(
            IntegrationAdmissionDisposition.BASE_TOPOLOGY_CHANGED,
            lease.lease_id,
            False,
            "target ref changed",
        )
    if repository.current_head_sha != lease.candidate_head_sha:
        return IntegrationAdmission(
            IntegrationAdmissionDisposition.STALE_CANDIDATE,
            lease.lease_id,
            False,
            "candidate head changed",
        )
    if lease.candidate_tree_sha is not None and repository.current_tree_sha != lease.candidate_tree_sha:
        return IntegrationAdmission(
            IntegrationAdmissionDisposition.STALE_CANDIDATE,
            lease.lease_id,
            False,
            "candidate tree changed or cannot be proven",
        )
    if repository.current_base_sha != lease.observed_base_sha:
        if lease.base_policy is BasePolicy.COMPATIBLE_ADVANCE and repository.base_advance_compatible is True:
            return IntegrationAdmission(
                IntegrationAdmissionDisposition.BASE_ADVANCED_COMPATIBLE,
                lease.lease_id,
                False,
                "compatible base advance requires explicit policy handling/re-admission",
            )
        return IntegrationAdmission(
            IntegrationAdmissionDisposition.BASE_TOPOLOGY_CHANGED,
            lease.lease_id,
            False,
            "target/base moved from the lease snapshot",
        )
    if not _evidence_current(lease, evidence):
        return IntegrationAdmission(
            IntegrationAdmissionDisposition.EVIDENCE_STALE,
            lease.lease_id,
            False,
            "required evidence or policy revision is missing/stale",
        )
    if repository.provider_allows_integration is not True:
        return IntegrationAdmission(
            IntegrationAdmissionDisposition.PROVIDER_BLOCKED,
            lease.lease_id,
            False,
            "authoritative provider controls do not currently admit integration",
        )
    return IntegrationAdmission(
        IntegrationAdmissionDisposition.INTEGRATION_ADMITTED,
        lease.lease_id,
        True,
        "exact authority, candidate, base, evidence, policy and provider controls are current",
    )


def admit_and_reserve_integration(
    lease: IntegrationLease,
    *,
    acting_principal_ref: str,
    now: datetime,
    repository: IntegrationRepositoryState,
    evidence: IntegrationEvidenceSnapshot,
    operation_ref: str,
) -> tuple[IntegrationAdmission, IntegrationLease, IntegrationOperation | None]:
    """Atomically derive mutation admission and consume one-shot authority for one operation."""
    _require(operation_ref, "operation_ref")
    admission = admit_integration(
        lease,
        acting_principal_ref=acting_principal_ref,
        now=now,
        repository=repository,
        evidence=evidence,
    )
    if not admission.operation_may_dispatch:
        return admission, lease, None
    operation = IntegrationOperation(
        operation_ref=operation_ref,
        lease_id=lease.lease_id,
        repository_ref=lease.repository_ref,
        change_ref=lease.change_ref,
        candidate_sha=lease.candidate_head_sha,
        candidate_tree_sha=lease.candidate_tree_sha,
        target_ref=lease.target_ref,
        target_before_sha=repository.current_base_sha,
        merge_strategy=lease.merge_strategy,
        evidence_set_digest=lease.required_evidence_set_digest,
        review_policy_revision=lease.review_policy_revision,
        verification_policy_revision=lease.verification_policy_revision,
        autonomy_policy_revision=lease.autonomy_policy_revision,
        execution_generation=lease.execution_generation,
    )
    consumed_lease = replace(
        lease,
        state=IntegrationLeaseState.USED,
        consumed_by_operation_ref=operation_ref,
    )
    return admission, consumed_lease, operation

def note_dispatch(
    operation: IntegrationOperation,
    observation: DispatchObservation,
) -> IntegrationOperation:
    """Record dispatch acknowledgement without interpreting transport failure as replay authority."""
    if operation.state is not IntegrationOperationState.RESERVED:
        raise ValueError("operation may be dispatched only once from RESERVED")
    if observation is DispatchObservation.DELIVERY_UNKNOWN:
        return replace(operation, state=IntegrationOperationState.RECONCILIATION_REQUIRED)
    if observation is DispatchObservation.REJECTED:
        return replace(operation, state=IntegrationOperationState.NOT_INTEGRATED)
    return replace(operation, state=IntegrationOperationState.DISPATCHED)


def reconcile_integration(
    operation: IntegrationOperation,
    observation: IntegrationObservation,
    *,
    lineage_proof_ref: str | None,
) -> tuple[IntegrationOperation, IntegrationResult | None]:
    """Reconcile authoritative provider/ref state before any replay after ambiguous delivery."""
    if observation.target_ref != operation.target_ref:
        return (
            replace(operation, state=IntegrationOperationState.RECONCILIATION_REQUIRED),
            None,
        )
    if observation.change_ref != operation.change_ref:
        return (
            replace(operation, state=IntegrationOperationState.RECONCILIATION_REQUIRED),
            None,
        )
    if observation.observed_candidate_sha not in {None, operation.candidate_sha}:
        return (
            replace(operation, state=IntegrationOperationState.RECONCILIATION_REQUIRED),
            None,
        )
    if observation.integrated is None:
        return (
            replace(operation, state=IntegrationOperationState.RECONCILIATION_REQUIRED),
            None,
        )
    if observation.integrated is False:
        return replace(operation, state=IntegrationOperationState.NOT_INTEGRATED), None
    if observation.observed_candidate_sha != operation.candidate_sha:
        return (
            replace(operation, state=IntegrationOperationState.RECONCILIATION_REQUIRED),
            None,
        )
    if not observation.integrated_sha or observation.target_after_sha != observation.integrated_sha:
        return (
            replace(operation, state=IntegrationOperationState.RECONCILIATION_REQUIRED),
            None,
        )
    if observation.target_before_sha != operation.target_before_sha:
        return (
            replace(operation, state=IntegrationOperationState.RECONCILIATION_REQUIRED),
            None,
        )
    if lineage_proof_ref is None or not lineage_proof_ref.strip():
        return (
            replace(operation, state=IntegrationOperationState.RECONCILIATION_REQUIRED),
            None,
        )
    result = IntegrationResult(
        lease_ref=operation.lease_id,
        operation_ref=operation.operation_ref,
        repository_ref=operation.repository_ref,
        change_ref=operation.change_ref,
        candidate_sha=operation.candidate_sha,
        candidate_tree_sha=operation.candidate_tree_sha,
        integrated_sha=observation.integrated_sha,
        target_ref=operation.target_ref,
        observed_target_before=operation.target_before_sha,
        observed_target_after=observation.target_after_sha,
        merge_strategy=operation.merge_strategy,
        evidence_set_digest=operation.evidence_set_digest,
        review_policy_revision=operation.review_policy_revision,
        verification_policy_revision=operation.verification_policy_revision,
        autonomy_policy_revision=operation.autonomy_policy_revision,
        lineage_proof_ref=lineage_proof_ref,
    )
    return replace(operation, state=IntegrationOperationState.INTEGRATED), result


def to_integration_receipt_projection(result: IntegrationResult) -> dict[str, Any]:
    """Project a bounded provider-neutral shape suitable for an execution-evidence adapter."""
    return {
        "receiptKind": "integration",
        "repositoryRef": result.repository_ref,
        "changeRef": result.change_ref,
        "leaseRef": result.lease_ref,
        "operationRef": result.operation_ref,
        "candidateSha": result.candidate_sha,
        "candidateTreeSha": result.candidate_tree_sha,
        "integratedSha": result.integrated_sha,
        "targetRef": result.target_ref,
        "observedTargetBefore": result.observed_target_before,
        "observedTargetAfter": result.observed_target_after,
        "mergeStrategy": result.merge_strategy.value,
        "evidenceSetDigest": result.evidence_set_digest,
        "reviewPolicyRevision": result.review_policy_revision,
        "verificationPolicyRevision": result.verification_policy_revision,
        "autonomyPolicyRevision": result.autonomy_policy_revision,
        "lineageProofRef": result.lineage_proof_ref,
    }
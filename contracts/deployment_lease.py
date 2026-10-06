#!/usr/bin/env python3
"""Reference admission checks for exact, one-use and target-fenced deployment leases."""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

FULL_REVISION = re.compile(r"^[0-9a-fA-F]{40}$")


class DeploymentLeaseError(ValueError):
    """Raised when a lease cannot authorize the exact requested mutation."""


@dataclass(frozen=True)
class LeaseAdmission:
    lease_id: str
    principal: str
    session: str | None
    action: str
    artifact_digest: str
    target_project: str
    target_environment: str
    target_resource: str
    policy_revision: str
    source_revision: str | None


def _utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise DeploymentLeaseError(f"invalid lease timestamp: {value}") from error
    if parsed.tzinfo is None:
        raise DeploymentLeaseError("lease timestamps must include a timezone")
    return parsed.astimezone(UTC)


def _target_dimension(target: Mapping[str, Any], field: str, *, label: str) -> str:
    value = target.get(field)
    if not isinstance(value, str) or not value:
        raise DeploymentLeaseError(f"{label} target.{field} is required")
    return value


def admit_lease(
    lease: Mapping[str, Any],
    *,
    principal: str,
    target: Mapping[str, str],
    artifact_digest: str,
    action: str,
    normalized_args_digest: str,
    policy_revision: str,
    now: datetime,
    source_revision: str | None = None,
    session: str | None = None,
    consumed_lease_ids: Collection[str] = (),
) -> LeaseAdmission:
    """Admit only an active, unconsumed lease matching every protected dimension exactly."""
    if not policy_revision:
        raise DeploymentLeaseError("current policy_revision is required")
    if source_revision is not None and FULL_REVISION.fullmatch(source_revision) is None:
        raise DeploymentLeaseError("current source_revision must be an immutable full revision")

    lease_id = str(lease.get("lease_id") or "")
    if not lease_id:
        raise DeploymentLeaseError("lease_id is required")
    if lease_id in consumed_lease_ids:
        raise DeploymentLeaseError("deployment lease was already consumed")
    if lease.get("state") != "active":
        raise DeploymentLeaseError(f"deployment lease is not active: {lease.get('state')}")

    if now.tzinfo is None:
        raise DeploymentLeaseError("current time must include a timezone")
    instant = now.astimezone(UTC)
    issued_at = _utc(str(lease.get("issued_at") or ""))
    expires_at = _utc(str(lease.get("expires_at") or ""))
    if issued_at > instant:
        raise DeploymentLeaseError("deployment lease is not active yet")
    if expires_at <= instant:
        raise DeploymentLeaseError("deployment lease is expired")

    checks = {
        "principal": (lease.get("principal"), principal),
        "artifact_digest": (lease.get("artifact_digest"), artifact_digest),
        "action": (lease.get("action"), action),
        "normalized_args_digest": (lease.get("normalized_args_digest"), normalized_args_digest),
        "policy_revision": (lease.get("policy_revision"), policy_revision),
    }
    for field, (actual, expected) in checks.items():
        if actual != expected:
            raise DeploymentLeaseError(f"deployment lease {field} does not match requested operation")

    lease_session = lease.get("session")
    if lease_session is not None:
        if not isinstance(lease_session, str) or not lease_session:
            raise DeploymentLeaseError("deployment lease session must be a non-empty string when present")
        if session != lease_session:
            raise DeploymentLeaseError("deployment lease session does not match current session")

    lease_target = lease.get("target")
    if not isinstance(lease_target, Mapping):
        raise DeploymentLeaseError("deployment lease target is missing")
    requested_dimensions = {
        field: _target_dimension(target, field, label="requested") for field in ("project", "environment", "resource")
    }
    lease_dimensions = {
        field: _target_dimension(lease_target, field, label="deployment lease")
        for field in ("project", "environment", "resource")
    }
    for field in ("project", "environment", "resource"):
        if lease_dimensions[field] != requested_dimensions[field]:
            raise DeploymentLeaseError(f"deployment lease target.{field} does not match requested target")

    lease_source_revision = lease.get("source_revision")
    if lease_source_revision is not None or source_revision is not None:
        if not isinstance(lease_source_revision, str) or FULL_REVISION.fullmatch(lease_source_revision) is None:
            raise DeploymentLeaseError("deployment lease source_revision is missing or invalid")
        if source_revision != lease_source_revision:
            raise DeploymentLeaseError("deployment lease source_revision does not match requested operation")

    return LeaseAdmission(
        lease_id=lease_id,
        principal=principal,
        session=session if lease_session is not None else None,
        action=action,
        artifact_digest=artifact_digest,
        target_project=requested_dimensions["project"],
        target_environment=requested_dimensions["environment"],
        target_resource=requested_dimensions["resource"],
        policy_revision=policy_revision,
        source_revision=source_revision,
    )


class FenceMode(StrEnum):
    PROVIDER_CAS = "provider_cas"
    BROKER_SINGLE_WRITER = "broker_single_writer"
    LEASE_GENERATION = "lease_generation"


class DeploymentAdmissionDisposition(StrEnum):
    TARGET_PRECONDITION_MATCH = "TARGET_PRECONDITION_MATCH"
    TARGET_ADVANCED_COMPATIBLE = "TARGET_ADVANCED_COMPATIBLE"
    TARGET_CHANGED = "TARGET_CHANGED"
    STALE_LEASE = "STALE_LEASE"
    CONFLICTING_MUTATION_ACTIVE = "CONFLICTING_MUTATION_ACTIVE"
    TARGET_STATE_UNKNOWN = "TARGET_STATE_UNKNOWN"
    LOST_AUTHORITY = "LOST_AUTHORITY"
    LEASE_NOT_ACTIVE = "LEASE_NOT_ACTIVE"
    LEASE_EXPIRED = "LEASE_EXPIRED"


def _require_text(value: str, name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{name} must be non-empty")


@dataclass(frozen=True)
class DeploymentTargetState:
    """Authoritative pre-dispatch state for one deployment mutation domain."""

    mutation_domain: str
    fence_token_or_generation: str
    deployment_generation: str | None = None
    runtime_instance_generation: str | None = None
    artifact_digest: str | None = None
    config_revision: str | None = None
    provider_revision_or_etag: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.mutation_domain, "mutation_domain")
        _require_text(self.fence_token_or_generation, "fence_token_or_generation")
        for value, name in (
            (self.deployment_generation, "deployment_generation"),
            (self.runtime_instance_generation, "runtime_instance_generation"),
            (self.artifact_digest, "artifact_digest"),
            (self.config_revision, "config_revision"),
            (self.provider_revision_or_etag, "provider_revision_or_etag"),
        ):
            if value is not None:
                _require_text(value, name)


@dataclass(frozen=True)
class MutationDomainSnapshot:
    """Durable broker/controller view used to serialize conflicting mutations."""

    target: DeploymentTargetState
    active_operation_ref: str | None = None
    active_lease_id: str | None = None
    unresolved_external_effect: bool = False

    def __post_init__(self) -> None:
        if (self.active_operation_ref is None) != (self.active_lease_id is None):
            raise ValueError("active operation and lease identity must be present together")
        if self.active_operation_ref is not None:
            _require_text(self.active_operation_ref, "active_operation_ref")
            assert self.active_lease_id is not None
            _require_text(self.active_lease_id, "active_lease_id")
        if self.unresolved_external_effect and self.active_operation_ref is None:
            raise ValueError("unresolved external effect requires an active operation identity")


@dataclass(frozen=True)
class DeploymentLeaseAuthorityRecord:
    """Lease loaded from an authority-controlled store or issuer adapter."""

    source_ref: str
    attestation_ref: str
    lease: Mapping[str, Any]

    def __post_init__(self) -> None:
        _require_text(self.source_ref, "source_ref")
        _require_text(self.attestation_ref, "attestation_ref")


DeploymentAuthorityVerifier = Callable[[DeploymentLeaseAuthorityRecord], bool]


@dataclass(frozen=True)
class FencedLeaseAdmission:
    disposition: DeploymentAdmissionDisposition
    lease_id: str
    mutation_domain: str | None
    operation_may_dispatch: bool
    reason: str
    fence_mode: FenceMode | None = None
    provider_precondition_token: str | None = None
    observed_target: DeploymentTargetState | None = None
    expected_target: DeploymentTargetState | None = None


@dataclass(frozen=True)
class DeploymentMutationReservation:
    operation_ref: str
    lease_id: str
    mutation_domain: str
    action: str
    artifact_digest: str
    fence_mode: FenceMode
    fence_token_or_generation: str
    observed_target: DeploymentTargetState

    def __post_init__(self) -> None:
        for value, name in (
            (self.operation_ref, "operation_ref"),
            (self.lease_id, "lease_id"),
            (self.mutation_domain, "mutation_domain"),
            (self.action, "action"),
            (self.artifact_digest, "artifact_digest"),
            (self.fence_token_or_generation, "fence_token_or_generation"),
        ):
            _require_text(value, name)


ReservationWriter = Callable[[MutationDomainSnapshot, DeploymentMutationReservation], bool]


def _fenced_shape(lease: Mapping[str, Any]) -> tuple[str, FenceMode, str, DeploymentTargetState]:
    if lease.get("schema_version") != 2:
        raise DeploymentLeaseError("target-fenced admission requires deployment lease schema_version 2")
    target = lease.get("target")
    if not isinstance(target, Mapping):
        raise DeploymentLeaseError("deployment lease target is missing")
    mutation_domain = _target_dimension(target, "mutation_domain", label="deployment lease")
    fence = lease.get("fence")
    if not isinstance(fence, Mapping):
        raise DeploymentLeaseError("deployment lease fence is required")
    try:
        fence_mode = FenceMode(str(fence.get("mode") or ""))
    except ValueError as error:
        raise DeploymentLeaseError("deployment lease fence.mode is invalid") from error
    token = fence.get("token_or_generation")
    if not isinstance(token, str) or not token:
        raise DeploymentLeaseError("deployment lease fence.token_or_generation is required")
    expected = lease.get("expected_current")
    if not isinstance(expected, Mapping):
        raise DeploymentLeaseError("deployment lease expected_current is required")
    dimensions = (
        "deployment_generation",
        "runtime_instance_generation",
        "artifact_digest",
        "config_revision",
        "provider_revision_or_etag",
    )
    non_null = [expected.get(field) for field in dimensions if expected.get(field) is not None]
    if not non_null:
        raise DeploymentLeaseError(
            "deployment lease expected_current is invalid: at least one target identity dimension is required"
        )
    if any(not isinstance(value, str) or not value.strip() for value in non_null):
        raise DeploymentLeaseError(
            "deployment lease expected_current is invalid: bound target identity dimensions must be non-empty strings"
        )
    expected_target = DeploymentTargetState(
        mutation_domain=mutation_domain,
        fence_token_or_generation=token,
        deployment_generation=expected.get("deployment_generation"),
        runtime_instance_generation=expected.get("runtime_instance_generation"),
        artifact_digest=expected.get("artifact_digest"),
        config_revision=expected.get("config_revision"),
        provider_revision_or_etag=expected.get("provider_revision_or_etag"),
    )
    return mutation_domain, fence_mode, token, expected_target


def _classify_target_precondition(
    expected: DeploymentTargetState,
    current: DeploymentTargetState,
    *,
    compatible_advancement_proof_ref: str | None,
) -> tuple[DeploymentAdmissionDisposition, str]:
    dimensions = (
        "deployment_generation",
        "runtime_instance_generation",
        "artifact_digest",
        "config_revision",
        "provider_revision_or_etag",
    )
    for field in dimensions:
        expected_value = getattr(expected, field)
        if expected_value is None:
            continue
        current_value = getattr(current, field)
        if current_value is None:
            return (
                DeploymentAdmissionDisposition.TARGET_STATE_UNKNOWN,
                f"authoritative target state does not expose required {field}",
            )
        if current_value != expected_value:
            if compatible_advancement_proof_ref is not None:
                return (
                    DeploymentAdmissionDisposition.TARGET_ADVANCED_COMPATIBLE,
                    f"target {field} advanced under an explicit compatibility proof; lease re-admission is required",
                )
            return DeploymentAdmissionDisposition.TARGET_CHANGED, f"target {field} changed from lease precondition"
    return DeploymentAdmissionDisposition.TARGET_PRECONDITION_MATCH, "target precondition and fence are current"


def admit_fenced_lease(
    authority_record: DeploymentLeaseAuthorityRecord,
    *,
    verify_authority_record: DeploymentAuthorityVerifier,
    principal: str,
    target: Mapping[str, str],
    artifact_digest: str,
    action: str,
    normalized_args_digest: str,
    policy_revision: str,
    now: datetime,
    domain_snapshot: MutationDomainSnapshot,
    source_revision: str | None = None,
    session: str | None = None,
    consumed_lease_ids: Collection[str] = (),
    compatible_advancement_proof_ref: str | None = None,
) -> FencedLeaseAdmission:
    """Re-read authority and exact target state before a v2 mutation may be reserved."""
    lease = authority_record.lease
    lease_id = str(lease.get("lease_id") or "")
    try:
        authority_current = verify_authority_record(authority_record)
    except Exception:
        authority_current = False
    if authority_current is not True:
        return FencedLeaseAdmission(
            DeploymentAdmissionDisposition.LOST_AUTHORITY,
            lease_id,
            None,
            False,
            "lease is not current in the trusted authority source",
        )
    try:
        base = admit_lease(
            lease,
            principal=principal,
            session=session,
            target=target,
            artifact_digest=artifact_digest,
            action=action,
            normalized_args_digest=normalized_args_digest,
            policy_revision=policy_revision,
            source_revision=source_revision,
            now=now,
            consumed_lease_ids=consumed_lease_ids,
        )
        mutation_domain, fence_mode, fence_token, expected = _fenced_shape(lease)
    except DeploymentLeaseError as error:
        text_value = str(error)
        if "expired" in text_value:
            disposition = DeploymentAdmissionDisposition.LEASE_EXPIRED
        elif "already consumed" in text_value or "not active" in text_value:
            disposition = DeploymentAdmissionDisposition.LEASE_NOT_ACTIVE
        else:
            disposition = DeploymentAdmissionDisposition.LOST_AUTHORITY
        return FencedLeaseAdmission(disposition, lease_id, None, False, text_value)

    requested_domain = target.get("mutation_domain")
    if requested_domain != mutation_domain:
        return FencedLeaseAdmission(
            DeploymentAdmissionDisposition.LOST_AUTHORITY,
            base.lease_id,
            mutation_domain,
            False,
            "deployment lease target.mutation_domain does not match requested mutation domain",
            fence_mode,
        )
    if domain_snapshot.target.mutation_domain != mutation_domain:
        return FencedLeaseAdmission(
            DeploymentAdmissionDisposition.TARGET_STATE_UNKNOWN,
            base.lease_id,
            mutation_domain,
            False,
            "authoritative snapshot belongs to a different mutation domain",
            fence_mode,
            expected_target=expected,
        )
    if domain_snapshot.active_operation_ref is not None:
        return FencedLeaseAdmission(
            DeploymentAdmissionDisposition.CONFLICTING_MUTATION_ACTIVE,
            base.lease_id,
            mutation_domain,
            False,
            "another mutation is active or awaiting reconciliation in this domain",
            fence_mode,
            fence_token,
            domain_snapshot.target,
            expected,
        )
    if domain_snapshot.target.fence_token_or_generation != fence_token:
        return FencedLeaseAdmission(
            DeploymentAdmissionDisposition.STALE_LEASE,
            base.lease_id,
            mutation_domain,
            False,
            "target fence token/generation advanced after lease issuance",
            fence_mode,
            fence_token,
            domain_snapshot.target,
            expected,
        )
    disposition, reason = _classify_target_precondition(
        expected,
        domain_snapshot.target,
        compatible_advancement_proof_ref=compatible_advancement_proof_ref,
    )
    return FencedLeaseAdmission(
        disposition,
        base.lease_id,
        mutation_domain,
        False,
        reason + "; atomic reservation is still required before dispatch",
        fence_mode,
        fence_token,
        domain_snapshot.target,
        expected,
    )


def admit_and_reserve_fenced_mutation(
    authority_record: DeploymentLeaseAuthorityRecord,
    *,
    verify_authority_record: DeploymentAuthorityVerifier,
    principal: str,
    target: Mapping[str, str],
    artifact_digest: str,
    action: str,
    normalized_args_digest: str,
    policy_revision: str,
    now: datetime,
    domain_snapshot: MutationDomainSnapshot,
    operation_ref: str,
    reserve_if_current: ReservationWriter,
    source_revision: str | None = None,
    session: str | None = None,
    consumed_lease_ids: Collection[str] = (),
    compatible_advancement_proof_ref: str | None = None,
) -> tuple[FencedLeaseAdmission, DeploymentMutationReservation | None]:
    """Atomically consume the lease and reserve its mutation domain before dispatch."""
    _require_text(operation_ref, "operation_ref")
    admission = admit_fenced_lease(
        authority_record,
        verify_authority_record=verify_authority_record,
        principal=principal,
        target=target,
        artifact_digest=artifact_digest,
        action=action,
        normalized_args_digest=normalized_args_digest,
        policy_revision=policy_revision,
        now=now,
        domain_snapshot=domain_snapshot,
        source_revision=source_revision,
        session=session,
        consumed_lease_ids=consumed_lease_ids,
        compatible_advancement_proof_ref=compatible_advancement_proof_ref,
    )
    if admission.disposition is not DeploymentAdmissionDisposition.TARGET_PRECONDITION_MATCH:
        return admission, None
    assert admission.mutation_domain is not None
    assert admission.fence_mode is not None
    assert admission.provider_precondition_token is not None
    assert admission.observed_target is not None
    reservation = DeploymentMutationReservation(
        operation_ref=operation_ref,
        lease_id=admission.lease_id,
        mutation_domain=admission.mutation_domain,
        action=action,
        artifact_digest=artifact_digest,
        fence_mode=admission.fence_mode,
        fence_token_or_generation=admission.provider_precondition_token,
        observed_target=admission.observed_target,
    )
    try:
        reserved = reserve_if_current(domain_snapshot, reservation)
    except Exception:
        reserved = False
    if reserved is not True:
        return (
            FencedLeaseAdmission(
                DeploymentAdmissionDisposition.CONFLICTING_MUTATION_ACTIVE,
                admission.lease_id,
                admission.mutation_domain,
                False,
                "atomic mutation-domain reservation lost a concurrent race",
                admission.fence_mode,
                admission.provider_precondition_token,
                admission.observed_target,
                admission.expected_target,
            ),
            None,
        )
    dispatch_admission = FencedLeaseAdmission(
        admission.disposition,
        admission.lease_id,
        admission.mutation_domain,
        True,
        "target precondition is current and the mutation domain is atomically reserved",
        admission.fence_mode,
        admission.provider_precondition_token,
        admission.observed_target,
        admission.expected_target,
    )
    return dispatch_admission, reservation


def snapshot_after_reservation(
    snapshot: MutationDomainSnapshot, reservation: DeploymentMutationReservation
) -> MutationDomainSnapshot:
    """Reference durable state produced by a successful reservation CAS."""
    if snapshot.target.mutation_domain != reservation.mutation_domain:
        raise ValueError("reservation mutation domain does not match snapshot")
    if snapshot.active_operation_ref is not None:
        raise ValueError("snapshot already has an active mutation")
    return MutationDomainSnapshot(
        target=snapshot.target,
        active_operation_ref=reservation.operation_ref,
        active_lease_id=reservation.lease_id,
        unresolved_external_effect=False,
    )


def reservation_may_dispatch(
    snapshot: MutationDomainSnapshot,
    reservation: DeploymentMutationReservation,
) -> bool:
    """Return whether this reservation is still the current non-ambiguous domain owner."""
    return (
        not snapshot.unresolved_external_effect
        and snapshot.active_operation_ref == reservation.operation_ref
        and snapshot.active_lease_id == reservation.lease_id
        and snapshot.target.mutation_domain == reservation.mutation_domain
        and snapshot.target.fence_token_or_generation == reservation.fence_token_or_generation
    )


def mark_delivery_unknown(snapshot: MutationDomainSnapshot, *, operation_ref: str) -> MutationDomainSnapshot:
    """Keep the mutation owner pressure-bearing until authoritative reconciliation."""
    if snapshot.active_operation_ref != operation_ref:
        raise ValueError("operation_ref does not own the mutation domain")
    return MutationDomainSnapshot(
        target=snapshot.target,
        active_operation_ref=snapshot.active_operation_ref,
        active_lease_id=snapshot.active_lease_id,
        unresolved_external_effect=True,
    )


def reconcile_mutation(
    snapshot: MutationDomainSnapshot,
    *,
    operation_ref: str,
    effect_applied: bool | None,
    observed_target: DeploymentTargetState | None,
) -> MutationDomainSnapshot:
    """Reconcile one reserved operation without inventing target advancement."""
    if snapshot.active_operation_ref != operation_ref:
        raise ValueError("operation_ref does not own the mutation domain")
    if effect_applied is None:
        return mark_delivery_unknown(snapshot, operation_ref=operation_ref)
    if effect_applied:
        if observed_target is None:
            raise ValueError("applied mutation requires authoritative observed target state")
        if observed_target.mutation_domain != snapshot.target.mutation_domain:
            raise ValueError("observed target mutation domain changed")
        if observed_target.fence_token_or_generation == snapshot.target.fence_token_or_generation:
            raise ValueError("applied mutation must advance the target fence token/generation")
        return MutationDomainSnapshot(target=observed_target)
    if observed_target is not None and observed_target != snapshot.target:
        raise ValueError("no-effect reconciliation cannot silently change target identity")
    return MutationDomainSnapshot(target=snapshot.target)


def fencing_audit_projection(
    admission: FencedLeaseAdmission,
    reservation: DeploymentMutationReservation | None,
    resulting_target: DeploymentTargetState | None = None,
) -> dict[str, object]:
    """Return bounded admission and resulting-target deployment-fencing evidence."""
    observed = admission.observed_target
    expected = admission.expected_target
    return {
        "leaseId": admission.lease_id,
        "mutationDomain": admission.mutation_domain,
        "disposition": admission.disposition.value,
        "fenceMode": admission.fence_mode.value if admission.fence_mode is not None else None,
        "expectedFenceTokenOrGeneration": admission.provider_precondition_token,
        "expectedDeploymentGeneration": expected.deployment_generation if expected is not None else None,
        "expectedRuntimeInstanceGeneration": (
            expected.runtime_instance_generation if expected is not None else None
        ),
        "expectedArtifactDigest": expected.artifact_digest if expected is not None else None,
        "expectedConfigRevision": expected.config_revision if expected is not None else None,
        "expectedProviderRevisionOrEtag": (
            expected.provider_revision_or_etag if expected is not None else None
        ),
        "observedFenceTokenOrGeneration": observed.fence_token_or_generation if observed is not None else None,
        "observedDeploymentGeneration": observed.deployment_generation if observed is not None else None,
        "observedRuntimeInstanceGeneration": observed.runtime_instance_generation if observed is not None else None,
        "observedArtifactDigest": observed.artifact_digest if observed is not None else None,
        "observedConfigRevision": observed.config_revision if observed is not None else None,
        "observedProviderRevisionOrEtag": observed.provider_revision_or_etag if observed is not None else None,
        "operationRef": reservation.operation_ref if reservation is not None else None,
        "action": reservation.action if reservation is not None else None,
        "resultingFenceTokenOrGeneration": (
            resulting_target.fence_token_or_generation if resulting_target is not None else None
        ),
        "resultingDeploymentGeneration": (
            resulting_target.deployment_generation if resulting_target is not None else None
        ),
        "resultingRuntimeInstanceGeneration": (
            resulting_target.runtime_instance_generation if resulting_target is not None else None
        ),
        "resultingArtifactDigest": resulting_target.artifact_digest if resulting_target is not None else None,
        "resultingConfigRevision": resulting_target.config_revision if resulting_target is not None else None,
        "resultingProviderRevisionOrEtag": (
            resulting_target.provider_revision_or_etag if resulting_target is not None else None
        ),
    }

"""Provider-neutral exact-artifact publication authority helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from collections.abc import Callable


class PublicationLeaseState(StrEnum):
    ACTIVE = "ACTIVE"
    USED = "USED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class PublicationAction(StrEnum):
    PUBLISH_PACKAGE = "publish_package"
    PROMOTE_DIGEST = "promote_digest"
    PUBLISH_RELEASE_ASSET = "publish_release_asset"
    MOVE_CHANNEL = "move_channel"


class PublicationAdmissionDisposition(StrEnum):
    AVAILABLE = "AVAILABLE"
    ALREADY_PRESENT_SAME_ARTIFACT = "ALREADY_PRESENT_SAME_ARTIFACT"
    ALREADY_PRESENT_DIFFERENT_ARTIFACT = "ALREADY_PRESENT_DIFFERENT_ARTIFACT"
    DESTINATION_UNKNOWN = "DESTINATION_UNKNOWN"
    LOST_AUTHORITY = "LOST_AUTHORITY"
    POLICY_STALE = "POLICY_STALE"
    EVIDENCE_STALE = "EVIDENCE_STALE"
    ARTIFACT_MISMATCH = "ARTIFACT_MISMATCH"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    PROVIDER_BLOCKED = "PROVIDER_BLOCKED"
    LEASE_NOT_ACTIVE = "LEASE_NOT_ACTIVE"
    LEASE_EXPIRED = "LEASE_EXPIRED"


class PublicationOperationState(StrEnum):
    RESERVED = "RESERVED"
    DISPATCHED = "DISPATCHED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    PUBLISHED = "PUBLISHED"
    NOT_PUBLISHED = "NOT_PUBLISHED"
    CONFLICT = "CONFLICT"


class DispatchObservation(StrEnum):
    ACKNOWLEDGED = "ACKNOWLEDGED"
    REJECTED_OR_CONFLICT = "REJECTED_OR_CONFLICT"
    DELIVERY_UNKNOWN = "DELIVERY_UNKNOWN"


class PublicationOutcome(StrEnum):
    PUBLISHED = "PUBLISHED"
    RECONCILED_ALREADY_PRESENT = "RECONCILED_ALREADY_PRESENT"


def _require(value: str, name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{name} must be non-empty")


def _require_utc(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{name} must be timezone-aware UTC")


def _validate_digest(value: str, name: str) -> None:
    _require(value, name)
    if ":" not in value:
        raise ValueError(f"{name} must include an algorithm prefix")


@dataclass(frozen=True)
class PublicationArtifact:
    artifact_ref: str
    artifact_digest: str
    media_or_package_type: str | None = None
    source_location_ref: str | None = None

    def __post_init__(self) -> None:
        _require(self.artifact_ref, "artifact_ref")
        _validate_digest(self.artifact_digest, "artifact_digest")
        if self.media_or_package_type is not None:
            _require(self.media_or_package_type, "media_or_package_type")
        if self.source_location_ref is not None:
            _require(self.source_location_ref, "source_location_ref")


@dataclass(frozen=True)
class PublicationDestination:
    provider_or_registry: str
    namespace: str
    package_or_repository: str
    version: str | None = None
    tags_or_channels: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value, name in (
            (self.provider_or_registry, "provider_or_registry"),
            (self.namespace, "namespace"),
            (self.package_or_repository, "package_or_repository"),
        ):
            _require(value, name)
        if self.version is not None:
            _require(self.version, "version")
        if any(not item.strip() for item in self.tags_or_channels):
            raise ValueError("tags_or_channels must contain non-empty values")
        if len(set(self.tags_or_channels)) != len(self.tags_or_channels):
            raise ValueError("tags_or_channels must be unique")
        object.__setattr__(self, "tags_or_channels", tuple(sorted(self.tags_or_channels)))


@dataclass(frozen=True)
class ArtifactPublicationLease:
    lease_id: str
    authority_principal_ref: str
    artifact: PublicationArtifact
    destination: PublicationDestination
    action: PublicationAction
    policy_revision: str
    required_evidence_set_digest: str
    execution_generation: str
    issued_at: datetime
    expires_at: datetime
    state: PublicationLeaseState = PublicationLeaseState.ACTIVE
    consumed_by_operation_ref: str | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.lease_id, "lease_id"),
            (self.authority_principal_ref, "authority_principal_ref"),
            (self.policy_revision, "policy_revision"),
            (self.required_evidence_set_digest, "required_evidence_set_digest"),
            (self.execution_generation, "execution_generation"),
        ):
            _require(value, name)
        _require_utc(self.issued_at, "issued_at")
        _require_utc(self.expires_at, "expires_at")
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be after issued_at")
        if self.state is PublicationLeaseState.USED:
            if self.consumed_by_operation_ref is None:
                raise ValueError("used lease requires consumed_by_operation_ref")
            _require(self.consumed_by_operation_ref, "consumed_by_operation_ref")
        elif self.consumed_by_operation_ref is not None:
            raise ValueError("only a used lease may bind consumed_by_operation_ref")


@dataclass(frozen=True)
class PublicationLeaseAuthorityRecord:
    source_ref: str
    attestation_ref: str
    lease: ArtifactPublicationLease

    def __post_init__(self) -> None:
        _require(self.source_ref, "source_ref")
        _require(self.attestation_ref, "attestation_ref")


PublicationAuthorityVerifier = Callable[[PublicationLeaseAuthorityRecord], bool]


@dataclass(frozen=True)
class PublicationEvidenceSnapshot:
    artifact_ref: str
    artifact_digest: str
    artifact_current: bool
    evidence_set_digest: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require(self.artifact_ref, "artifact_ref")
        _validate_digest(self.artifact_digest, "artifact_digest")
        _require(self.evidence_set_digest, "evidence_set_digest")
        if any(not item.strip() for item in self.evidence_refs):
            raise ValueError("evidence_refs must contain non-empty values")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("evidence_refs must be unique")


@dataclass(frozen=True)
class PublicationDestinationState:
    destination: PublicationDestination
    observable: bool | None
    existing_artifact_digest: str | None
    existing_provider_artifact_id: str | None
    channel_digests: tuple[tuple[str, str | None], ...]
    channels_observed_complete: bool
    provider_allows_publication: bool | None
    same_artifact_reconciliation_allowed: bool | None
    current_policy_revision: str
    execution_generation: str

    def __post_init__(self) -> None:
        _require(self.current_policy_revision, "current_policy_revision")
        _require(self.execution_generation, "execution_generation")
        if self.existing_artifact_digest is not None:
            _validate_digest(self.existing_artifact_digest, "existing_artifact_digest")
        if self.existing_provider_artifact_id is not None:
            _require(self.existing_provider_artifact_id, "existing_provider_artifact_id")
        seen: set[str] = set()
        for channel, digest in self.channel_digests:
            _require(channel, "channel")
            if channel in seen:
                raise ValueError("channel_digests must contain unique channel names")
            seen.add(channel)
            if digest is not None:
                _validate_digest(digest, "channel_digest")


@dataclass(frozen=True)
class PublicationAdmission:
    disposition: PublicationAdmissionDisposition
    lease_id: str
    operation_may_dispatch: bool
    may_complete_without_dispatch: bool
    reason: str


@dataclass(frozen=True)
class ArtifactPublicationOperation:
    operation_ref: str
    lease_ref: str
    artifact: PublicationArtifact
    destination: PublicationDestination
    action: PublicationAction
    policy_revision: str
    evidence_set_digest: str
    evidence_refs: tuple[str, ...]
    execution_generation: str
    channel_before_digests: tuple[tuple[str, str | None], ...]
    initial_disposition: PublicationAdmissionDisposition
    state: PublicationOperationState = PublicationOperationState.RESERVED

    def __post_init__(self) -> None:
        for value, name in (
            (self.operation_ref, "operation_ref"),
            (self.lease_ref, "lease_ref"),
            (self.policy_revision, "policy_revision"),
            (self.evidence_set_digest, "evidence_set_digest"),
            (self.execution_generation, "execution_generation"),
        ):
            _require(value, name)


@dataclass(frozen=True)
class PublicationDestinationObservation:
    destination: PublicationDestination
    observable: bool | None
    artifact_digest: str | None
    immutable_digest_or_provider_id: str | None
    channel_digests: tuple[tuple[str, str | None], ...]
    channels_observed_complete: bool

    def __post_init__(self) -> None:
        if self.artifact_digest is not None:
            _validate_digest(self.artifact_digest, "artifact_digest")
        if self.immutable_digest_or_provider_id is not None:
            _require(self.immutable_digest_or_provider_id, "immutable_digest_or_provider_id")
        seen: set[str] = set()
        for channel, digest in self.channel_digests:
            _require(channel, "channel")
            if channel in seen:
                raise ValueError("channel_digests must contain unique channel names")
            seen.add(channel)
            if digest is not None:
                _validate_digest(digest, "channel_digest")


@dataclass(frozen=True)
class ArtifactPublicationReceipt:
    artifact_ref: str
    artifact_digest: str
    destination: PublicationDestination
    immutable_digest_or_provider_id: str | None
    publication_operation_ref: str
    lease_ref: str
    policy_revision: str
    evidence_set_digest: str
    outcome: PublicationOutcome
    observed_at: datetime
    evidence_refs: tuple[str, ...]
    channel_before_digests: tuple[tuple[str, str | None], ...]
    channel_after_digests: tuple[tuple[str, str | None], ...]
    receipt_kind: str = "artifact_publication"

    def __post_init__(self) -> None:
        _require(self.artifact_ref, "artifact_ref")
        _validate_digest(self.artifact_digest, "artifact_digest")
        _require(self.publication_operation_ref, "publication_operation_ref")
        _require(self.lease_ref, "lease_ref")
        _require(self.policy_revision, "policy_revision")
        _require(self.evidence_set_digest, "evidence_set_digest")
        _require_utc(self.observed_at, "observed_at")


@dataclass(frozen=True)
class PublishedArtifactReference:
    artifact_ref: str
    artifact_digest: str
    destination: PublicationDestination
    immutable_digest_or_provider_id: str | None


def _channel_map(values: tuple[tuple[str, str | None], ...]) -> dict[str, str | None]:
    return dict(values)


def _requested_channels_current(
    destination: PublicationDestination,
    values: tuple[tuple[str, str | None], ...],
    *,
    complete: bool,
) -> bool:
    if not destination.tags_or_channels:
        return True
    if not complete:
        return False
    observed = _channel_map(values)
    return set(observed) == set(destination.tags_or_channels)


def _channels_point_to(
    destination: PublicationDestination,
    values: tuple[tuple[str, str | None], ...],
    digest: str,
) -> bool:
    if not destination.tags_or_channels:
        return True
    observed = _channel_map(values)
    return all(observed.get(channel) == digest for channel in destination.tags_or_channels)


def admit_publication(
    authority_record: PublicationLeaseAuthorityRecord,
    *,
    verify_authority_record: PublicationAuthorityVerifier,
    acting_principal_ref: str,
    now: datetime,
    evidence: PublicationEvidenceSnapshot,
    destination_state: PublicationDestinationState,
) -> PublicationAdmission:
    """Revalidate exact publication authority, artifact evidence, and destination state."""
    lease = authority_record.lease
    _require(acting_principal_ref, "acting_principal_ref")
    _require_utc(now, "now")
    try:
        authority_current = verify_authority_record(authority_record)
    except Exception:
        authority_current = False
    if authority_current is not True:
        return PublicationAdmission(
            PublicationAdmissionDisposition.LOST_AUTHORITY,
            lease.lease_id,
            False,
            False,
            "lease is not current in the trusted authority source",
        )
    if lease.state is not PublicationLeaseState.ACTIVE:
        return PublicationAdmission(
            PublicationAdmissionDisposition.LEASE_NOT_ACTIVE,
            lease.lease_id,
            False,
            False,
            f"lease state is {lease.state.value}",
        )
    if now >= lease.expires_at:
        return PublicationAdmission(
            PublicationAdmissionDisposition.LEASE_EXPIRED,
            lease.lease_id,
            False,
            False,
            "lease expired before publication admission",
        )
    if acting_principal_ref != lease.authority_principal_ref:
        return PublicationAdmission(
            PublicationAdmissionDisposition.LOST_AUTHORITY,
            lease.lease_id,
            False,
            False,
            "acting principal is not the lease authority principal",
        )
    if destination_state.execution_generation != lease.execution_generation:
        return PublicationAdmission(
            PublicationAdmissionDisposition.LOST_AUTHORITY,
            lease.lease_id,
            False,
            False,
            "execution generation changed",
        )
    if destination_state.current_policy_revision != lease.policy_revision:
        return PublicationAdmission(
            PublicationAdmissionDisposition.POLICY_STALE,
            lease.lease_id,
            False,
            False,
            "publication policy revision changed",
        )
    if (
        evidence.evidence_set_digest != lease.required_evidence_set_digest
        or not evidence.artifact_current
    ):
        return PublicationAdmission(
            PublicationAdmissionDisposition.EVIDENCE_STALE,
            lease.lease_id,
            False,
            False,
            "required artifact evidence is missing or stale",
        )
    if (
        evidence.artifact_ref != lease.artifact.artifact_ref
        or evidence.artifact_digest != lease.artifact.artifact_digest
    ):
        return PublicationAdmission(
            PublicationAdmissionDisposition.ARTIFACT_MISMATCH,
            lease.lease_id,
            False,
            False,
            "observed artifact identity does not match the lease",
        )
    if destination_state.destination != lease.destination:
        return PublicationAdmission(
            PublicationAdmissionDisposition.SCOPE_MISMATCH,
            lease.lease_id,
            False,
            False,
            "provider destination/version/channel scope differs from the lease",
        )
    if destination_state.observable is not True:
        return PublicationAdmission(
            PublicationAdmissionDisposition.DESTINATION_UNKNOWN,
            lease.lease_id,
            False,
            False,
            "authoritative destination state is not observable",
        )
    if not _requested_channels_current(
        lease.destination,
        destination_state.channel_digests,
        complete=destination_state.channels_observed_complete,
    ):
        return PublicationAdmission(
            PublicationAdmissionDisposition.DESTINATION_UNKNOWN,
            lease.lease_id,
            False,
            False,
            "requested mutable channel state is incomplete or ambiguous",
        )

    existing = destination_state.existing_artifact_digest
    if existing is not None and existing != lease.artifact.artifact_digest:
        return PublicationAdmission(
            PublicationAdmissionDisposition.ALREADY_PRESENT_DIFFERENT_ARTIFACT,
            lease.lease_id,
            False,
            False,
            "immutable destination identity already contains a different artifact",
        )

    if existing == lease.artifact.artifact_digest and _channels_point_to(
        lease.destination,
        destination_state.channel_digests,
        lease.artifact.artifact_digest,
    ):
        if destination_state.same_artifact_reconciliation_allowed is not True:
            return PublicationAdmission(
                PublicationAdmissionDisposition.PROVIDER_BLOCKED,
                lease.lease_id,
                False,
                False,
                "same-artifact convergence is not explicitly admitted by provider/policy",
            )
        return PublicationAdmission(
            PublicationAdmissionDisposition.ALREADY_PRESENT_SAME_ARTIFACT,
            lease.lease_id,
            False,
            True,
            "destination already contains the exact leased artifact and requested channels",
        )

    if destination_state.provider_allows_publication is not True:
        return PublicationAdmission(
            PublicationAdmissionDisposition.PROVIDER_BLOCKED,
            lease.lease_id,
            False,
            False,
            "authoritative provider controls do not currently admit publication",
        )

    return PublicationAdmission(
        PublicationAdmissionDisposition.AVAILABLE,
        lease.lease_id,
        True,
        False,
        "exact authority, artifact evidence, destination scope, policy, and provider controls are current",
    )


def admit_and_reserve_publication(
    authority_record: PublicationLeaseAuthorityRecord,
    *,
    verify_authority_record: PublicationAuthorityVerifier,
    acting_principal_ref: str,
    now: datetime,
    evidence: PublicationEvidenceSnapshot,
    destination_state: PublicationDestinationState,
    operation_ref: str,
) -> tuple[PublicationAdmission, ArtifactPublicationLease, ArtifactPublicationOperation | None]:
    """Atomically classify destination state and consume one-shot authority for this operation."""
    _require(operation_ref, "operation_ref")
    lease = authority_record.lease
    admission = admit_publication(
        authority_record,
        verify_authority_record=verify_authority_record,
        acting_principal_ref=acting_principal_ref,
        now=now,
        evidence=evidence,
        destination_state=destination_state,
    )
    if not (admission.operation_may_dispatch or admission.may_complete_without_dispatch):
        return admission, lease, None

    operation = ArtifactPublicationOperation(
        operation_ref=operation_ref,
        lease_ref=lease.lease_id,
        artifact=lease.artifact,
        destination=lease.destination,
        action=lease.action,
        policy_revision=lease.policy_revision,
        evidence_set_digest=lease.required_evidence_set_digest,
        evidence_refs=evidence.evidence_refs,
        execution_generation=lease.execution_generation,
        channel_before_digests=destination_state.channel_digests,
        initial_disposition=admission.disposition,
    )
    consumed = replace(
        lease,
        state=PublicationLeaseState.USED,
        consumed_by_operation_ref=operation_ref,
    )
    return admission, consumed, operation


def note_dispatch(
    operation: ArtifactPublicationOperation,
    observation: DispatchObservation,
    *,
    publisher_artifact: PublicationArtifact,
) -> ArtifactPublicationOperation:
    """Bind the privileged dispatch to the exact already-proven artifact actually opened by the publisher."""
    if operation.state is not PublicationOperationState.RESERVED:
        raise ValueError("publication operation may be dispatched only once from RESERVED")
    if operation.initial_disposition is not PublicationAdmissionDisposition.AVAILABLE:
        raise ValueError("already-satisfied publication must reconcile without provider dispatch")
    if publisher_artifact != operation.artifact:
        raise ValueError("publisher artifact identity differs from the reserved exact artifact")
    if observation is DispatchObservation.ACKNOWLEDGED:
        return replace(operation, state=PublicationOperationState.DISPATCHED)
    return replace(operation, state=PublicationOperationState.RECONCILIATION_REQUIRED)


def reconcile_publication(
    operation: ArtifactPublicationOperation,
    observation: PublicationDestinationObservation,
    *,
    observed_at: datetime,
) -> tuple[ArtifactPublicationOperation, ArtifactPublicationReceipt | None]:
    """Read back the exact destination before declaring publication success or any retry path."""
    _require_utc(observed_at, "observed_at")
    allowed = {
        PublicationOperationState.DISPATCHED,
        PublicationOperationState.RECONCILIATION_REQUIRED,
    }
    if (
        operation.state is PublicationOperationState.RESERVED
        and operation.initial_disposition
        is PublicationAdmissionDisposition.ALREADY_PRESENT_SAME_ARTIFACT
    ):
        allowed.add(PublicationOperationState.RESERVED)
    if operation.state not in allowed:
        raise ValueError("publication may reconcile only after dispatch or exact same-artifact preflight")

    if observation.destination != operation.destination or observation.observable is not True:
        return replace(operation, state=PublicationOperationState.RECONCILIATION_REQUIRED), None
    if not _requested_channels_current(
        operation.destination,
        observation.channel_digests,
        complete=observation.channels_observed_complete,
    ):
        return replace(operation, state=PublicationOperationState.RECONCILIATION_REQUIRED), None

    digest = observation.artifact_digest
    if digest is None:
        return replace(operation, state=PublicationOperationState.NOT_PUBLISHED), None
    if digest != operation.artifact.artifact_digest:
        return replace(operation, state=PublicationOperationState.CONFLICT), None
    if not _channels_point_to(operation.destination, observation.channel_digests, digest):
        return replace(operation, state=PublicationOperationState.RECONCILIATION_REQUIRED), None

    outcome = (
        PublicationOutcome.RECONCILED_ALREADY_PRESENT
        if operation.initial_disposition
        is PublicationAdmissionDisposition.ALREADY_PRESENT_SAME_ARTIFACT
        else PublicationOutcome.PUBLISHED
    )
    receipt = ArtifactPublicationReceipt(
        artifact_ref=operation.artifact.artifact_ref,
        artifact_digest=operation.artifact.artifact_digest,
        destination=operation.destination,
        immutable_digest_or_provider_id=observation.immutable_digest_or_provider_id,
        publication_operation_ref=operation.operation_ref,
        lease_ref=operation.lease_ref,
        policy_revision=operation.policy_revision,
        evidence_set_digest=operation.evidence_set_digest,
        outcome=outcome,
        observed_at=observed_at,
        evidence_refs=operation.evidence_refs,
        channel_before_digests=operation.channel_before_digests,
        channel_after_digests=observation.channel_digests,
    )
    return replace(operation, state=PublicationOperationState.PUBLISHED), receipt


def satisfies_artifact_accepted(
    receipt: ArtifactPublicationReceipt,
    *,
    artifact_digest: str,
    destination: PublicationDestination,
) -> bool:
    """Bounded composition point for a policy owner using terminalBoundary=artifact_accepted."""
    return (
        receipt.receipt_kind == "artifact_publication"
        and receipt.artifact_digest == artifact_digest
        and receipt.destination == destination
        and receipt.outcome
        in {
            PublicationOutcome.PUBLISHED,
            PublicationOutcome.RECONCILED_ALREADY_PRESENT,
        }
    )


def deployment_artifact_reference(
    receipt: ArtifactPublicationReceipt,
) -> PublishedArtifactReference:
    """Project exact published identity without carrying publication authority into deployment."""
    return PublishedArtifactReference(
        artifact_ref=receipt.artifact_ref,
        artifact_digest=receipt.artifact_digest,
        destination=receipt.destination,
        immutable_digest_or_provider_id=receipt.immutable_digest_or_provider_id,
    )

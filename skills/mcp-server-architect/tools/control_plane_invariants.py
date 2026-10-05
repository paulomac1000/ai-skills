"""Pure helpers for canonical-control-plane projection and identity invariants."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum


class ProjectionDeliveryState(StrEnum):
    PENDING = "PENDING"
    RECONCILE_REQUIRED = "RECONCILE_REQUIRED"
    CONFIRMED = "CONFIRMED"
    DISPROVEN = "DISPROVEN"


class EventIngressState(StrEnum):
    RECEIVED = "RECEIVED"
    RECONCILE_REQUIRED = "RECONCILE_REQUIRED"
    APPLIED = "APPLIED"
    NO_CHANGE = "NO_CHANGE"


@dataclass(frozen=True)
class ProjectionOutboxEntry:
    canonical_id: str
    projection_generation: str
    idempotency_key: str
    state: ProjectionDeliveryState = ProjectionDeliveryState.PENDING

    def __post_init__(self) -> None:
        if not self.canonical_id.strip() or not self.projection_generation.strip() or not self.idempotency_key.strip():
            raise ValueError("outbox identity fields must be non-empty")


@dataclass(frozen=True)
class CanonicalEntity:
    canonical_id: str
    owner: str
    projection_target: str
    transition_history: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.canonical_id.strip() or not self.owner.strip() or not self.projection_target.strip():
            raise ValueError("canonical entity identity fields must be non-empty")


@dataclass(frozen=True)
class ProviderScopedExternalIdentity:
    """External identity whose uniqueness scope is explicit instead of inferred from a local locator."""

    provider: str
    resource_kind: str
    resource_id: str
    provider_namespace: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.resource_kind.strip() or not self.resource_id.strip():
            raise ValueError("external identity fields must be non-empty")
        if any(not component.strip() for component in self.provider_namespace):
            raise ValueError("provider namespace components must be non-empty")
        if not self.provider_namespace:
            raise ValueError("external identity requires complete provider namespace")

    @property
    def binding_key(self) -> tuple[str, ...]:
        return (self.provider, *self.provider_namespace, self.resource_kind, self.resource_id)


@dataclass(frozen=True)
class ExternalBinding:
    """Keep canonical identity, provider identity, and recovery locator as separate concerns."""

    canonical_id: str
    external_identity: ProviderScopedExternalIdentity
    recovery_locator: str | None = None
    transition_history: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.canonical_id.strip():
            raise ValueError("canonical binding identity must be non-empty")
        if self.recovery_locator is not None and not self.recovery_locator.strip():
            raise ValueError("recovery locator must be non-empty when supplied")


@dataclass(frozen=True)
class EventIngressReceipt:
    """Durable receipt identity for one authenticated external delivery."""

    provider: str
    delivery_id: str
    event_kind: str
    external_identity: ProviderScopedExternalIdentity
    received_at: str
    source_scope: tuple[str, ...] = ()
    state: EventIngressState = EventIngressState.RECEIVED
    canonical_id: str | None = None
    authoritative_state_revision: str | None = None
    resource_generation: str | None = None

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.delivery_id.strip() or not self.event_kind.strip() or not self.received_at.strip():
            raise ValueError("event receipt identity fields must be non-empty")
        if self.provider != self.external_identity.provider:
            raise ValueError("event provider must match external resource provider")
        if any(not component.strip() for component in self.source_scope):
            raise ValueError("event source scope components must be non-empty")
        if not self.source_scope:
            raise ValueError("provider-scoped delivery identity requires source scope")

    @property
    def dedup_key(self) -> tuple[str, ...]:
        return (self.provider, *self.source_scope, self.delivery_id)

    @property
    def delivery_subject(self) -> tuple[object, ...]:
        return (self.dedup_key, self.event_kind, self.external_identity.binding_key)


def admit_event_receipt(
    existing: EventIngressReceipt | None,
    incoming: EventIngressReceipt,
) -> tuple[EventIngressReceipt, bool]:
    """Persist once by provider/source-scoped delivery identity; a retry reuses the durable receipt."""
    if incoming.state is not EventIngressState.RECEIVED:
        raise ValueError("only a newly received event may enter ingress admission")
    if existing is None:
        return incoming, True
    if existing.dedup_key != incoming.dedup_key:
        raise ValueError("existing receipt must use the incoming delivery dedup key")
    if existing.delivery_subject != incoming.delivery_subject:
        raise ValueError("delivery dedup identity collision changed event subject")
    return existing, False


def begin_event_reconciliation(receipt: EventIngressReceipt) -> EventIngressReceipt:
    """Event arrival is only a reconciliation trigger; it is never direct transition authority."""
    if receipt.state is EventIngressState.RECEIVED:
        return replace(receipt, state=EventIngressState.RECONCILE_REQUIRED)
    if receipt.state is EventIngressState.RECONCILE_REQUIRED:
        return receipt
    raise ValueError("terminal event receipt cannot begin another semantic effect")


def settle_event_reconciliation(
    receipt: EventIngressReceipt,
    *,
    canonical_id: str,
    authoritative_state_revision: str,
    policy_authorized: bool,
    expected_resource_generation: str,
    current_resource_generation: str,
    semantic_change: bool,
) -> EventIngressReceipt:
    """Settle after trusted current-state observation, canonical policy, and a per-resource generation fence.

    policy_authorized is an input from canonical server policy, never from the event payload.
    """
    if receipt.state is not EventIngressState.RECONCILE_REQUIRED:
        raise ValueError("event settlement requires RECONCILE_REQUIRED")
    if not canonical_id.strip() or not authoritative_state_revision.strip():
        raise ValueError("canonical identity and authoritative state revision are required")
    if not expected_resource_generation.strip() or not current_resource_generation.strip():
        raise ValueError("resource generation fence values are required")
    if not policy_authorized:
        raise ValueError("event delivery does not grant canonical transition authority")
    if expected_resource_generation != current_resource_generation:
        return receipt
    state = EventIngressState.APPLIED if semantic_change else EventIngressState.NO_CHANGE
    return replace(
        receipt,
        state=state,
        canonical_id=canonical_id,
        authoritative_state_revision=authoritative_state_revision,
        resource_generation=current_resource_generation,
    )


def rebind_external_resource(
    binding: ExternalBinding,
    new_external_identity: ProviderScopedExternalIdentity,
    *,
    reason: str,
) -> ExternalBinding:
    """Rename/transfer/move an external projection without creating a second canonical entity."""
    if not reason.strip():
        raise ValueError("rebind reason must be non-empty")
    transition = f"rebind:{binding.external_identity.binding_key!r}->{new_external_identity.binding_key!r}:{reason}"
    return replace(
        binding,
        external_identity=new_external_identity,
        transition_history=(*binding.transition_history, transition),
    )


def binding_matches_external(binding: ExternalBinding, candidate: ProviderScopedExternalIdentity) -> bool:
    """Recovery locators never participate in binding authority."""
    return binding.external_identity.binding_key == candidate.binding_key


def mark_projection_ambiguous(entry: ProjectionOutboxEntry) -> ProjectionOutboxEntry:
    """Ambiguous provider delivery requires reconciliation, never optimistic replay."""
    if entry.state is not ProjectionDeliveryState.PENDING:
        raise ValueError("only a pending projection write can become ambiguous")
    return replace(entry, state=ProjectionDeliveryState.RECONCILE_REQUIRED)


def reconcile_projection_delivery(
    entry: ProjectionOutboxEntry,
    authoritative_present: bool | None,
) -> ProjectionOutboxEntry:
    """Resolve ambiguous projection delivery from authoritative provider state."""
    if entry.state is not ProjectionDeliveryState.RECONCILE_REQUIRED:
        raise ValueError("projection reconciliation requires RECONCILE_REQUIRED")
    if authoritative_present is True:
        return replace(entry, state=ProjectionDeliveryState.CONFIRMED)
    if authoritative_present is False:
        return replace(entry, state=ProjectionDeliveryState.DISPROVEN)
    return entry


def retarget_projection(entity: CanonicalEntity, new_projection_target: str, *, reason: str) -> CanonicalEntity:
    """Move/replace a projection without changing canonical entity identity or owner."""
    if not new_projection_target.strip() or not reason.strip():
        raise ValueError("retarget target and reason must be non-empty")
    transition = f"retarget:{entity.projection_target}->{new_projection_target}:{reason}"
    return replace(
        entity,
        projection_target=new_projection_target,
        transition_history=(*entity.transition_history, transition),
    )

"""Pure helpers for canonical-control-plane projection and identity invariants."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum


class ProjectionDeliveryState(StrEnum):
    PENDING = "PENDING"
    RECONCILE_REQUIRED = "RECONCILE_REQUIRED"
    CONFIRMED = "CONFIRMED"
    DISPROVEN = "DISPROVEN"


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

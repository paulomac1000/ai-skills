"""Authoritative reconciliation for ambiguous MCP write/send delivery."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class DeliveryState(StrEnum):
    DELIVERED = "DELIVERED"
    UNDELIVERED = "UNDELIVERED"
    RECONCILE_REQUIRED = "RECONCILE_REQUIRED"


@dataclass(frozen=True)
class DeliveryContext:
    """Stable identity that must not change between dispatch and reconciliation."""

    target_id: str
    operation_id: str
    idempotency_key: str
    runtime_identity: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.target_id.strip() or not self.operation_id.strip() or not self.idempotency_key.strip():
            raise ValueError("delivery context identities must be non-empty")
        _canonical_runtime_key(self.runtime_identity)


@dataclass(frozen=True)
class DeliveryDecision:
    state: DeliveryState
    context: DeliveryContext
    safe_to_retry: bool = False


def _canonical_runtime_key(identity: Mapping[str, object]) -> tuple[str, str]:
    if identity.get("schema_version") != 1:
        raise ValueError("runtime identity must use canonical schema_version")
    runtime_id = identity.get("runtime_id")
    generation = identity.get("instance_generation")
    if not isinstance(runtime_id, str) or not runtime_id.strip():
        raise ValueError("runtime identity must use canonical runtime_id")
    if not isinstance(generation, str) or not generation.strip():
        raise ValueError("runtime identity must use canonical instance_generation")
    return runtime_id, generation


def ambiguous_transport_outcome(transport_outcome: str, context: DeliveryContext) -> DeliveryDecision:
    """NO_ACK/timeout-after-dispatch never authorizes a speculative resend."""
    if transport_outcome not in {"NO_ACK", "TIMEOUT_AFTER_DISPATCH", "CONNECTION_LOST_AFTER_DISPATCH"}:
        raise ValueError("transport outcome is not an ambiguous dispatched outcome")
    return DeliveryDecision(DeliveryState.RECONCILE_REQUIRED, context, safe_to_retry=False)


def apply_authoritative_read_back(
    decision: DeliveryDecision,
    delivered: bool | None,
    *,
    exact_replay_safe: bool = False,
) -> DeliveryDecision:
    """Resolve against authoritative provider/resource state while preserving identity."""
    if decision.state is not DeliveryState.RECONCILE_REQUIRED:
        raise ValueError("authoritative read-back requires RECONCILE_REQUIRED")
    if delivered is True:
        return DeliveryDecision(DeliveryState.DELIVERED, decision.context, safe_to_retry=False)
    if delivered is False:
        return DeliveryDecision(
            DeliveryState.UNDELIVERED,
            decision.context,
            safe_to_retry=exact_replay_safe,
        )
    return DeliveryDecision(DeliveryState.RECONCILE_REQUIRED, decision.context, safe_to_retry=False)


def should_resend(decision: DeliveryDecision) -> bool:
    """Replay only after authoritative non-delivery plus an exact safe replay proof."""
    return decision.state is DeliveryState.UNDELIVERED and decision.safe_to_retry

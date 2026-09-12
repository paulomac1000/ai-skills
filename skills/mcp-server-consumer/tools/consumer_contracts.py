"""Scoped health and typed public-identifier handoff contracts for MCP consumers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum


class HealthState(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"


@dataclass(frozen=True)
class ProviderHealth:
    """Health evidence for one provider and canonical runtime generation."""

    provider: str
    runtime_identity: Mapping[str, object]
    fresh: bool
    process: HealthState
    transport: HealthState
    auth: HealthState
    read: HealthState
    write: HealthState

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("provider must be non-empty")
        _runtime_key(self.runtime_identity)

    def ready_for(self, action: str) -> bool:
        """Fail closed unless all shared scopes and the requested action are READY and fresh."""
        if action not in {"read", "write"}:
            raise ValueError("action must be read or write")
        shared = (self.process, self.transport, self.auth)
        action_state = self.read if action == "read" else self.write
        return self.fresh and all(state is HealthState.READY for state in shared) and action_state is HealthState.READY

    @property
    def fully_ready(self) -> bool:
        """Whole-provider readiness requires both read and write, never one successful action."""
        return self.ready_for("read") and self.ready_for("write")


@dataclass(frozen=True)
class PublicResourceRef:
    """Typed public ID provenance without inventing an alternate runtime identity shape."""

    resource_id: str
    kind: str
    source_operation: str
    runtime_identity: Mapping[str, object]

    def __post_init__(self) -> None:
        for name, value in (
            ("resource_id", self.resource_id),
            ("kind", self.kind),
            ("source_operation", self.source_operation),
        ):
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")
        _runtime_key(self.runtime_identity)


def _runtime_key(identity: Mapping[str, object]) -> tuple[str, str]:
    """Read only the canonical runtime identity key; reject legacy aliases by omission."""
    runtime_id = identity.get("runtime_id")
    generation = identity.get("instance_generation")
    schema_version = identity.get("schema_version")
    if schema_version != 1 or not isinstance(runtime_id, str) or not runtime_id.strip():
        raise ValueError("runtime_identity must use canonical schema_version/runtime_id")
    if not isinstance(generation, str) or not generation.strip():
        raise ValueError("runtime_identity must use canonical instance_generation")
    return runtime_id, generation


def verify_public_id_handoff(
    created: PublicResourceRef,
    downstream: Sequence[PublicResourceRef],
) -> PublicResourceRef:
    """Require create→status/read/result references to preserve ID namespace and runtime identity."""
    expected = (
        created.resource_id,
        created.kind,
        _runtime_key(created.runtime_identity),
    )
    for observed in downstream:
        actual = (
            observed.resource_id,
            observed.kind,
            _runtime_key(observed.runtime_identity),
        )
        if actual != expected:
            raise ValueError("public resource identifier handoff mismatch")
    return created

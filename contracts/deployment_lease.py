#!/usr/bin/env python3
"""Reference admission checks for exact, one-use deployment leases."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


class DeploymentLeaseError(ValueError):
    """Raised when a lease cannot authorize the exact requested mutation."""


@dataclass(frozen=True)
class LeaseAdmission:
    lease_id: str
    principal: str
    action: str
    artifact_digest: str
    target_project: str
    target_environment: str
    target_resource: str
    policy_revision: str


def _utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise DeploymentLeaseError(f"invalid lease timestamp: {value}") from error
    if parsed.tzinfo is None:
        raise DeploymentLeaseError("lease timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def admit_lease(
    lease: Mapping[str, Any],
    *,
    principal: str,
    target: Mapping[str, str],
    artifact_digest: str,
    action: str,
    normalized_args_digest: str,
    now: datetime,
    consumed_lease_ids: Collection[str] = (),
) -> LeaseAdmission:
    """Admit only an active, unconsumed lease matching every protected dimension exactly."""
    lease_id = str(lease.get("lease_id") or "")
    if not lease_id:
        raise DeploymentLeaseError("lease_id is required")
    if lease_id in consumed_lease_ids:
        raise DeploymentLeaseError("deployment lease was already consumed")
    if lease.get("state") != "active":
        raise DeploymentLeaseError(f"deployment lease is not active: {lease.get('state')}")

    instant = now.astimezone(timezone.utc)
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
    }
    for field, (actual, expected) in checks.items():
        if actual != expected:
            raise DeploymentLeaseError(f"deployment lease {field} does not match requested operation")

    lease_target = lease.get("target")
    if not isinstance(lease_target, Mapping):
        raise DeploymentLeaseError("deployment lease target is missing")
    for field in ("project", "environment", "resource"):
        if lease_target.get(field) != target.get(field):
            raise DeploymentLeaseError(f"deployment lease target.{field} does not match requested target")

    policy_revision = str(lease.get("policy_revision") or "")
    if not policy_revision:
        raise DeploymentLeaseError("deployment lease policy_revision is required")

    return LeaseAdmission(
        lease_id=lease_id,
        principal=principal,
        action=action,
        artifact_digest=artifact_digest,
        target_project=target["project"],
        target_environment=target["environment"],
        target_resource=target["resource"],
        policy_revision=policy_revision,
    )

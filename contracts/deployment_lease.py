#!/usr/bin/env python3
"""Reference admission checks for exact, one-use deployment leases."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


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
    now: datetime,
    session: str | None = None,
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

    policy_revision = str(lease.get("policy_revision") or "")
    if not policy_revision:
        raise DeploymentLeaseError("deployment lease policy_revision is required")

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
    )

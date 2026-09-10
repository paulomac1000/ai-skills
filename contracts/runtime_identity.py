#!/usr/bin/env python3
"""Reference checks for source -> artifact -> running-runtime identity chains."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


class RuntimeIdentityError(ValueError):
    """Raised when a running runtime does not prove the expected candidate identity."""


@dataclass(frozen=True)
class RuntimeChainReceipt:
    source_revision: str
    artifact_digest: str
    candidate_runtime_id: str
    candidate_generation: str
    deployed_runtime_id: str
    deployed_generation: str
    previous_deployed_generation: str | None
    previous_evidence_stale: bool


def _required_text(identity: Mapping[str, Any], field: str) -> str:
    value = identity.get(field)
    if not isinstance(value, str) or not value:
        raise RuntimeIdentityError(f"runtime identity is missing {field}")
    return value


def _assert_expected(
    identity: Mapping[str, Any],
    *,
    expected_source_revision: str,
    expected_artifact_digest: str,
    label: str,
) -> None:
    source = _required_text(identity, "source_revision")
    digest = _required_text(identity, "artifact_digest")
    if source != expected_source_revision:
        raise RuntimeIdentityError(
            f"{label} runtime source revision {source} does not match expected {expected_source_revision}"
        )
    if digest != expected_artifact_digest:
        raise RuntimeIdentityError(
            f"{label} runtime artifact digest {digest} does not match expected {expected_artifact_digest}"
        )


def verify_runtime_chain(
    *,
    expected_source_revision: str,
    expected_artifact_digest: str,
    candidate_runtime: Mapping[str, Any],
    deployed_runtime: Mapping[str, Any],
    previous_deployed_runtime: Mapping[str, Any] | None = None,
    require_new_generation: bool = False,
) -> RuntimeChainReceipt:
    """Bind exact source/artifact identity to candidate and deployed runtime self-reports."""
    if not expected_source_revision or not expected_artifact_digest:
        raise RuntimeIdentityError("expected source revision and artifact digest are required")
    if require_new_generation and previous_deployed_runtime is None:
        raise RuntimeIdentityError(
            "previous deployed runtime identity is required to prove a new instance generation"
        )
    _assert_expected(
        candidate_runtime,
        expected_source_revision=expected_source_revision,
        expected_artifact_digest=expected_artifact_digest,
        label="candidate",
    )
    _assert_expected(
        deployed_runtime,
        expected_source_revision=expected_source_revision,
        expected_artifact_digest=expected_artifact_digest,
        label="deployed",
    )

    candidate_generation = _required_text(candidate_runtime, "instance_generation")
    deployed_generation = _required_text(deployed_runtime, "instance_generation")
    previous_generation: str | None = None
    stale = False
    if previous_deployed_runtime is not None:
        previous_generation = _required_text(previous_deployed_runtime, "instance_generation")
        stale = previous_generation != deployed_generation
        if require_new_generation and not stale:
            raise RuntimeIdentityError("deployment/restart did not produce a new instance generation")

    return RuntimeChainReceipt(
        source_revision=expected_source_revision,
        artifact_digest=expected_artifact_digest,
        candidate_runtime_id=_required_text(candidate_runtime, "runtime_id"),
        candidate_generation=candidate_generation,
        deployed_runtime_id=_required_text(deployed_runtime, "runtime_id"),
        deployed_generation=deployed_generation,
        previous_deployed_generation=previous_generation,
        previous_evidence_stale=stale,
    )

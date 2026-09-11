"""Deterministic, I/O-free pre-mutation admission classification for MCP consumers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AdmissionClass(StrEnum):
    """Provider-neutral identity/owner/readiness classification."""

    MATCH = "MATCH"
    SUSPECTED_DRIFT = "SUSPECTED_DRIFT"
    CONFIRMED_DRIFT = "CONFIRMED_DRIFT"
    OWNER_UNKNOWN = "OWNER_UNKNOWN"
    RUNTIME_STALE_OR_UNKNOWN = "RUNTIME_STALE_OR_UNKNOWN"
    CAPABILITY_DEGRADED = "CAPABILITY_DEGRADED"


@dataclass(frozen=True)
class AdmissionEvidence:
    """Already-observed evidence; this helper performs no discovery or I/O."""

    owner_known: bool
    target_resolved: bool
    runtime_fresh: bool | None
    capability_ready: bool | None
    observed_matches_expected: bool | None
    exact_runtime_identity_available: bool


def classify_admission(evidence: AdmissionEvidence) -> AdmissionClass:
    """Classify with stable fail-closed precedence: owner, runtime, health, drift."""
    if not evidence.owner_known:
        return AdmissionClass.OWNER_UNKNOWN
    if evidence.runtime_fresh is not True:
        return AdmissionClass.RUNTIME_STALE_OR_UNKNOWN
    if evidence.capability_ready is not True:
        return AdmissionClass.CAPABILITY_DEGRADED
    if evidence.observed_matches_expected is True and evidence.target_resolved:
        return AdmissionClass.MATCH
    if evidence.observed_matches_expected is False and evidence.exact_runtime_identity_available:
        return AdmissionClass.CONFIRMED_DRIFT
    return AdmissionClass.SUSPECTED_DRIFT


def mutation_allowed(evidence: AdmissionEvidence) -> bool:
    """Admit mutation only for an exact resolved MATCH; every uncertainty blocks."""
    return evidence.target_resolved and classify_admission(evidence) is AdmissionClass.MATCH

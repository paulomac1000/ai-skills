"""Provider-neutral runtime acceptance evaluation and currentness helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

_MAX_REF = 2048
_MAX_REFS = 64
_ALLOWED_IDENTITY_FIELDS = frozenset({"artifact_digest", "source_revision", "config_revision"})


class ProofStatus(StrEnum):
    PROVEN = "proven"
    FAILED = "failed"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"


class AcceptanceVerdict(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


class AcceptanceCurrentness(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


def _require_ref(value: str, name: str) -> None:
    if not value.strip() or len(value) > _MAX_REF:
        raise ValueError(f"{name} must be non-empty and at most {_MAX_REF} characters")


def _optional_ref(value: str | None, name: str) -> None:
    if value is not None:
        _require_ref(value, name)


@dataclass(frozen=True)
class AcceptanceProfile:
    profile_id: str
    profile_revision: str
    policy_revision: str
    required_identity_fields: tuple[str, ...] = ("artifact_digest",)
    required_proof_kinds: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_ref(self.profile_id, "profile id")
        _require_ref(self.profile_revision, "profile revision")
        _require_ref(self.policy_revision, "policy revision")
        if len(set(self.required_identity_fields)) != len(self.required_identity_fields):
            raise ValueError("required identity fields must be unique")
        unknown = set(self.required_identity_fields) - _ALLOWED_IDENTITY_FIELDS
        if unknown:
            raise ValueError(f"unsupported required identity fields: {sorted(unknown)}")
        if len(set(self.required_proof_kinds)) != len(self.required_proof_kinds):
            raise ValueError("required proof kinds must be unique")
        for kind in self.required_proof_kinds:
            _require_ref(kind, "required proof kind")


@dataclass(frozen=True)
class ExpectedRuntime:
    artifact_digest: str
    source_revision: str | None = None
    config_revision: str | None = None
    artifact_identity: str | None = None
    deployment_operation_ref: str | None = None

    def __post_init__(self) -> None:
        _require_ref(self.artifact_digest, "expected artifact digest")
        _optional_ref(self.source_revision, "expected source revision")
        _optional_ref(self.config_revision, "expected config revision")
        _optional_ref(self.artifact_identity, "expected artifact identity")
        _optional_ref(self.deployment_operation_ref, "deployment operation ref")


@dataclass(frozen=True)
class ObservedRuntime:
    runtime_identity_ref: str
    runtime_id: str
    instance_generation: str
    observed_at: str
    artifact_digest: str | None = None
    source_revision: str | None = None
    artifact_version: str | None = None
    config_revision: str | None = None

    def __post_init__(self) -> None:
        _require_ref(self.runtime_identity_ref, "runtime identity ref")
        _require_ref(self.runtime_id, "runtime id")
        _require_ref(self.instance_generation, "instance generation")
        _require_ref(self.observed_at, "observed at")
        _optional_ref(self.artifact_digest, "observed artifact digest")
        _optional_ref(self.source_revision, "observed source revision")
        _optional_ref(self.artifact_version, "observed artifact version")
        _optional_ref(self.config_revision, "observed config revision")


@dataclass(frozen=True)
class ProofResult:
    kind: str
    status: ProofStatus
    authority: str
    evidence_ref: str | None = None

    def __post_init__(self) -> None:
        _require_ref(self.kind, "proof kind")
        _require_ref(self.authority, "proof authority")
        _optional_ref(self.evidence_ref, "proof evidence ref")


@dataclass(frozen=True)
class AcceptanceDecision:
    verdict: AcceptanceVerdict
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeAcceptanceDependencies:
    artifact_digest: str | None
    source_revision: str | None
    config_revision: str | None
    instance_generation: str
    profile_revision: str
    policy_revision: str

    def __post_init__(self) -> None:
        _optional_ref(self.artifact_digest, "dependency artifact digest")
        _optional_ref(self.source_revision, "dependency source revision")
        _optional_ref(self.config_revision, "dependency config revision")
        _require_ref(self.instance_generation, "dependency instance generation")
        _require_ref(self.profile_revision, "dependency profile revision")
        _require_ref(self.policy_revision, "dependency policy revision")


def evaluate_acceptance(
    profile: AcceptanceProfile,
    expected: ExpectedRuntime,
    observed: ObservedRuntime,
    proofs: Iterable[ProofResult],
) -> AcceptanceDecision:
    """Evaluate expected-vs-observed identity and required proof obligations."""
    reasons: list[str] = []
    hard_failure = False
    unresolved = False

    for field_name in profile.required_identity_fields:
        expected_value = getattr(expected, field_name)
        observed_value = getattr(observed, field_name)
        if expected_value is None:
            reasons.append(f"required-expected-{field_name}-missing")
            unresolved = True
        elif observed_value is None:
            reasons.append(f"required-observed-{field_name}-unknown")
            unresolved = True
        elif expected_value != observed_value:
            reasons.append(f"required-{field_name}-mismatch")
            hard_failure = True

    by_kind: dict[str, ProofResult] = {}
    for proof in proofs:
        if proof.kind in by_kind:
            raise ValueError(f"duplicate proof kind: {proof.kind}")
        by_kind[proof.kind] = proof

    for kind in profile.required_proof_kinds:
        proof = by_kind.get(kind)
        if proof is None:
            reasons.append(f"required-proof-{kind}-missing")
            unresolved = True
            continue
        if proof.status is ProofStatus.FAILED:
            reasons.append(f"required-proof-{kind}-failed")
            hard_failure = True
        elif proof.status in {ProofStatus.UNKNOWN, ProofStatus.UNSUPPORTED}:
            reasons.append(f"required-proof-{kind}-{proof.status.value}")
            unresolved = True

    if hard_failure:
        return AcceptanceDecision(AcceptanceVerdict.REJECTED, tuple(sorted(reasons)))
    if unresolved:
        return AcceptanceDecision(AcceptanceVerdict.INCONCLUSIVE, tuple(sorted(reasons)))
    return AcceptanceDecision(AcceptanceVerdict.ACCEPTED, ())


def dependency_snapshot(
    profile: AcceptanceProfile,
    observed: ObservedRuntime,
) -> RuntimeAcceptanceDependencies:
    """Capture the load-bearing runtime/profile identity for later currentness checks."""
    return RuntimeAcceptanceDependencies(
        artifact_digest=observed.artifact_digest,
        source_revision=observed.source_revision,
        config_revision=observed.config_revision,
        instance_generation=observed.instance_generation,
        profile_revision=profile.profile_revision,
        policy_revision=profile.policy_revision,
    )


def derive_currentness(
    receipt: RuntimeAcceptanceDependencies,
    current: RuntimeAcceptanceDependencies,
) -> AcceptanceCurrentness:
    """Return STALE for changed known dependencies and UNKNOWN for missing observations."""
    if receipt.profile_revision != current.profile_revision or receipt.policy_revision != current.policy_revision:
        return AcceptanceCurrentness.STALE
    if receipt.instance_generation != current.instance_generation:
        return AcceptanceCurrentness.STALE
    for field_name in ("artifact_digest", "source_revision", "config_revision"):
        prior = getattr(receipt, field_name)
        now = getattr(current, field_name)
        if prior is None:
            continue
        if now is None:
            return AcceptanceCurrentness.UNKNOWN
        if prior != now:
            return AcceptanceCurrentness.STALE
    return AcceptanceCurrentness.CURRENT


def evidence_set_digest(evidence_refs: Iterable[str]) -> str:
    """Create a stable digest for the exact bounded set of evidence references."""
    refs = tuple(sorted(set(evidence_refs)))
    if len(refs) > _MAX_REFS:
        raise ValueError(f"evidence refs must contain at most {_MAX_REFS} items")
    for ref in refs:
        _require_ref(ref, "evidence ref")
    encoded = json.dumps(refs, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()

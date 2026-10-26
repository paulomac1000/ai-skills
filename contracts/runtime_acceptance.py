#!/usr/bin/env python3
"""Provider-neutral RuntimeAcceptanceReceipt v1 composition, evaluation, and currentness (#97).

The receipt composes caller-supplied expected deployment identity with
independently observed RuntimeIdentity data, proof obligations selected by a
trusted acceptance profile, bounded evidence inputs, and mechanically derivable
staleness. It never upgrades untrusted evidence authority and never copies an
expected value into an observation.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path

_MAX_REF = 2048
_MAX_REFS = 64
_MAX_PROOFS = 64
_MAX_FINDINGS = 200
_MAX_INPUT_BYTES = 1024 * 1024
_ALLOWED_IDENTITY_FIELDS = frozenset({"artifact_digest", "source_revision", "config_revision"})
RECEIPT_FORMAT = "ai-skills-runtime-acceptance"
RECEIPT_KIND = "runtime_acceptance"


class ProofStatus(StrEnum):
    PROVEN = "proven"
    FAILED = "failed"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"


class AcceptanceVerdict(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"
    STALE = "stale"


class AcceptanceCurrentness(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class EvidenceAuthority(StrEnum):
    """Independent evidence authority classes; composition never upgrades them.

    Satisfaction of a minimum-authority floor is an explicit compatibility
    relation, not a scalar rank: a model review can never stand in for
    deterministic QA execution, and only an independent observer satisfies an
    independent-observer floor.
    """

    CALLER_CLAIM = "caller_claim"
    WORKER_REPORT = "worker_report"
    PROVIDER_ACK = "provider_ack"
    QA_DETERMINISTIC = "qa_deterministic"
    MODEL_REVIEW = "model_review"
    INDEPENDENT_OBSERVER = "independent_observer"


_AUTHORITY_SUBSTITUTIONS: dict[EvidenceAuthority, frozenset[EvidenceAuthority]] = {
    EvidenceAuthority.CALLER_CLAIM: frozenset(EvidenceAuthority),
    EvidenceAuthority.WORKER_REPORT: frozenset(EvidenceAuthority) - {EvidenceAuthority.CALLER_CLAIM},
    EvidenceAuthority.PROVIDER_ACK: frozenset(
        {
            EvidenceAuthority.PROVIDER_ACK,
            EvidenceAuthority.QA_DETERMINISTIC,
            EvidenceAuthority.MODEL_REVIEW,
            EvidenceAuthority.INDEPENDENT_OBSERVER,
        }
    ),
    EvidenceAuthority.QA_DETERMINISTIC: frozenset(
        {EvidenceAuthority.QA_DETERMINISTIC, EvidenceAuthority.INDEPENDENT_OBSERVER}
    ),
    EvidenceAuthority.MODEL_REVIEW: frozenset({EvidenceAuthority.MODEL_REVIEW, EvidenceAuthority.INDEPENDENT_OBSERVER}),
    EvidenceAuthority.INDEPENDENT_OBSERVER: frozenset({EvidenceAuthority.INDEPENDENT_OBSERVER}),
}


def authority_satisfies(observed: EvidenceAuthority, floor: EvidenceAuthority) -> bool:
    """Return whether the observed authority class may satisfy the declared floor."""
    return observed in _AUTHORITY_SUBSTITUTIONS[floor]


@dataclass(frozen=True)
class ClockProvenance:
    """Preserved source-clock metadata; normalization never fabricates certainty."""

    source_timestamp: str
    source_clock: str
    normalization: str  # exact | derived | unknown
    source_offset: str | None = None

    def __post_init__(self) -> None:
        _require_ref(self.source_timestamp, "clock source timestamp")
        _require_ref(self.source_clock, "clock source identity")
        if self.normalization not in {"exact", "derived", "unknown"}:
            raise ValueError("clock normalization must be exact, derived, or unknown")
        if self.normalization == "exact" and (
            self.source_offset is None or not _CLOCK_OFFSET.match(self.source_offset)
        ):
            raise ValueError("exact normalization requires a preserved valid source offset")

    def as_document(self) -> dict[str, str | None]:
        return {
            "source_timestamp": self.source_timestamp,
            "source_offset": self.source_offset,
            "source_clock": self.source_clock,
            "normalization": self.normalization,
        }


def _require_ref(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > _MAX_REF:
        raise ValueError(f"{name} must be a non-empty string of at most {_MAX_REF} characters")


def _require_bounded(value: str, name: str, max_length: int) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError(f"{name} must be a non-empty string of at most {max_length} characters")


_SHA256_DIGEST = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
_SOURCE_REVISION = re.compile(r"^[0-9a-fA-F]{40}$")
_CLOCK_OFFSET = re.compile(r"^Z$|^[+-](?:0[0-9]|1[0-4]):[0-5][0-9]$")


def _require_digest(value: str, name: str) -> None:
    _require_bounded(value, name, 71)
    if not _SHA256_DIGEST.match(value):
        raise ValueError(f"{name} must match sha256:<64 hex characters>")


def _optional_digest(value: str | None, name: str) -> None:
    if value is not None:
        _require_digest(value, name)


def _require_source_revision(value: str, name: str) -> None:
    _require_bounded(value, name, 40)
    if not _SOURCE_REVISION.match(value):
        raise ValueError(f"{name} must be a 40-character hex source revision")


def _optional_source_revision(value: str | None, name: str) -> None:
    if value is not None:
        _require_source_revision(value, name)


def _optional_bounded(value: str | None, name: str, max_length: int) -> None:
    if value is not None:
        _require_bounded(value, name, max_length)


def _optional_offset(value: str | None, name: str) -> None:
    if value is None:
        return
    _require_bounded(value, name, 6)
    if not _CLOCK_OFFSET.match(value):
        raise ValueError(f"{name} must be Z or a +/-HH:MM UTC offset")


@dataclass(frozen=True)
class AcceptanceProfile:
    profile_id: str
    profile_revision: str
    policy_revision: str
    required_identity_fields: tuple[str, ...] = ("artifact_digest",)
    required_proof_kinds: tuple[str, ...] = ()
    minimum_authority: Mapping[str, EvidenceAuthority] = field(default_factory=dict)
    require_target_binding: bool = True
    bind_proofs_to_generation: bool = True

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
        unknown_kinds = set(self.minimum_authority) - set(self.required_proof_kinds)
        if unknown_kinds:
            raise ValueError(f"minimum authority declared for unprofiled proof kinds: {sorted(unknown_kinds)}")


@dataclass(frozen=True)
class ExpectedRuntime:
    artifact_digest: str
    source_revision: str | None = None
    config_revision: str | None = None
    artifact_identity: str | None = None
    deployment_operation_ref: str | None = None
    deployment_identity: str | None = None

    def __post_init__(self) -> None:
        _require_digest(self.artifact_digest, "expected artifact digest")
        _optional_source_revision(self.source_revision, "expected source revision")
        _optional_bounded(self.config_revision, "expected config revision", 256)
        _optional_bounded(self.artifact_identity, "expected artifact identity", 512)
        _optional_bounded(self.deployment_operation_ref, "deployment operation ref", 2048)
        _optional_bounded(self.deployment_identity, "expected deployment identity", 256)


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
    deployment_identity: str | None = None
    clock_provenance: ClockProvenance | None = None
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_ref(self.runtime_identity_ref, "runtime identity ref")
        _require_bounded(self.runtime_id, "runtime id", 256)
        _require_bounded(self.instance_generation, "instance generation", 256)
        _require_ref(self.observed_at, "observed at")
        _optional_digest(self.artifact_digest, "observed artifact digest")
        _optional_source_revision(self.source_revision, "observed source revision")
        _optional_bounded(self.artifact_version, "observed artifact version", 128)
        _optional_bounded(self.config_revision, "observed config revision", 256)
        _optional_bounded(self.deployment_identity, "observed deployment identity", 256)
        if len(self.provenance_refs) > _MAX_REFS:
            raise ValueError(f"provenance refs must contain at most {_MAX_REFS} items")
        for ref in self.provenance_refs:
            _require_ref(ref, "provenance ref")


@dataclass(frozen=True)
class ProofResult:
    kind: str
    status: ProofStatus
    authority: EvidenceAuthority
    evidence_ref: str | None = None
    runtime_generation: str | None = None

    def __post_init__(self) -> None:
        _require_ref(self.kind, "proof kind")
        _optional_bounded(self.evidence_ref, "proof evidence ref", _MAX_REF)
        _optional_bounded(self.runtime_generation, "proof runtime generation", 256)


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
        _optional_digest(self.artifact_digest, "dependency artifact digest")
        _optional_source_revision(self.source_revision, "dependency source revision")
        _optional_bounded(self.config_revision, "dependency config revision", 256)
        _require_bounded(self.instance_generation, "dependency instance generation", 256)
        _require_bounded(self.profile_revision, "dependency profile revision", 256)
        _require_bounded(self.policy_revision, "dependency policy revision", 256)


def profile_digest(profile: AcceptanceProfile) -> str:
    """Canonical digest of the complete acceptance policy that produced a verdict."""
    body = {
        "id": profile.profile_id,
        "revision": profile.profile_revision,
        "policy_revision": profile.policy_revision,
        "required_identity_fields": list(profile.required_identity_fields),
        "required_proof_kinds": list(profile.required_proof_kinds),
        "minimum_authority": {kind: floor.value for kind, floor in sorted(profile.minimum_authority.items())},
        "require_target_binding": profile.require_target_binding,
        "bind_proofs_to_generation": profile.bind_proofs_to_generation,
    }
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def evaluate_acceptance(
    profile: AcceptanceProfile,
    expected: ExpectedRuntime,
    observed: ObservedRuntime,
    proofs: Iterable[ProofResult],
) -> AcceptanceDecision:
    """Evaluate expected-vs-observed identity, target binding, and required proof obligations.

    Typed reasons make every non-green outcome explicit. Authority escalation and
    evidence-free proven claims are hard rejections, never silent downgrades.
    """
    reasons: list[str] = []
    hard_failure = False
    unresolved = False

    if profile.require_target_binding:
        if expected.deployment_identity is None:
            reasons.append("required-target-deployment-identity-missing")
            unresolved = True
        elif observed.deployment_identity is None:
            reasons.append("target-binding-unknown")
            unresolved = True
        elif expected.deployment_identity != observed.deployment_identity:
            reasons.append("target-binding-mismatch")
            hard_failure = True

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
    for candidate in proofs:
        if candidate.kind in by_kind:
            raise ValueError(f"duplicate proof kind: {candidate.kind}")
        by_kind[candidate.kind] = candidate

    for kind in profile.required_proof_kinds:
        item = by_kind.get(kind)
        if item is None:
            reasons.append(f"required-proof-{kind}-missing")
            unresolved = True
            continue
        if profile.bind_proofs_to_generation:
            if item.runtime_generation is None:
                reasons.append(f"required-proof-{kind}-generation-unbound")
                hard_failure = True
                continue
            if item.runtime_generation != observed.instance_generation:
                reasons.append(f"required-proof-{kind}-generation-mismatch")
                hard_failure = True
                continue
        floor = profile.minimum_authority.get(kind)
        if item.status is ProofStatus.PROVEN and floor is not None and not authority_satisfies(item.authority, floor):
            reasons.append(f"required-proof-{kind}-authority-insufficient")
            hard_failure = True
            continue
        if item.status is ProofStatus.PROVEN and item.evidence_ref is None:
            reasons.append(f"required-proof-{kind}-evidence-missing")
            hard_failure = True
            continue
        if item.status is ProofStatus.FAILED:
            reasons.append(f"required-proof-{kind}-failed")
            hard_failure = True
        elif item.status in {ProofStatus.UNKNOWN, ProofStatus.UNSUPPORTED}:
            reasons.append(f"required-proof-{kind}-{item.status.value}")
            unresolved = True

    if hard_failure:
        return AcceptanceDecision(AcceptanceVerdict.REJECTED, tuple(sorted(reasons)))
    if unresolved:
        return AcceptanceDecision(AcceptanceVerdict.INCONCLUSIVE, tuple(sorted(reasons)))
    return AcceptanceDecision(AcceptanceVerdict.ACCEPTED, ())


def compose_observations(observations: Sequence[ObservedRuntime]) -> ObservedRuntime:
    """Merge independent observations of one target, failing closed on conflicts."""
    if not observations:
        raise ValueError("at least one observation is required")
    first = observations[0]
    runtime_id = first.runtime_id
    instance_generation = first.instance_generation
    artifact_digest = first.artifact_digest
    source_revision = first.source_revision
    artifact_version = first.artifact_version
    config_revision = first.config_revision
    deployment_identity = first.deployment_identity
    clock_provenance = first.clock_provenance
    provenance: dict[str, None] = {first.runtime_identity_ref: None}
    for ref in first.provenance_refs:
        provenance.setdefault(ref)
    latest_at = _parse_utc(first.observed_at)

    def _merge(current: str | None, incoming: str | None, name: str) -> str | None:
        if current is not None and incoming is not None and current != incoming:
            raise ValueError(f"conflicting observation {name}: {current!r} vs {incoming!r}")
        return current if current is not None else incoming

    for other in observations[1:]:
        other_at = _parse_utc(other.observed_at)
        if other_at > latest_at:
            latest_at = other_at
        runtime_id = _merge(runtime_id, other.runtime_id, "runtime_id") or runtime_id
        instance_generation = (
            _merge(instance_generation, other.instance_generation, "instance_generation") or instance_generation
        )
        artifact_digest = _merge(artifact_digest, other.artifact_digest, "artifact_digest")
        source_revision = _merge(source_revision, other.source_revision, "source_revision")
        artifact_version = _merge(artifact_version, other.artifact_version, "artifact_version")
        config_revision = _merge(config_revision, other.config_revision, "config_revision")
        deployment_identity = _merge(deployment_identity, other.deployment_identity, "deployment_identity")
        if (
            clock_provenance is not None
            and other.clock_provenance is not None
            and clock_provenance != other.clock_provenance
        ):
            raise ValueError("conflicting observation clock_provenance")
        clock_provenance = clock_provenance if clock_provenance is not None else other.clock_provenance
        provenance.setdefault(other.runtime_identity_ref)
        for ref in other.provenance_refs:
            provenance.setdefault(ref)
        if len(provenance) > _MAX_REFS:
            raise ValueError(f"merged provenance references must contain at most {_MAX_REFS} items")

    return ObservedRuntime(
        runtime_identity_ref=first.runtime_identity_ref,
        runtime_id=runtime_id,
        instance_generation=instance_generation,
        observed_at=latest_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        artifact_digest=artifact_digest,
        source_revision=source_revision,
        artifact_version=artifact_version,
        config_revision=config_revision,
        deployment_identity=deployment_identity,
        clock_provenance=clock_provenance,
        provenance_refs=tuple(sorted(provenance)),
    )


def _parse_utc(value: str) -> datetime:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"timestamp must be a valid ISO 8601 value: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must include a timezone offset: {value!r}")
    return parsed


def dependency_snapshot(profile: AcceptanceProfile, observed: ObservedRuntime) -> RuntimeAcceptanceDependencies:
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
    receipt: RuntimeAcceptanceDependencies, current: RuntimeAcceptanceDependencies
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


def adjudicate(
    issued_verdict: AcceptanceVerdict,
    receipt_dependencies: RuntimeAcceptanceDependencies,
    current_dependencies: RuntimeAcceptanceDependencies,
    *,
    expires_at: str | None,
    now: datetime,
    current_observation: ObservedRuntime | None = None,
    max_age_seconds: float | None = None,
) -> AcceptanceVerdict:
    """Dependency-only currentness comparison.

    This helper is NOT authoritative currentness evidence: with no current
    observation or no freshness window it compares detached dependency values
    only. Acceptance-gate decisions must use :func:`adjudicate_current`, which
    requires fresh generation-bound observation evidence.
    """
    if now.tzinfo is None:
        raise ValueError("adjudicate now must be timezone-aware")
    if current_observation is not None:
        _require_observation_binding(current_observation, current_dependencies)
    if issued_verdict is not AcceptanceVerdict.ACCEPTED:
        return issued_verdict
    if expires_at is not None and now >= _parse_utc(expires_at):
        return AcceptanceVerdict.STALE
    if current_observation is not None and max_age_seconds is not None:
        observed = _parse_utc(current_observation.observed_at)
        if (now - observed).total_seconds() > max_age_seconds:
            return AcceptanceVerdict.STALE
    return _currentness_verdict(receipt_dependencies, current_dependencies)


def adjudicate_current(
    issued_verdict: AcceptanceVerdict,
    receipt_dependencies: RuntimeAcceptanceDependencies,
    current_dependencies: RuntimeAcceptanceDependencies,
    *,
    now: datetime,
    current_observation: ObservedRuntime,
    max_age_seconds: float,
    clock_skew_seconds: float = 0.0,
    expires_at: str | None = None,
) -> AcceptanceVerdict:
    """Authoritative currentness adjudication bound to fresh observation evidence.

    Requires a real current observation (generation and identity fields must
    agree with the supplied current dependencies), a positive freshness
    window, and rejects future-dated observations beyond the declared
    clock-skew tolerance. Missing or over-aged current evidence yields
    INCONCLUSIVE or STALE instead of a replayed acceptance.
    """
    if now.tzinfo is None:
        raise ValueError("adjudicate now must be timezone-aware")
    if not max_age_seconds > 0:
        raise ValueError("the freshness window must be positive")
    if clock_skew_seconds < 0:
        raise ValueError("the clock-skew tolerance must not be negative")
    _require_observation_binding(current_observation, current_dependencies)
    observed_at = _parse_utc(current_observation.observed_at)
    age_seconds = (now - observed_at).total_seconds()
    if age_seconds < -clock_skew_seconds:
        raise ValueError("current observation is future-dated beyond the clock-skew tolerance")
    if issued_verdict is not AcceptanceVerdict.ACCEPTED:
        return issued_verdict
    if expires_at is not None and now >= _parse_utc(expires_at):
        return AcceptanceVerdict.STALE
    if age_seconds > max_age_seconds:
        return AcceptanceVerdict.STALE
    return _currentness_verdict(receipt_dependencies, current_dependencies)


def _require_observation_binding(
    current_observation: ObservedRuntime,
    current_dependencies: RuntimeAcceptanceDependencies,
) -> None:
    if current_observation.instance_generation != current_dependencies.instance_generation:
        raise ValueError("current observation generation disagrees with the supplied current dependencies")
    for field_name in ("artifact_digest", "source_revision", "config_revision"):
        if getattr(current_observation, field_name) != getattr(current_dependencies, field_name):
            raise ValueError(f"current observation {field_name} disagrees with the supplied current dependencies")


def _currentness_verdict(
    receipt_dependencies: RuntimeAcceptanceDependencies,
    current_dependencies: RuntimeAcceptanceDependencies,
) -> AcceptanceVerdict:
    currentness = derive_currentness(receipt_dependencies, current_dependencies)
    if currentness is AcceptanceCurrentness.STALE:
        return AcceptanceVerdict.STALE
    if currentness is AcceptanceCurrentness.UNKNOWN:
        return AcceptanceVerdict.INCONCLUSIVE
    return AcceptanceVerdict.ACCEPTED


def evidence_set_digest(evidence_refs: Iterable[str]) -> str:
    """Create a stable digest for the exact bounded set of evidence references.

    Consumption is bounded: the reference-count limit is enforced while
    iterating, before any unbounded set materialises.
    """
    unique: dict[str, None] = {}
    for ref in evidence_refs:
        _require_ref(ref, "evidence ref")
        unique.setdefault(ref)
        if len(unique) > _MAX_REFS:
            raise ValueError(f"evidence refs must contain at most {_MAX_REFS} items")
    refs = tuple(sorted(unique))
    encoded = json.dumps(refs, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def payload_digest(document: Mapping[str, object]) -> str:
    """Recompute the structural integrity digest of a receipt body without its own digest."""
    body = {key: value for key, value in document.items() if key != "payload_digest"}
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def compose_receipt(
    *,
    acceptance_id: str,
    profile: AcceptanceProfile,
    target_environment_class: str,
    target_deployment_identity: str,
    target_identity: str | None,
    expected: ExpectedRuntime,
    observed: ObservedRuntime,
    proofs: Sequence[ProofResult],
    evidence_refs: Sequence[str],
    expires_at: str | None = None,
) -> dict[str, object]:
    """Compose a schema-conformant receipt; issued verdicts are never stale at issue time.

    Composition validates its own output: any input that would violate the
    published schema or the bounded integrity rules raises ValueError instead
    of returning a document the schema would reject.
    """
    _require_bounded(acceptance_id, "acceptance id", 256)
    _require_bounded(target_environment_class, "target environment class", 128)
    _require_bounded(target_deployment_identity, "target deployment identity", 256)
    _optional_bounded(target_identity, "target identity", 256)
    if expires_at is not None:
        _parse_utc(expires_at)
    if profile.require_target_binding:
        if observed.deployment_identity is not None and observed.deployment_identity != target_deployment_identity:
            raise ValueError(
                f"observed deployment identity {observed.deployment_identity!r} disagrees with the receipt "
                f"target deployment identity {target_deployment_identity!r}"
            )
        if expected.deployment_identity is not None and expected.deployment_identity != target_deployment_identity:
            raise ValueError(
                f"expected deployment identity {expected.deployment_identity!r} disagrees with the receipt "
                f"target deployment identity {target_deployment_identity!r}"
            )
    if not proofs:
        raise ValueError("receipts must contain at least one proof")
    if len(proofs) > _MAX_PROOFS:
        raise ValueError(f"receipts must contain at most {_MAX_PROOFS} proofs")
    decision = evaluate_acceptance(profile, expected, observed, proofs)
    issued = AcceptanceVerdict.REJECTED if decision.verdict is AcceptanceVerdict.STALE else decision.verdict
    snapshot = dependency_snapshot(profile, observed)
    document: dict[str, object] = {
        "format": RECEIPT_FORMAT,
        "schema_version": 1,
        "receipt_kind": RECEIPT_KIND,
        "acceptance_id": acceptance_id,
        "acceptance_profile": {
            "id": profile.profile_id,
            "revision": profile.profile_revision,
            "digest": profile_digest(profile),
        },
        "policy_revision": profile.policy_revision,
        "target": {
            "environment_class": target_environment_class,
            "deployment_identity": target_deployment_identity,
            "target_identity": target_identity,
        },
        "expected": {
            "artifact_digest": expected.artifact_digest,
            "source_revision": expected.source_revision,
            "artifact_identity": expected.artifact_identity,
            "config_revision": expected.config_revision,
            "deployment_operation_ref": expected.deployment_operation_ref,
            "deployment_identity": expected.deployment_identity,
        },
        "observed": {
            "runtime_identity_ref": observed.runtime_identity_ref,
            "runtime_id": observed.runtime_id,
            "source_revision": observed.source_revision,
            "artifact_digest": observed.artifact_digest,
            "artifact_version": observed.artifact_version,
            "config_revision": observed.config_revision,
            "instance_generation": observed.instance_generation,
            "observed_at": observed.observed_at,
            "deployment_identity": observed.deployment_identity,
            **(
                {"clock_provenance": observed.clock_provenance.as_document()}
                if observed.clock_provenance is not None
                else {}
            ),
        },
        "proofs": [
            {
                "kind": item.kind,
                "required": item.kind in profile.required_proof_kinds,
                "status": item.status.value,
                "authority": item.authority.value,
                "evidence_ref": item.evidence_ref,
                "runtime_generation": item.runtime_generation,
            }
            for item in proofs
        ],
        "inputs": {
            "evidence_refs": list(dict.fromkeys(evidence_refs)),
            "evidence_set_digest": evidence_set_digest(evidence_refs),
        },
        "dependency_snapshot": {
            "artifact_digest": snapshot.artifact_digest,
            "source_revision": snapshot.source_revision,
            "config_revision": snapshot.config_revision,
            "instance_generation": snapshot.instance_generation,
            "acceptance_profile_revision": snapshot.profile_revision,
            "policy_revision": snapshot.policy_revision,
        },
        "verdict": issued.value,
        "reason_codes": list(decision.reason_codes)[:_MAX_REFS],
        "currentness_at_issue": AcceptanceCurrentness.CURRENT.value,
        "expires_at": expires_at,
    }
    document["payload_digest"] = payload_digest(document)
    integrity = verify_receipt(document)
    if integrity:
        raise ValueError(f"composed receipt failed integrity verification: {'; '.join(integrity)}")
    return document


@dataclass(frozen=True)
class ReceiptProof:
    """A proof re-derived from a receipt document with its serialized required flag."""

    result: ProofResult
    required: bool | None


def _receipt_proofs(document: Mapping[str, object]) -> list[ReceiptProof]:
    """Re-derive typed proof results from a receipt document with their serialized required flags."""
    proofs: list[ReceiptProof] = []
    raw = document.get("proofs")
    if not isinstance(raw, list):
        return proofs
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        kind = item.get("kind")
        status = item.get("status")
        authority = item.get("authority")
        if not isinstance(kind, str) or not isinstance(status, str) or not isinstance(authority, str):
            continue
        evidence = item.get("evidence_ref")
        generation = item.get("runtime_generation")
        required = item.get("required")
        try:
            proofs.append(
                ReceiptProof(
                    result=ProofResult(
                        kind=kind,
                        status=ProofStatus(status),
                        authority=EvidenceAuthority(authority),
                        evidence_ref=evidence if isinstance(evidence, str) else None,
                        runtime_generation=generation if isinstance(generation, str) else None,
                    ),
                    required=required if isinstance(required, bool) else None,
                )
            )
        except ValueError:
            continue
    return proofs


def verify_receipt(
    document: object,
    *,
    schema_path: Path | None = None,
    profile: AcceptanceProfile | None = None,
) -> list[str]:
    """Validate one receipt structurally and semantically; return bounded typed findings.

    When a trusted acceptance profile is supplied, the issued verdict is
    re-derived from the receipt's own identities and proofs under that profile
    and any disagreement is a finding: the payload digest binds content, but
    never authenticates the acceptance decision itself.
    """
    findings: list[str] = []
    if schema_path is not None:
        from jsonschema import Draft202012Validator, FormatChecker

        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return [f"cannot load receipt schema: {exc}"]
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        findings.extend(
            f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in sorted(
                validator.iter_errors(document),
                key=lambda item: tuple(str(part) for part in item.absolute_path),
            )[:_MAX_FINDINGS]
        )
        if len(findings) >= _MAX_FINDINGS:
            findings.append(f"schema findings truncated at {_MAX_FINDINGS}")
        if findings:
            return findings
    if not isinstance(document, Mapping):
        return ["receipt root must be an object"]

    inputs = document.get("inputs")
    if isinstance(inputs, Mapping):
        refs = inputs.get("evidence_refs")
        declared = inputs.get("evidence_set_digest")
        if isinstance(refs, list) and isinstance(declared, str):
            try:
                recomputed = evidence_set_digest(str(ref) for ref in refs)
            except ValueError as exc:
                findings.append(f"inputs.evidence_refs: {exc}")
            else:
                if recomputed != declared:
                    findings.append(
                        f"inputs.evidence_set_digest mismatch: declared {declared}, recomputed {recomputed}"
                    )

    declared_payload = document.get("payload_digest")
    if isinstance(declared_payload, str):
        recomputed_payload = payload_digest(dict(document))
        if recomputed_payload != declared_payload:
            findings.append(f"payload_digest mismatch: declared {declared_payload}, recomputed {recomputed_payload}")

    observed_block = document.get("observed")
    if isinstance(observed_block, Mapping):
        observed_at = observed_block.get("observed_at")
        if isinstance(observed_at, str):
            try:
                _parse_utc(observed_at)
            except ValueError as exc:
                findings.append(f"observed.observed_at: {exc}")
        clock = observed_block.get("clock_provenance")
        if isinstance(clock, Mapping):
            normalization = clock.get("normalization")
            if normalization == "exact" and (
                not isinstance(clock.get("source_offset"), str) or not _CLOCK_OFFSET.match(clock["source_offset"])
            ):
                findings.append("observed.clock_provenance: exact normalization requires a valid source offset")

    expires_at = document.get("expires_at")
    if isinstance(expires_at, str):
        try:
            _parse_utc(expires_at)
        except ValueError as exc:
            findings.append(f"expires_at: {exc}")

    refs_block = document.get("inputs")
    declared_refs: set[str] = set()
    if isinstance(refs_block, Mapping) and isinstance(refs_block.get("evidence_refs"), list):
        declared_refs = {str(ref) for ref in refs_block["evidence_refs"] if isinstance(ref, str)}
    receipt_proofs = _receipt_proofs(document)
    for receipt_proof in receipt_proofs:
        item = receipt_proof.result
        if item.evidence_ref is not None and item.evidence_ref not in declared_refs:
            findings.append(f"proofs[{item.kind}].evidence_ref {item.evidence_ref} is outside inputs.evidence_refs")

    if profile is not None:
        for receipt_proof in receipt_proofs:
            expected_required = receipt_proof.result.kind in profile.required_proof_kinds
            if receipt_proof.required is not None and receipt_proof.required != expected_required:
                findings.append(
                    f"proofs[{receipt_proof.result.kind}].required flag {receipt_proof.required!r} disagrees with "
                    f"the trusted profile (required={expected_required})"
                )
        expected_block = document.get("expected")
        observed_block = document.get("observed")
        if not isinstance(expected_block, Mapping) or not isinstance(observed_block, Mapping):
            findings.append("verdict re-evaluation requires expected and observed blocks")
            return findings
        if profile.require_target_binding:
            target_block = document.get("target")
            declared_target = target_block.get("deployment_identity") if isinstance(target_block, Mapping) else None
            if not isinstance(declared_target, str):
                findings.append("verdict re-evaluation requires a typed target deployment identity")
                return findings
        profile_block = document.get("acceptance_profile")
        if not isinstance(profile_block, Mapping) or profile_block.get("digest") != profile_digest(profile):
            declared_digest = profile_block.get("digest") if isinstance(profile_block, Mapping) else None
            findings.append(
                f"acceptance_profile.digest mismatch: declared {declared_digest!r}, "
                f"trusted profile {profile_digest(profile)}"
            )
            return findings
        observed_generation = observed_block.get("instance_generation")
        observed_deployment = observed_block.get("deployment_identity")
        if not isinstance(observed_generation, str) or (
            profile.require_target_binding and not isinstance(observed_deployment, str)
        ):
            findings.append("verdict re-evaluation requires typed observed generation and deployment identity")
            return findings
        expected_digest = expected_block.get("artifact_digest")
        if not isinstance(expected_digest, str):
            findings.append("verdict re-evaluation requires a typed expected artifact digest")
            return findings
        observed_digest = observed_block.get("artifact_digest")
        observed_source = observed_block.get("source_revision")
        observed_config = observed_block.get("config_revision")
        expected_deployment = expected_block.get("deployment_identity")
        expected_source = expected_block.get("source_revision")
        expected_config = expected_block.get("config_revision")
        try:
            reobserved = ObservedRuntime(
                runtime_identity_ref=str(observed_block.get("runtime_identity_ref", "")),
                runtime_id=str(observed_block.get("runtime_id", "")),
                instance_generation=observed_generation,
                observed_at=str(observed_block.get("observed_at", "")),
                artifact_digest=observed_digest if isinstance(observed_digest, str) else None,
                source_revision=observed_source if isinstance(observed_source, str) else None,
                config_revision=observed_config if isinstance(observed_config, str) else None,
                deployment_identity=observed_deployment if isinstance(observed_deployment, str) else None,
            )
            reexpected = ExpectedRuntime(
                artifact_digest=expected_digest,
                source_revision=expected_source if isinstance(expected_source, str) else None,
                config_revision=expected_config if isinstance(expected_config, str) else None,
                deployment_identity=expected_deployment if isinstance(expected_deployment, str) else None,
            )
            decision = evaluate_acceptance(profile, reexpected, reobserved, [p.result for p in receipt_proofs])
        except ValueError as exc:
            findings.append(f"verdict re-evaluation failed: {exc}")
            return findings
        if profile.require_target_binding:
            target_block = document.get("target")
            declared_target = target_block.get("deployment_identity") if isinstance(target_block, Mapping) else None
            for label, value in (
                ("expected", reexpected.deployment_identity),
                ("observed", reobserved.deployment_identity),
            ):
                if value != declared_target:
                    findings.append(
                        f"target.deployment_identity mismatch: declared {declared_target!r}, "
                        f"{label} deployment identity {value!r}"
                    )
        issued = document.get("verdict")
        if issued != decision.verdict.value:
            findings.append(
                f"verdict mismatch: issued {issued!r}, profile re-evaluation {decision.verdict.value} "
                f"({', '.join(decision.reason_codes) if decision.reason_codes else 'no reasons'})"
            )
        issued_reasons = document.get("reason_codes")
        if issued != decision.verdict.value or issued_reasons != list(decision.reason_codes):
            if issued == decision.verdict.value:
                findings.append(
                    f"reason_codes mismatch: issued {issued_reasons!r}, "
                    f"profile re-evaluation {list(decision.reason_codes)!r}"
                )
        snapshot = document.get("dependency_snapshot")
        if isinstance(snapshot, Mapping):
            expected_snapshot = {
                "artifact_digest": reobserved.artifact_digest,
                "source_revision": reobserved.source_revision,
                "config_revision": reobserved.config_revision,
                "instance_generation": reobserved.instance_generation,
                "acceptance_profile_revision": profile.profile_revision,
                "policy_revision": profile.policy_revision,
            }
            for key, value in expected_snapshot.items():
                if snapshot.get(key) != value:
                    findings.append(
                        f"dependency_snapshot.{key} disagrees with observed identity: {snapshot.get(key)!r}"
                    )
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    """Validate one receipt file: structural, integrity, and (CLI) full schema verification.

    The CLI always verifies against the published schema. Structural-only
    library use (``schema_path=None``) never constitutes acceptance evidence;
    authoritative acceptance verification requires a trusted profile.
    """
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument(
        "--schema", type=Path, default=Path(__file__).with_name("runtime-acceptance-receipt.schema.json")
    )
    args = parser.parse_args(argv)
    try:
        if args.receipt.stat().st_size > _MAX_INPUT_BYTES:
            print(f"ERROR: receipt exceeds {_MAX_INPUT_BYTES} bytes")
            return 1
        document = json.loads(args.receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot load receipt: {exc}")
        return 1
    findings = verify_receipt(document, schema_path=args.schema)
    for finding in findings:
        print(f"ERROR: {finding}")
    print(f"runtime acceptance receipt findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

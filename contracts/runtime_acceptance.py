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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path

_MAX_REF = 2048
_MAX_REFS = 64
_MAX_PROOFS = 64
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
    """Independent evidence authority classes; composition never upgrades them."""

    CALLER_CLAIM = "caller_claim"
    WORKER_REPORT = "worker_report"
    PROVIDER_ACK = "provider_ack"
    QA_DETERMINISTIC = "qa_deterministic"
    MODEL_REVIEW = "model_review"
    INDEPENDENT_OBSERVER = "independent_observer"

    @property
    def rank(self) -> int:
        return _AUTHORITY_RANK[self]


_AUTHORITY_RANK: dict[EvidenceAuthority, int] = {
    EvidenceAuthority.CALLER_CLAIM: 0,
    EvidenceAuthority.WORKER_REPORT: 1,
    EvidenceAuthority.PROVIDER_ACK: 2,
    EvidenceAuthority.QA_DETERMINISTIC: 3,
    EvidenceAuthority.MODEL_REVIEW: 3,
    EvidenceAuthority.INDEPENDENT_OBSERVER: 4,
}


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
        if self.normalization == "exact" and self.source_offset is None:
            raise ValueError("exact normalization requires the preserved source offset")

    def as_document(self) -> dict[str, str | None]:
        return {
            "source_timestamp": self.source_timestamp,
            "source_offset": self.source_offset,
            "source_clock": self.source_clock,
            "normalization": self.normalization,
        }


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
    minimum_authority: Mapping[str, EvidenceAuthority] = field(default_factory=dict)
    require_target_binding: bool = True

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
        _require_ref(self.artifact_digest, "expected artifact digest")
        _optional_ref(self.source_revision, "expected source revision")
        _optional_ref(self.config_revision, "expected config revision")
        _optional_ref(self.artifact_identity, "expected artifact identity")
        _optional_ref(self.deployment_operation_ref, "deployment operation ref")
        _optional_ref(self.deployment_identity, "expected deployment identity")


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

    def __post_init__(self) -> None:
        _require_ref(self.runtime_identity_ref, "runtime identity ref")
        _require_ref(self.runtime_id, "runtime id")
        _require_ref(self.instance_generation, "instance generation")
        _require_ref(self.observed_at, "observed at")
        _optional_ref(self.artifact_digest, "observed artifact digest")
        _optional_ref(self.source_revision, "observed source revision")
        _optional_ref(self.artifact_version, "observed artifact version")
        _optional_ref(self.config_revision, "observed config revision")
        _optional_ref(self.deployment_identity, "observed deployment identity")


@dataclass(frozen=True)
class ProofResult:
    kind: str
    status: ProofStatus
    authority: EvidenceAuthority
    evidence_ref: str | None = None

    def __post_init__(self) -> None:
        _require_ref(self.kind, "proof kind")
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
        floor = profile.minimum_authority.get(kind)
        if item.status is ProofStatus.PROVEN and floor is not None and item.authority.rank < floor.rank:
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
) -> AcceptanceVerdict:
    """Combine the issued verdict with currentness and expiry into one bounded outcome."""
    if issued_verdict is not AcceptanceVerdict.ACCEPTED:
        return issued_verdict
    if expires_at is not None and now >= _parse_utc(expires_at):
        return AcceptanceVerdict.STALE
    currentness = derive_currentness(receipt_dependencies, current_dependencies)
    if currentness is AcceptanceCurrentness.STALE:
        return AcceptanceVerdict.STALE
    if currentness is AcceptanceCurrentness.UNKNOWN:
        return AcceptanceVerdict.INCONCLUSIVE
    return AcceptanceVerdict.ACCEPTED


def evidence_set_digest(evidence_refs: Iterable[str]) -> str:
    """Create a stable digest for the exact bounded set of evidence references."""
    refs = tuple(sorted(set(evidence_refs)))
    if len(refs) > _MAX_REFS:
        raise ValueError(f"evidence refs must contain at most {_MAX_REFS} items")
    for ref in refs:
        _require_ref(ref, "evidence ref")
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
    """Compose a schema-conformant receipt; issued verdicts are never stale at issue time."""
    _require_ref(acceptance_id, "acceptance id")
    _require_ref(target_environment_class, "target environment class")
    _require_ref(target_deployment_identity, "target deployment identity")
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
        "acceptance_profile": {"id": profile.profile_id, "revision": profile.profile_revision},
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
        "currentness_at_issue": AcceptanceCurrentness.CURRENT.value,
        "expires_at": expires_at,
    }
    document["payload_digest"] = payload_digest(document)
    return document


def verify_receipt(document: object, *, schema_path: Path | None = None) -> list[str]:
    """Validate one receipt structurally and semantically; return bounded typed findings."""
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
            )
        )
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
            if normalization == "exact" and clock.get("source_offset") is None:
                findings.append("observed.clock_provenance: unknown source clock cannot claim exact normalization")

    expires_at = document.get("expires_at")
    if isinstance(expires_at, str):
        try:
            _parse_utc(expires_at)
        except ValueError as exc:
            findings.append(f"expires_at: {exc}")
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    """Validate one receipt file given as the only argument."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument(
        "--schema", type=Path, default=Path(__file__).with_name("runtime-acceptance-receipt.schema.json")
    )
    args = parser.parse_args(argv)
    try:
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

#!/usr/bin/env python3
"""Provider-neutral release deliverable manifest and artifact closure evaluation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_DELIVERABLES = 256
_MAX_UNEXPECTED_COMPONENTS = 256


class DeliverableKind(StrEnum):
    RUNTIME_ENTRYPOINT = "runtime_entrypoint"
    OPERATOR_ENTRYPOINT = "operator_entrypoint"
    MIGRATION_TOOL = "migration_tool"
    WORKER = "worker"
    SIDECAR = "sidecar"
    ASSET = "asset"
    OTHER = "other"


class Presence(StrEnum):
    PRESENT = "PRESENT"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


class SmokeStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_REQUIRED = "NOT_REQUIRED"


class ClosureVerdict(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


class ClosureCurrentness(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class UnexpectedCriticality(StrEnum):
    CRITICAL = "critical"
    NON_CRITICAL = "non_critical"
    UNKNOWN = "unknown"


class UnexpectedDisposition(StrEnum):
    ALLOWED = "allowed"
    FORBIDDEN = "forbidden"
    UNRESOLVED = "unresolved"


def _require_text(value: str, name: str, *, limit: int = 2048) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    if len(value) > limit:
        raise ValueError(f"{name} must be at most {limit} characters")


def _require_sha256(value: str, name: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a sha256:<64 lowercase hex> digest")


def _sha256_document(document: dict[str, Any]) -> str:
    payload = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class DeliverableRequirement:
    deliverable_id: str
    kind: DeliverableKind
    required: bool = True
    expected_identity_ref: str | None = None
    smoke_profile_ref: str | None = None
    smoke_required: bool = False

    def __post_init__(self) -> None:
        _require_text(self.deliverable_id, "deliverable_id", limit=256)
        if not isinstance(self.kind, DeliverableKind):
            raise ValueError("kind must be a DeliverableKind")
        if not isinstance(self.required, bool) or not isinstance(self.smoke_required, bool):
            raise ValueError("required and smoke_required must be boolean")
        if self.expected_identity_ref is not None:
            _require_text(self.expected_identity_ref, "expected_identity_ref")
        if self.smoke_profile_ref is not None:
            _require_text(self.smoke_profile_ref, "smoke_profile_ref")
        if self.smoke_required and self.smoke_profile_ref is None:
            raise ValueError("smoke_required deliverable requires smoke_profile_ref")


@dataclass(frozen=True)
class ReleaseDeliverableManifest:
    manifest_id: str
    revision: str
    policy_ref: str
    deliverables: tuple[DeliverableRequirement, ...]

    def __post_init__(self) -> None:
        _require_text(self.manifest_id, "manifest_id", limit=256)
        _require_text(self.revision, "revision", limit=256)
        _require_text(self.policy_ref, "policy_ref")
        if not isinstance(self.deliverables, tuple):
            raise ValueError("deliverables must be a tuple")
        if not self.deliverables:
            raise ValueError("deliverables must contain at least one requirement")
        if len(self.deliverables) > _MAX_DELIVERABLES:
            raise ValueError(f"deliverables must contain at most {_MAX_DELIVERABLES} requirements")
        if not all(isinstance(item, DeliverableRequirement) for item in self.deliverables):
            raise ValueError("deliverables must contain DeliverableRequirement values")
        ids = [item.deliverable_id for item in self.deliverables]
        if len(ids) != len(set(ids)):
            raise ValueError("deliverable ids must be unique")


@dataclass(frozen=True)
class DeliverableObservation:
    deliverable_id: str
    artifact_digest: str
    presence: Presence
    identity_ref: str | None
    smoke_status: SmokeStatus
    evidence_ref: str

    def __post_init__(self) -> None:
        _require_text(self.deliverable_id, "deliverable_id", limit=256)
        _require_sha256(self.artifact_digest, "artifact_digest")
        if not isinstance(self.presence, Presence):
            raise ValueError("presence must be a Presence")
        if not isinstance(self.smoke_status, SmokeStatus):
            raise ValueError("smoke_status must be a SmokeStatus")
        if self.identity_ref is not None:
            _require_text(self.identity_ref, "identity_ref")
        _require_text(self.evidence_ref, "evidence_ref")
        if self.presence is not Presence.PRESENT and self.identity_ref is not None:
            raise ValueError("non-present deliverable cannot claim an observed identity")
        if self.presence is not Presence.PRESENT and self.smoke_status in {SmokeStatus.PASS, SmokeStatus.FAIL}:
            raise ValueError("non-present deliverable cannot claim an executed smoke result")


@dataclass(frozen=True)
class UnexpectedComponentObservation:
    component_ref: str
    artifact_digest: str
    criticality: UnexpectedCriticality
    disposition: UnexpectedDisposition
    evidence_ref: str

    def __post_init__(self) -> None:
        _require_text(self.component_ref, "component_ref")
        _require_sha256(self.artifact_digest, "artifact_digest")
        _require_text(self.evidence_ref, "evidence_ref")
        if not isinstance(self.criticality, UnexpectedCriticality):
            raise ValueError("criticality must be an UnexpectedCriticality")
        if not isinstance(self.disposition, UnexpectedDisposition):
            raise ValueError("disposition must be an UnexpectedDisposition")


def manifest_document(manifest: ReleaseDeliverableManifest) -> dict[str, Any]:
    if not isinstance(manifest, ReleaseDeliverableManifest):
        raise ValueError("manifest must be a ReleaseDeliverableManifest")
    return {
        "schema_version": 1,
        "manifest_id": manifest.manifest_id,
        "revision": manifest.revision,
        "policy_ref": manifest.policy_ref,
        "deliverables": [
            {
                "id": item.deliverable_id,
                "kind": item.kind.value,
                "required": item.required,
                "expected_identity_ref": item.expected_identity_ref,
                "smoke_profile_ref": item.smoke_profile_ref,
                "smoke_required": item.smoke_required,
            }
            for item in sorted(manifest.deliverables, key=lambda value: value.deliverable_id)
        ],
    }


def manifest_digest(manifest: ReleaseDeliverableManifest) -> str:
    return _sha256_document(manifest_document(manifest))


def evaluate_artifact_closure(
    manifest: ReleaseDeliverableManifest,
    observations: tuple[DeliverableObservation, ...],
    *,
    source_revision: str,
    artifact_ref: str,
    artifact_digest: str,
    artifact_evidence_ref: str,
    unexpected_components: tuple[UnexpectedComponentObservation, ...] = (),
) -> dict[str, Any]:
    """Evaluate exact-artifact deliverable closure without inferring requirements from contents."""
    _require_text(source_revision, "source_revision", limit=256)
    _require_text(artifact_ref, "artifact_ref")
    _require_sha256(artifact_digest, "artifact_digest")
    _require_text(artifact_evidence_ref, "artifact_evidence_ref")
    if not isinstance(manifest, ReleaseDeliverableManifest):
        raise ValueError("manifest must be a ReleaseDeliverableManifest")
    if not isinstance(observations, tuple) or not all(
        isinstance(item, DeliverableObservation) for item in observations
    ):
        raise ValueError("observations must be a tuple of DeliverableObservation values")
    if len(observations) > _MAX_DELIVERABLES:
        raise ValueError(f"observations must contain at most {_MAX_DELIVERABLES} values")
    if not isinstance(unexpected_components, tuple) or not all(
        isinstance(item, UnexpectedComponentObservation) for item in unexpected_components
    ):
        raise ValueError("unexpected_components must be a tuple of UnexpectedComponentObservation values")
    if len(unexpected_components) > _MAX_UNEXPECTED_COMPONENTS:
        raise ValueError(f"unexpected_components must contain at most {_MAX_UNEXPECTED_COMPONENTS} values")
    if any(item.artifact_digest != artifact_digest for item in observations):
        raise ValueError("deliverable observations must bind the same exact artifact digest")
    if any(item.artifact_digest != artifact_digest for item in unexpected_components):
        raise ValueError("unexpected component observations must bind the same exact artifact digest")

    requirements = {item.deliverable_id: item for item in manifest.deliverables}
    observation_map: dict[str, DeliverableObservation] = {}
    for observation in observations:
        if observation.deliverable_id not in requirements:
            raise ValueError(f"observation references undeclared deliverable: {observation.deliverable_id}")
        if observation.deliverable_id in observation_map:
            raise ValueError(f"duplicate observation for deliverable: {observation.deliverable_id}")
        observation_map[observation.deliverable_id] = observation

    component_refs = [item.component_ref for item in unexpected_components]
    if len(component_refs) != len(set(component_refs)):
        raise ValueError("unexpected component refs must be unique")

    normalized_observations: list[dict[str, Any]] = []
    missing_required: list[str] = []
    unknown_required: list[str] = []
    identity_mismatches: list[dict[str, str | None]] = []
    smoke_failures: list[dict[str, str]] = []

    for deliverable_id in sorted(requirements):
        requirement = requirements[deliverable_id]
        observation = observation_map.get(deliverable_id)
        if observation is None:
            presence = Presence.UNKNOWN
            identity_ref = None
            smoke_status = SmokeStatus.UNKNOWN
            evidence_ref = None
        else:
            presence = observation.presence
            identity_ref = observation.identity_ref
            smoke_status = observation.smoke_status
            evidence_ref = observation.evidence_ref

        normalized_observations.append(
            {
                "deliverable_id": deliverable_id,
                "artifact_digest": artifact_digest,
                "presence": presence.value,
                "identity_ref": identity_ref,
                "smoke_status": smoke_status.value,
                "evidence_ref": evidence_ref,
            }
        )

        if not requirement.required:
            continue
        if presence is Presence.MISSING:
            missing_required.append(deliverable_id)
            continue
        if presence is Presence.UNKNOWN:
            unknown_required.append(deliverable_id)
            continue
        if requirement.expected_identity_ref is not None and identity_ref != requirement.expected_identity_ref:
            identity_mismatches.append(
                {
                    "deliverable_id": deliverable_id,
                    "expected_identity_ref": requirement.expected_identity_ref,
                    "observed_identity_ref": identity_ref,
                }
            )
        if requirement.smoke_required and smoke_status is not SmokeStatus.PASS:
            smoke_failures.append({"deliverable_id": deliverable_id, "smoke_status": smoke_status.value})

    normalized_unexpected = [
        {
            "component_ref": item.component_ref,
            "artifact_digest": item.artifact_digest,
            "criticality": item.criticality.value,
            "disposition": item.disposition.value,
            "evidence_ref": item.evidence_ref,
        }
        for item in sorted(unexpected_components, key=lambda value: value.component_ref)
    ]
    blocking_unexpected = [
        item.component_ref
        for item in sorted(unexpected_components, key=lambda value: value.component_ref)
        if item.disposition is UnexpectedDisposition.FORBIDDEN
        or (
            item.disposition is UnexpectedDisposition.UNRESOLVED
            and item.criticality in {UnexpectedCriticality.CRITICAL, UnexpectedCriticality.UNKNOWN}
        )
    ]

    verdict = (
        ClosureVerdict.COMPLETE
        if not (missing_required or unknown_required or identity_mismatches or smoke_failures or blocking_unexpected)
        else ClosureVerdict.INCOMPLETE
    )
    digest = manifest_digest(manifest)
    receipt_without_digest: dict[str, Any] = {
        "schema_version": 1,
        "receipt_kind": "artifact_closure",
        "source_revision": source_revision,
        "artifact_ref": artifact_ref,
        "artifact_digest": artifact_digest,
        "artifact_evidence_ref": artifact_evidence_ref,
        "manifest": {
            "manifest_id": manifest.manifest_id,
            "revision": manifest.revision,
            "digest": digest,
            "policy_ref": manifest.policy_ref,
        },
        "observed": normalized_observations,
        "unexpected_components": normalized_unexpected,
        "missing_required": missing_required,
        "unknown_required": unknown_required,
        "identity_mismatches": identity_mismatches,
        "smoke_failures": smoke_failures,
        "blocking_unexpected": blocking_unexpected,
        "verdict": verdict.value,
    }
    return {**receipt_without_digest, "receipt_digest": _sha256_document(receipt_without_digest)}


def verify_artifact_closure_receipt_integrity(receipt: dict[str, Any]) -> bool:
    """Verify the self-contained canonical receipt digest before trusting its fields."""
    if not isinstance(receipt, dict):
        return False
    supplied = receipt.get("receipt_digest")
    if not isinstance(supplied, str) or _SHA256_RE.fullmatch(supplied) is None:
        return False
    payload = dict(receipt)
    payload.pop("receipt_digest", None)
    return _sha256_document(payload) == supplied


def classify_artifact_closure_currentness(
    receipt: dict[str, Any],
    *,
    current_source_revision: str | None,
    current_artifact_digest: str | None,
    current_artifact_evidence_ref: str | None,
    current_manifest: ReleaseDeliverableManifest | None,
) -> ClosureCurrentness:
    """Classify whether immutable closure evidence still applies to current artifact/manifest identity."""
    if not verify_artifact_closure_receipt_integrity(receipt):
        return ClosureCurrentness.UNKNOWN
    if (
        current_source_revision is None
        or current_artifact_digest is None
        or current_artifact_evidence_ref is None
        or current_manifest is None
    ):
        return ClosureCurrentness.UNKNOWN
    try:
        _require_text(current_source_revision, "current_source_revision", limit=256)
        _require_sha256(current_artifact_digest, "current_artifact_digest")
        _require_text(current_artifact_evidence_ref, "current_artifact_evidence_ref")
        current_manifest_digest = manifest_digest(current_manifest)
        receipt_source_revision = receipt["source_revision"]
        receipt_artifact_digest = receipt["artifact_digest"]
        receipt_artifact_evidence_ref = receipt["artifact_evidence_ref"]
        receipt_manifest_digest = receipt["manifest"]["digest"]
        _require_text(receipt_source_revision, "receipt.source_revision", limit=256)
        _require_sha256(receipt_artifact_digest, "receipt.artifact_digest")
        _require_text(receipt_artifact_evidence_ref, "receipt.artifact_evidence_ref")
        _require_sha256(receipt_manifest_digest, "receipt.manifest.digest")
    except (KeyError, TypeError, ValueError):
        return ClosureCurrentness.UNKNOWN

    if (
        receipt_source_revision != current_source_revision
        or receipt_artifact_digest != current_artifact_digest
        or receipt_artifact_evidence_ref != current_artifact_evidence_ref
        or receipt_manifest_digest != current_manifest_digest
    ):
        return ClosureCurrentness.STALE
    return ClosureCurrentness.CURRENT

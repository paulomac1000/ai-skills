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
_SOURCE_REVISION_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_MAX_DELIVERABLES = 256
_MAX_UNEXPECTED_COMPONENTS = 256
_RECEIPT_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "receipt_kind",
        "source_revision",
        "artifact_ref",
        "artifact_digest",
        "artifact_evidence_ref",
        "artifact_evidence_digest",
        "manifest",
        "observed",
        "unexpected_components",
        "missing_required",
        "unknown_required",
        "identity_mismatches",
        "smoke_failures",
        "blocking_unexpected",
        "verdict",
        "receipt_digest",
    }
)
_RECEIPT_MANIFEST_FIELDS = frozenset({"manifest_id", "revision", "digest", "policy_ref"})
_OBSERVED_FIELDS = frozenset(
    {
        "presence",
        "identity_ref",
        "smoke_profile_ref",
        "smoke_profile_digest",
        "smoke_status",
        "evidence_ref",
        "evidence_digest",
    }
)
_UNEXPECTED_FIELDS = frozenset({"criticality", "disposition", "evidence_ref", "evidence_digest"})
_IDENTITY_MISMATCH_FIELDS = frozenset({"deliverable_id", "expected_identity_ref", "observed_identity_ref"})
_SMOKE_FAILURE_FIELDS = frozenset(
    {"deliverable_id", "smoke_status", "expected_smoke_profile_ref", "observed_smoke_profile_ref"}
)


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
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{name} must contain only Unicode scalar values") from exc


def _require_sha256(value: str, name: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a sha256:<64 lowercase hex> digest")


def _require_source_revision(value: str, name: str) -> None:
    if not isinstance(value, str) or _SOURCE_REVISION_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a full immutable 40- or 64-hex commit id")


def _sha256_document(document: dict[str, Any]) -> str:
    payload = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _is_bounded_text(value: object, *, limit: int = 2048) -> bool:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _is_source_revision(value: object) -> bool:
    return isinstance(value, str) and _SOURCE_REVISION_RE.fullmatch(value) is not None


def _has_exact_fields(value: object, fields: frozenset[str]) -> bool:
    return isinstance(value, dict) and set(value) == fields


def _bounded_unique_text_list(value: object, *, maximum: int, limit: int) -> bool:
    if not isinstance(value, list) or len(value) > maximum:
        return False
    if not all(_is_bounded_text(item, limit=limit) for item in value):
        return False
    return len(value) == len(set(value))


def _receipt_shape_is_valid(receipt: object) -> bool:
    if not _has_exact_fields(receipt, _RECEIPT_ROOT_FIELDS):
        return False
    assert isinstance(receipt, dict)
    if receipt.get("schema_version") != 1 or receipt.get("receipt_kind") != "artifact_closure":
        return False
    if not _is_source_revision(receipt.get("source_revision")):
        return False
    if not _is_bounded_text(receipt.get("artifact_ref")):
        return False
    artifact_digest = receipt.get("artifact_digest")
    if not _is_sha256(artifact_digest):
        return False
    if not _is_bounded_text(receipt.get("artifact_evidence_ref")):
        return False
    if not _is_sha256(receipt.get("artifact_evidence_digest")):
        return False
    if not _is_sha256(receipt.get("receipt_digest")):
        return False
    if receipt.get("verdict") not in {ClosureVerdict.COMPLETE.value, ClosureVerdict.INCOMPLETE.value}:
        return False

    manifest = receipt.get("manifest")
    if not _has_exact_fields(manifest, _RECEIPT_MANIFEST_FIELDS):
        return False
    assert isinstance(manifest, dict)
    if not _is_bounded_text(manifest.get("manifest_id"), limit=256):
        return False
    if not _is_bounded_text(manifest.get("revision"), limit=256):
        return False
    if not _is_sha256(manifest.get("digest")):
        return False
    if not _is_bounded_text(manifest.get("policy_ref")):
        return False

    observed = receipt.get("observed")
    if not isinstance(observed, dict) or len(observed) > _MAX_DELIVERABLES:
        return False
    for deliverable_id, item in observed.items():
        if not _is_bounded_text(deliverable_id, limit=256):
            return False
        if not _has_exact_fields(item, _OBSERVED_FIELDS):
            return False
        assert isinstance(item, dict)
        if item.get("presence") not in {state.value for state in Presence}:
            return False
        identity_ref = item.get("identity_ref")
        if identity_ref is not None and not _is_bounded_text(identity_ref):
            return False
        smoke_profile_ref = item.get("smoke_profile_ref")
        if smoke_profile_ref is not None and not _is_bounded_text(smoke_profile_ref):
            return False
        smoke_profile_digest = item.get("smoke_profile_digest")
        if smoke_profile_digest is not None and not _is_sha256(smoke_profile_digest):
            return False
        smoke_status = item.get("smoke_status")
        if smoke_status not in {status.value for status in SmokeStatus}:
            return False
        if smoke_status in {SmokeStatus.PASS.value, SmokeStatus.FAIL.value} and (
            smoke_profile_ref is None or smoke_profile_digest is None
        ):
            return False
        evidence_ref = item.get("evidence_ref")
        evidence_digest = item.get("evidence_digest")
        if evidence_ref is None:
            if evidence_digest is not None:
                return False
            if item.get("presence") != Presence.UNKNOWN.value or smoke_status != SmokeStatus.UNKNOWN.value:
                return False
        elif not _is_bounded_text(evidence_ref) or not _is_sha256(evidence_digest):
            return False
        if item.get("presence") != Presence.PRESENT.value:
            if identity_ref is not None or smoke_status in {SmokeStatus.PASS.value, SmokeStatus.FAIL.value}:
                return False

    unexpected = receipt.get("unexpected_components")
    if not isinstance(unexpected, dict) or len(unexpected) > _MAX_UNEXPECTED_COMPONENTS:
        return False
    for component_ref, item in unexpected.items():
        if not _is_bounded_text(component_ref):
            return False
        if not _has_exact_fields(item, _UNEXPECTED_FIELDS):
            return False
        assert isinstance(item, dict)
        if item.get("criticality") not in {value.value for value in UnexpectedCriticality}:
            return False
        if item.get("disposition") not in {value.value for value in UnexpectedDisposition}:
            return False
        if not _is_bounded_text(item.get("evidence_ref")) or not _is_sha256(item.get("evidence_digest")):
            return False

    if not _bounded_unique_text_list(receipt.get("missing_required"), maximum=_MAX_DELIVERABLES, limit=256):
        return False
    if not _bounded_unique_text_list(receipt.get("unknown_required"), maximum=_MAX_DELIVERABLES, limit=256):
        return False
    if not _bounded_unique_text_list(
        receipt.get("blocking_unexpected"), maximum=_MAX_UNEXPECTED_COMPONENTS, limit=2048
    ):
        return False

    identity_mismatches = receipt.get("identity_mismatches")
    if not isinstance(identity_mismatches, list) or len(identity_mismatches) > _MAX_DELIVERABLES:
        return False
    mismatch_ids: list[str] = []
    for item in identity_mismatches:
        if not _has_exact_fields(item, _IDENTITY_MISMATCH_FIELDS):
            return False
        assert isinstance(item, dict)
        deliverable_id = item.get("deliverable_id")
        if not _is_bounded_text(deliverable_id, limit=256):
            return False
        assert isinstance(deliverable_id, str)
        mismatch_ids.append(deliverable_id)
        if not _is_bounded_text(item.get("expected_identity_ref")):
            return False
        observed_identity_ref = item.get("observed_identity_ref")
        if observed_identity_ref is not None and not _is_bounded_text(observed_identity_ref):
            return False
    if len(mismatch_ids) != len(set(mismatch_ids)):
        return False

    smoke_failures = receipt.get("smoke_failures")
    if not isinstance(smoke_failures, list) or len(smoke_failures) > _MAX_DELIVERABLES:
        return False
    smoke_ids: list[str] = []
    for item in smoke_failures:
        if not _has_exact_fields(item, _SMOKE_FAILURE_FIELDS):
            return False
        assert isinstance(item, dict)
        deliverable_id = item.get("deliverable_id")
        if not _is_bounded_text(deliverable_id, limit=256):
            return False
        assert isinstance(deliverable_id, str)
        smoke_ids.append(deliverable_id)
        if item.get("smoke_status") not in {status.value for status in SmokeStatus}:
            return False
        if not _is_bounded_text(item.get("expected_smoke_profile_ref")):
            return False
        observed_smoke_profile_ref = item.get("observed_smoke_profile_ref")
        if observed_smoke_profile_ref is not None and not _is_bounded_text(observed_smoke_profile_ref):
            return False
    return len(smoke_ids) == len(set(smoke_ids))


@dataclass(frozen=True)
class DeliverableRequirement:
    deliverable_id: str
    kind: DeliverableKind
    required: bool = True
    expected_identity_ref: str | None = None
    smoke_profile_ref: str | None = None
    smoke_profile_digest: str | None = None
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
        if self.smoke_profile_digest is not None:
            _require_sha256(self.smoke_profile_digest, "smoke_profile_digest")
        if self.smoke_required and (self.smoke_profile_ref is None or self.smoke_profile_digest is None):
            raise ValueError("smoke_required deliverable requires immutable smoke profile ref and digest")


@dataclass(frozen=True)
class UnexpectedComponentPolicy:
    component_ref: str
    disposition: UnexpectedDisposition

    def __post_init__(self) -> None:
        _require_text(self.component_ref, "component_ref")
        if self.disposition not in {UnexpectedDisposition.ALLOWED, UnexpectedDisposition.FORBIDDEN}:
            raise ValueError("unexpected component policy disposition must be allowed or forbidden")


@dataclass(frozen=True)
class ReleaseDeliverableManifest:
    manifest_id: str
    revision: str
    policy_ref: str
    deliverables: tuple[DeliverableRequirement, ...]
    unexpected_component_dispositions: tuple[UnexpectedComponentPolicy, ...] = ()

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
        if not isinstance(self.unexpected_component_dispositions, tuple):
            raise ValueError("unexpected_component_dispositions must be a tuple")
        if len(self.unexpected_component_dispositions) > _MAX_UNEXPECTED_COMPONENTS:
            raise ValueError(
                f"unexpected_component_dispositions must contain at most {_MAX_UNEXPECTED_COMPONENTS} values"
            )
        if not all(isinstance(item, UnexpectedComponentPolicy) for item in self.unexpected_component_dispositions):
            raise ValueError("unexpected_component_dispositions must contain UnexpectedComponentPolicy values")
        component_refs = [item.component_ref for item in self.unexpected_component_dispositions]
        if len(component_refs) != len(set(component_refs)):
            raise ValueError("unexpected component policy refs must be unique")


@dataclass(frozen=True)
class DeliverableObservation:
    deliverable_id: str
    artifact_digest: str
    presence: Presence
    identity_ref: str | None
    smoke_profile_ref: str | None
    smoke_profile_digest: str | None
    smoke_status: SmokeStatus
    evidence_ref: str
    evidence_digest: str

    def __post_init__(self) -> None:
        _require_text(self.deliverable_id, "deliverable_id", limit=256)
        _require_sha256(self.artifact_digest, "artifact_digest")
        if not isinstance(self.presence, Presence):
            raise ValueError("presence must be a Presence")
        if not isinstance(self.smoke_status, SmokeStatus):
            raise ValueError("smoke_status must be a SmokeStatus")
        if self.identity_ref is not None:
            _require_text(self.identity_ref, "identity_ref")
        if self.smoke_profile_ref is not None:
            _require_text(self.smoke_profile_ref, "smoke_profile_ref")
        if self.smoke_profile_digest is not None:
            _require_sha256(self.smoke_profile_digest, "smoke_profile_digest")
        if self.smoke_status in {SmokeStatus.PASS, SmokeStatus.FAIL} and (
            self.smoke_profile_ref is None or self.smoke_profile_digest is None
        ):
            raise ValueError("executed smoke result requires immutable smoke profile ref and digest")
        _require_text(self.evidence_ref, "evidence_ref")
        _require_sha256(self.evidence_digest, "evidence_digest")
        if self.presence is not Presence.PRESENT and self.identity_ref is not None:
            raise ValueError("non-present deliverable cannot claim an observed identity")
        if self.presence is not Presence.PRESENT and self.smoke_status in {SmokeStatus.PASS, SmokeStatus.FAIL}:
            raise ValueError("non-present deliverable cannot claim an executed smoke result")


@dataclass(frozen=True)
class UnexpectedComponentObservation:
    component_ref: str
    artifact_digest: str
    criticality: UnexpectedCriticality
    evidence_ref: str
    evidence_digest: str

    def __post_init__(self) -> None:
        _require_text(self.component_ref, "component_ref")
        _require_sha256(self.artifact_digest, "artifact_digest")
        _require_text(self.evidence_ref, "evidence_ref")
        _require_sha256(self.evidence_digest, "evidence_digest")
        if not isinstance(self.criticality, UnexpectedCriticality):
            raise ValueError("criticality must be an UnexpectedCriticality")


def manifest_document(manifest: ReleaseDeliverableManifest) -> dict[str, Any]:
    if not isinstance(manifest, ReleaseDeliverableManifest):
        raise ValueError("manifest must be a ReleaseDeliverableManifest")
    return {
        "schema_version": 1,
        "manifest_id": manifest.manifest_id,
        "revision": manifest.revision,
        "policy_ref": manifest.policy_ref,
        "deliverables": {
            item.deliverable_id: {
                "kind": item.kind.value,
                "required": item.required,
                "expected_identity_ref": item.expected_identity_ref,
                "smoke_profile_ref": item.smoke_profile_ref,
                "smoke_profile_digest": item.smoke_profile_digest,
                "smoke_required": item.smoke_required,
            }
            for item in sorted(manifest.deliverables, key=lambda value: value.deliverable_id)
        },
        "unexpected_component_dispositions": {
            item.component_ref: item.disposition.value
            for item in sorted(
                manifest.unexpected_component_dispositions,
                key=lambda value: value.component_ref,
            )
        },
    }


def manifest_digest(manifest: ReleaseDeliverableManifest) -> str:
    return _sha256_document(manifest_document(manifest))


def _artifact_evidence_digest(
    artifact_digest: str,
    observed: dict[str, dict[str, Any]],
    unexpected_components: dict[str, dict[str, Any]],
) -> str:
    return _sha256_document(
        {
            "schema_version": 1,
            "artifact_digest": artifact_digest,
            "observed": {
                deliverable_id: {
                    "presence": item["presence"],
                    "identity_ref": item["identity_ref"],
                    "smoke_profile_ref": item["smoke_profile_ref"],
                    "smoke_profile_digest": item["smoke_profile_digest"],
                    "smoke_status": item["smoke_status"],
                    "evidence_ref": item["evidence_ref"],
                    "evidence_digest": item["evidence_digest"],
                }
                for deliverable_id, item in sorted(observed.items())
            },
            "unexpected_components": {
                component_ref: {
                    "criticality": item["criticality"],
                    "evidence_ref": item["evidence_ref"],
                    "evidence_digest": item["evidence_digest"],
                }
                for component_ref, item in sorted(unexpected_components.items())
            },
        }
    )


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
    _require_source_revision(source_revision, "source_revision")
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

    normalized_observations: dict[str, dict[str, Any]] = {}
    missing_required: list[str] = []
    unknown_required: list[str] = []
    identity_mismatches: list[dict[str, str | None]] = []
    smoke_failures: list[dict[str, str | None]] = []

    for deliverable_id in sorted(requirements):
        requirement = requirements[deliverable_id]
        current_observation = observation_map.get(deliverable_id)
        if current_observation is None:
            presence = Presence.UNKNOWN
            identity_ref = None
            smoke_profile_ref = None
            smoke_profile_digest = None
            smoke_status = SmokeStatus.UNKNOWN
            evidence_ref = None
            evidence_digest = None
        else:
            presence = current_observation.presence
            identity_ref = current_observation.identity_ref
            smoke_profile_ref = current_observation.smoke_profile_ref
            smoke_profile_digest = current_observation.smoke_profile_digest
            smoke_status = current_observation.smoke_status
            evidence_ref = current_observation.evidence_ref
            evidence_digest = current_observation.evidence_digest

        normalized_observations[deliverable_id] = {
            "presence": presence.value,
            "identity_ref": identity_ref,
            "smoke_profile_ref": smoke_profile_ref,
            "smoke_profile_digest": smoke_profile_digest,
            "smoke_status": smoke_status.value,
            "evidence_ref": evidence_ref,
            "evidence_digest": evidence_digest,
        }

        if requirement.required:
            if presence is Presence.MISSING:
                missing_required.append(deliverable_id)
                continue
            if presence is Presence.UNKNOWN:
                unknown_required.append(deliverable_id)
                continue
        elif presence is not Presence.PRESENT:
            continue
        if requirement.expected_identity_ref is not None and identity_ref != requirement.expected_identity_ref:
            identity_mismatches.append(
                {
                    "deliverable_id": deliverable_id,
                    "expected_identity_ref": requirement.expected_identity_ref,
                    "observed_identity_ref": identity_ref,
                }
            )
        if requirement.smoke_required and (
            smoke_status is not SmokeStatus.PASS
            or smoke_profile_ref != requirement.smoke_profile_ref
            or smoke_profile_digest != requirement.smoke_profile_digest
        ):
            smoke_failures.append(
                {
                    "deliverable_id": deliverable_id,
                    "smoke_status": smoke_status.value,
                    "expected_smoke_profile_ref": requirement.smoke_profile_ref,
                    "observed_smoke_profile_ref": smoke_profile_ref,
                }
            )

    trusted_dispositions = {item.component_ref: item.disposition for item in manifest.unexpected_component_dispositions}
    normalized_unexpected = {
        item.component_ref: {
            "criticality": item.criticality.value,
            "disposition": trusted_dispositions.get(item.component_ref, UnexpectedDisposition.UNRESOLVED).value,
            "evidence_ref": item.evidence_ref,
            "evidence_digest": item.evidence_digest,
        }
        for item in sorted(unexpected_components, key=lambda value: value.component_ref)
    }
    blocking_unexpected = [
        component_ref
        for component_ref, item in normalized_unexpected.items()
        if item["disposition"] != UnexpectedDisposition.ALLOWED.value
    ]
    artifact_evidence_digest = _artifact_evidence_digest(
        artifact_digest, normalized_observations, normalized_unexpected
    )

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
        "artifact_evidence_digest": artifact_evidence_digest,
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
    """Verify bounded receipt shape and canonical digest before trusting any receipt fields."""
    if not _receipt_shape_is_valid(receipt):
        return False
    if (
        _artifact_evidence_digest(receipt["artifact_digest"], receipt["observed"], receipt["unexpected_components"])
        != receipt["artifact_evidence_digest"]
    ):
        return False
    supplied = receipt["receipt_digest"]
    payload = dict(receipt)
    payload.pop("receipt_digest", None)
    return _sha256_document(payload) == supplied


def verify_artifact_closure_receipt_semantics(
    receipt: dict[str, Any],
    manifest: object,
) -> bool:
    """Verify derived closure fields against the trusted manifest that owns requirements."""
    if not verify_artifact_closure_receipt_integrity(receipt):
        return False
    if not isinstance(manifest, ReleaseDeliverableManifest):
        return False

    receipt_manifest = receipt["manifest"]
    expected_manifest_digest = manifest_digest(manifest)
    if (
        receipt_manifest["manifest_id"] != manifest.manifest_id
        or receipt_manifest["revision"] != manifest.revision
        or receipt_manifest["policy_ref"] != manifest.policy_ref
        or receipt_manifest["digest"] != expected_manifest_digest
    ):
        return False

    requirements = {item.deliverable_id: item for item in manifest.deliverables}
    observed = receipt["observed"]
    if not isinstance(observed, dict) or set(observed) != set(requirements):
        return False
    observed_map = observed

    missing_required: list[str] = []
    unknown_required: list[str] = []
    identity_mismatches: list[dict[str, str | None]] = []
    smoke_failures: list[dict[str, str | None]] = []
    for deliverable_id in sorted(requirements):
        requirement = requirements[deliverable_id]
        observation = observed_map[deliverable_id]
        presence = observation["presence"]
        if requirement.required:
            if presence == Presence.MISSING.value:
                missing_required.append(deliverable_id)
                continue
            if presence == Presence.UNKNOWN.value:
                unknown_required.append(deliverable_id)
                continue
        elif presence != Presence.PRESENT.value:
            continue
        identity_ref = observation["identity_ref"]
        smoke_profile_ref = observation["smoke_profile_ref"]
        smoke_profile_digest = observation["smoke_profile_digest"]
        smoke_status = observation["smoke_status"]
        if requirement.expected_identity_ref is not None and identity_ref != requirement.expected_identity_ref:
            identity_mismatches.append(
                {
                    "deliverable_id": deliverable_id,
                    "expected_identity_ref": requirement.expected_identity_ref,
                    "observed_identity_ref": identity_ref,
                }
            )
        if requirement.smoke_required and (
            smoke_status != SmokeStatus.PASS.value
            or smoke_profile_ref != requirement.smoke_profile_ref
            or smoke_profile_digest != requirement.smoke_profile_digest
        ):
            smoke_failures.append(
                {
                    "deliverable_id": deliverable_id,
                    "smoke_status": smoke_status,
                    "expected_smoke_profile_ref": requirement.smoke_profile_ref,
                    "observed_smoke_profile_ref": smoke_profile_ref,
                }
            )

    trusted_dispositions = {
        item.component_ref: item.disposition.value for item in manifest.unexpected_component_dispositions
    }
    blocking_unexpected: list[str] = []
    for component_ref, item in sorted(receipt["unexpected_components"].items()):
        expected_disposition = trusted_dispositions.get(component_ref, UnexpectedDisposition.UNRESOLVED.value)
        if item["disposition"] != expected_disposition:
            return False
        if expected_disposition != UnexpectedDisposition.ALLOWED.value:
            blocking_unexpected.append(component_ref)
    verdict = (
        ClosureVerdict.COMPLETE.value
        if not (missing_required or unknown_required or identity_mismatches or smoke_failures or blocking_unexpected)
        else ClosureVerdict.INCOMPLETE.value
    )
    return (
        receipt["missing_required"] == missing_required
        and receipt["unknown_required"] == unknown_required
        and receipt["identity_mismatches"] == identity_mismatches
        and receipt["smoke_failures"] == smoke_failures
        and receipt["blocking_unexpected"] == blocking_unexpected
        and receipt["verdict"] == verdict
    )


def classify_artifact_closure_currentness(
    receipt: dict[str, Any],
    *,
    current_source_revision: str | None,
    current_artifact_ref: str | None,
    current_artifact_digest: str | None,
    current_artifact_evidence_ref: str | None,
    current_artifact_evidence_digest: str | None,
    current_manifest: ReleaseDeliverableManifest | None,
    receipt_manifest: ReleaseDeliverableManifest | None = None,
) -> ClosureCurrentness:
    """Classify whether immutable closure evidence still applies to current artifact/manifest identity."""
    if not verify_artifact_closure_receipt_integrity(receipt):
        return ClosureCurrentness.UNKNOWN
    if (
        current_source_revision is None
        or current_artifact_ref is None
        or current_artifact_digest is None
        or current_artifact_evidence_ref is None
        or current_artifact_evidence_digest is None
        or current_manifest is None
    ):
        return ClosureCurrentness.UNKNOWN
    try:
        _require_source_revision(current_source_revision, "current_source_revision")
        _require_text(current_artifact_ref, "current_artifact_ref")
        _require_sha256(current_artifact_digest, "current_artifact_digest")
        _require_text(current_artifact_evidence_ref, "current_artifact_evidence_ref")
        _require_sha256(current_artifact_evidence_digest, "current_artifact_evidence_digest")
        current_manifest_digest = manifest_digest(current_manifest)
        receipt_source_revision = receipt["source_revision"]
        receipt_artifact_ref = receipt["artifact_ref"]
        receipt_artifact_digest = receipt["artifact_digest"]
        receipt_artifact_evidence_ref = receipt["artifact_evidence_ref"]
        receipt_artifact_evidence_digest = receipt["artifact_evidence_digest"]
        receipt_manifest_digest = receipt["manifest"]["digest"]
        _require_source_revision(receipt_source_revision, "receipt.source_revision")
        _require_text(receipt_artifact_ref, "receipt.artifact_ref")
        _require_sha256(receipt_artifact_digest, "receipt.artifact_digest")
        _require_text(receipt_artifact_evidence_ref, "receipt.artifact_evidence_ref")
        _require_sha256(receipt_artifact_evidence_digest, "receipt.artifact_evidence_digest")
        _require_sha256(receipt_manifest_digest, "receipt.manifest.digest")
    except (KeyError, TypeError, ValueError):
        return ClosureCurrentness.UNKNOWN

    trusted_receipt_manifest = receipt_manifest
    if trusted_receipt_manifest is None and receipt_manifest_digest == current_manifest_digest:
        trusted_receipt_manifest = current_manifest
    if trusted_receipt_manifest is None:
        return ClosureCurrentness.UNKNOWN
    if not verify_artifact_closure_receipt_semantics(receipt, trusted_receipt_manifest):
        return ClosureCurrentness.UNKNOWN

    if (
        receipt_source_revision != current_source_revision
        or receipt_artifact_ref != current_artifact_ref
        or receipt_artifact_digest != current_artifact_digest
        or receipt_artifact_evidence_ref != current_artifact_evidence_ref
        or receipt_artifact_evidence_digest != current_artifact_evidence_digest
        or receipt_manifest_digest != current_manifest_digest
    ):
        return ClosureCurrentness.STALE
    return ClosureCurrentness.CURRENT

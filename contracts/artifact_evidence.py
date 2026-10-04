#!/usr/bin/env python3
"""Collision-safe exact artifact evidence construction."""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

_DIGEST_PREFIX = "sha256:"
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ENCODING = "length-prefixed-file-tree-v1"
_PATH_NORMALIZATION = "relative-posix-nfc-v1"
_METADATA_MODE = "regular-file-content-only-v1"
_DOMAIN = b"ai-skills/artifact-tree/v1\x00"

CoverageState = Literal["exact", "partial", "unknown"]
TruthState = Literal["true", "false", "unknown"]


class ArtifactEvidenceError(ValueError):
    """Raised when inputs cannot define a canonical artifact subject."""


@dataclass(frozen=True)
class ArtifactBounds:
    max_files: int = 10_000
    max_bytes: int = 128 * 1024 * 1024
    max_depth: int = 64
    max_duration_ms: int = 30_000

    def __post_init__(self) -> None:
        for field, value in (
            ("max_files", self.max_files),
            ("max_bytes", self.max_bytes),
            ("max_depth", self.max_depth),
            ("max_duration_ms", self.max_duration_ms),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ArtifactEvidenceError(f"{field} must be a positive integer")


@dataclass(frozen=True)
class ArtifactEntry:
    path: str
    content: bytes
    file_type: str = "regular_file"


@dataclass(frozen=True)
class ConstructionProfile:
    revision: str
    policy_ref: str
    bounds: ArtifactBounds = ArtifactBounds()

    def __post_init__(self) -> None:
        if not isinstance(self.revision, str) or not self.revision.strip():
            raise ArtifactEvidenceError("profile revision must be a non-empty string")
        if not isinstance(self.policy_ref, str) or not self.policy_ref.strip():
            raise ArtifactEvidenceError("profile policy_ref must be a non-empty string")


def _sha256(data: bytes) -> str:
    return _DIGEST_PREFIX + hashlib.sha256(data).hexdigest()


def _frame(payload: bytes) -> bytes:
    return len(payload).to_bytes(8, "big", signed=False) + payload


def _elapsed_ms(started_ns: int, clock_ns: Callable[[], int]) -> float:
    return (clock_ns() - started_ns) / 1_000_000


def _normalized_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ArtifactEvidenceError("artifact path must be a non-empty string")
    normalized = unicodedata.normalize("NFC", value)
    if normalized.startswith("/") or "\\" in normalized or "\x00" in normalized:
        raise ArtifactEvidenceError(f"artifact path is not portable relative POSIX form: {value!r}")
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ArtifactEvidenceError(f"artifact path contains an ambiguous segment: {value!r}")
    return "/".join(parts)


def _profile_document(profile: ConstructionProfile) -> dict[str, Any]:
    bounds = profile.bounds
    document = {
        "revision": profile.revision,
        "policy_ref": profile.policy_ref,
        "canonical_encoding": _ENCODING,
        "path_normalization": _PATH_NORMALIZATION,
        "metadata_mode": _METADATA_MODE,
        "bounds": {
            "max_files": bounds.max_files,
            "max_bytes": bounds.max_bytes,
            "max_depth": bounds.max_depth,
            "max_duration_ms": bounds.max_duration_ms,
        },
    }
    canonical = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return {**document, "profile_digest": _sha256(canonical)}


def _truth(value: bool | None) -> TruthState:
    if value is None:
        return "unknown"
    return "true" if value else "false"


def _requested_match(
    *,
    requested_kind: str,
    requested_value: str,
    artifact_digest: str | None,
    package_version: str | None,
    source_revision: str | None,
) -> TruthState:
    if requested_kind == "artifact_digest":
        return "unknown" if artifact_digest is None else _truth(requested_value == artifact_digest)
    if requested_kind == "version":
        return "unknown" if package_version is None else _truth(requested_value == package_version)
    if requested_kind == "source_revision":
        return "unknown" if source_revision is None else _truth(requested_value == source_revision)
    return "unknown"


def _non_exact(
    *,
    subject_ref: str,
    profile: ConstructionProfile,
    requested_kind: str,
    requested_value: str,
    state: CoverageState,
    file_count: int,
    byte_count: int,
    max_depth_observed: int,
    reason: str,
    limit_hit: bool,
    enumeration_complete: bool,
    package_version: str | None,
    source_revision: str | None,
    observation_refs: Sequence[str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "subject_ref": subject_ref,
        "construction_profile": _profile_document(profile),
        "coverage": {
            "state": state,
            "file_count": file_count,
            "byte_count": byte_count,
            "max_depth_observed": max_depth_observed,
            "limit_hit": limit_hit,
            "omitted_reason": reason,
            "enumeration_complete": enumeration_complete,
        },
        "requested_identity": {
            "kind": requested_kind,
            "value": requested_value,
            "preserved_from_admission": True,
        },
        "observed_identity": {
            "artifact_digest": None,
            "package_version": package_version,
            "source_revision": source_revision,
            "observation_refs": list(observation_refs),
        },
        "claims": {
            "artifact_exact": "false" if state == "partial" else "unknown",
            "requested_identity_matched": _requested_match(
                requested_kind=requested_kind,
                requested_value=requested_value,
                artifact_digest=None,
                package_version=package_version,
                source_revision=source_revision,
            ),
            "source_compatibility_established": "unknown",
            "runtime_compatibility_established": "unknown",
        },
    }


def construct_artifact_evidence(
    entries: Iterable[ArtifactEntry],
    *,
    subject_ref: str,
    profile: ConstructionProfile,
    requested_kind: Literal["version", "package_spec", "source_revision", "artifact_digest", "other"],
    requested_value: str,
    enumeration_complete: bool,
    package_version: str | None = None,
    source_revision: str | None = None,
    observation_refs: Sequence[str] = (),
    clock_ns: Callable[[], int] = time.monotonic_ns,
) -> dict[str, Any]:
    """Construct evidence from an authority-owned complete artifact inventory.

    V1 intentionally has no exclusion argument. Policy establishes the subject
    root and the complete inventory before it may set enumeration_complete=True.
    """
    if not isinstance(subject_ref, str) or not subject_ref.strip():
        raise ArtifactEvidenceError("subject_ref must be a non-empty string")
    if not isinstance(requested_value, str) or not requested_value.strip():
        raise ArtifactEvidenceError("requested_value must be a non-empty string")
    if not isinstance(enumeration_complete, bool):
        raise ArtifactEvidenceError("enumeration_complete must be boolean")
    if not isinstance(observation_refs, Sequence) or isinstance(
        observation_refs,
        (str, bytes, bytearray),
    ):
        raise ArtifactEvidenceError("observation_refs must be an array of strings")
    if not all(isinstance(item, str) and item.strip() for item in observation_refs):
        raise ArtifactEvidenceError("observation_refs entries must be non-empty strings")
    if len(set(observation_refs)) != len(observation_refs):
        raise ArtifactEvidenceError("observation_refs must be unique")

    started = clock_ns()
    buffered: list[tuple[bytes, bytes]] = []
    seen: set[str] = set()
    file_count = 0
    byte_count = 0
    max_depth_observed = 0
    bounds = profile.bounds

    def non_exact(state: CoverageState, reason: str, *, limit_hit: bool, complete: bool) -> dict[str, Any]:
        return _non_exact(
            subject_ref=subject_ref,
            profile=profile,
            requested_kind=requested_kind,
            requested_value=requested_value,
            state=state,
            file_count=file_count,
            byte_count=byte_count,
            max_depth_observed=max_depth_observed,
            reason=reason,
            limit_hit=limit_hit,
            enumeration_complete=complete,
            package_version=package_version,
            source_revision=source_revision,
            observation_refs=observation_refs,
        )

    for entry in entries:
        if _elapsed_ms(started, clock_ns) > bounds.max_duration_ms:
            return non_exact("partial", "time_limit", limit_hit=True, complete=False)
        if not isinstance(entry, ArtifactEntry):
            raise ArtifactEvidenceError("artifact entries must be ArtifactEntry records")
        if entry.file_type != "regular_file":
            return non_exact("unknown", "unsupported_file_type", limit_hit=False, complete=False)

        path = _normalized_path(entry.path)
        if path in seen:
            raise ArtifactEvidenceError(f"duplicate normalized artifact path: {path}")
        seen.add(path)
        if not isinstance(entry.content, bytes):
            raise ArtifactEvidenceError(f"artifact content must be bytes: {path}")

        depth = len(path.split("/"))
        max_depth_observed = max(max_depth_observed, depth)
        if depth > bounds.max_depth:
            return non_exact("partial", "depth_limit", limit_hit=True, complete=False)
        if file_count + 1 > bounds.max_files:
            return non_exact("partial", "file_limit", limit_hit=True, complete=False)
        if byte_count + len(entry.content) > bounds.max_bytes:
            return non_exact("partial", "byte_limit", limit_hit=True, complete=False)

        buffered.append((path.encode("utf-8"), entry.content))
        file_count += 1
        byte_count += len(entry.content)

    if _elapsed_ms(started, clock_ns) > bounds.max_duration_ms:
        return non_exact(
            "partial",
            "time_limit",
            limit_hit=True,
            complete=enumeration_complete,
        )
    if not enumeration_complete:
        return non_exact(
            "partial",
            "enumeration_incomplete",
            limit_hit=False,
            complete=False,
        )

    hasher = hashlib.sha256()
    hasher.update(_DOMAIN)
    hasher.update(len(buffered).to_bytes(8, "big", signed=False))
    for path_bytes, content in sorted(buffered, key=lambda item: item[0]):
        hasher.update(b"F")
        hasher.update(_frame(path_bytes))
        hasher.update(_frame(content))
    artifact_digest = _DIGEST_PREFIX + hasher.hexdigest()

    if _elapsed_ms(started, clock_ns) > bounds.max_duration_ms:
        return non_exact("partial", "time_limit", limit_hit=True, complete=True)

    return {
        "schema_version": 1,
        "subject_ref": subject_ref,
        "construction_profile": _profile_document(profile),
        "coverage": {
            "state": "exact",
            "file_count": file_count,
            "byte_count": byte_count,
            "max_depth_observed": max_depth_observed,
            "limit_hit": False,
            "omitted_reason": None,
            "enumeration_complete": True,
        },
        "requested_identity": {
            "kind": requested_kind,
            "value": requested_value,
            "preserved_from_admission": True,
        },
        "observed_identity": {
            "artifact_digest": artifact_digest,
            "package_version": package_version,
            "source_revision": source_revision,
            "observation_refs": list(observation_refs),
        },
        "claims": {
            "artifact_exact": "true",
            "requested_identity_matched": _requested_match(
                requested_kind=requested_kind,
                requested_value=requested_value,
                artifact_digest=artifact_digest,
                package_version=package_version,
                source_revision=source_revision,
            ),
            "source_compatibility_established": "unknown",
            "runtime_compatibility_established": "unknown",
        },
    }


def validate_artifact_evidence_semantics(evidence: object) -> tuple[str, ...]:
    """Validate semantic relationships that JSON Schema cannot express."""
    if not isinstance(evidence, Mapping):
        return ("artifact evidence must be an object",)

    findings: list[str] = []
    profile = evidence.get("construction_profile")
    if not isinstance(profile, Mapping):
        return ("construction_profile must be an object",)
    bounds = profile.get("bounds")
    if not isinstance(bounds, Mapping):
        return ("construction_profile.bounds must be an object",)

    try:
        reconstructed = ConstructionProfile(
            revision=profile.get("revision"),
            policy_ref=profile.get("policy_ref"),
            bounds=ArtifactBounds(
                max_files=bounds.get("max_files"),
                max_bytes=bounds.get("max_bytes"),
                max_depth=bounds.get("max_depth"),
                max_duration_ms=bounds.get("max_duration_ms"),
            ),
        )
    except ArtifactEvidenceError as error:
        findings.append(str(error))
    else:
        expected_profile = _profile_document(reconstructed)
        for field in (
            "profile_digest",
            "canonical_encoding",
            "path_normalization",
            "metadata_mode",
        ):
            if profile.get(field) != expected_profile[field]:
                findings.append(f"construction_profile.{field} does not match canonical profile semantics")

    coverage = evidence.get("coverage")
    requested = evidence.get("requested_identity")
    observed = evidence.get("observed_identity")
    claims = evidence.get("claims")
    if not isinstance(coverage, Mapping):
        findings.append("coverage must be an object")
    if not isinstance(requested, Mapping):
        findings.append("requested_identity must be an object")
    if not isinstance(observed, Mapping):
        findings.append("observed_identity must be an object")
    if not isinstance(claims, Mapping):
        findings.append("claims must be an object")
    if findings:
        return tuple(sorted(set(findings)))

    assert isinstance(coverage, Mapping)
    assert isinstance(requested, Mapping)
    assert isinstance(observed, Mapping)
    assert isinstance(claims, Mapping)

    state = coverage.get("state")
    artifact_digest = observed.get("artifact_digest")
    artifact_exact = claims.get("artifact_exact")
    if state == "exact":
        if not isinstance(artifact_digest, str) or not _DIGEST_RE.fullmatch(artifact_digest):
            findings.append("exact coverage requires a valid observed artifact digest")
        if artifact_exact != "true":
            findings.append("exact coverage requires claims.artifact_exact=true")
    elif state in {"partial", "unknown"}:
        if artifact_digest is not None:
            findings.append("non-exact coverage cannot publish an artifact digest")
        if artifact_exact == "true":
            findings.append("non-exact coverage cannot claim artifact_exact=true")

    if claims.get("source_compatibility_established") != "unknown":
        findings.append("artifact construction cannot establish source compatibility")
    if claims.get("runtime_compatibility_established") != "unknown":
        findings.append("artifact construction cannot establish runtime compatibility")

    kind = requested.get("kind")
    value = requested.get("value")
    if isinstance(kind, str) and isinstance(value, str):
        package_version = observed.get("package_version")
        source_revision = observed.get("source_revision")
        expected_match = _requested_match(
            requested_kind=kind,
            requested_value=value,
            artifact_digest=artifact_digest if isinstance(artifact_digest, str) else None,
            package_version=package_version if isinstance(package_version, str) else None,
            source_revision=source_revision if isinstance(source_revision, str) else None,
        )
        if claims.get("requested_identity_matched") != expected_match:
            findings.append("requested_identity_matched does not match requested and observed identity")

    return tuple(sorted(set(findings)))


def require_exact_artifact_digest(evidence: object) -> str:
    """Return the digest only when current artifact evidence is semantically exact."""
    findings = validate_artifact_evidence_semantics(evidence)
    if findings:
        raise ArtifactEvidenceError("; ".join(findings))
    if not isinstance(evidence, Mapping):
        raise ArtifactEvidenceError("artifact evidence must be an object")
    coverage = evidence.get("coverage")
    observed = evidence.get("observed_identity")
    if not isinstance(coverage, Mapping) or coverage.get("state") != "exact":
        raise ArtifactEvidenceError("artifact evidence is not exact")
    if not isinstance(observed, Mapping):
        raise ArtifactEvidenceError("observed_identity must be an object")
    digest = observed.get("artifact_digest")
    if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
        raise ArtifactEvidenceError("exact artifact evidence has no valid digest")
    return digest


def construction_profiles_comparable(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> bool:
    """V1 evidence is comparable only under the same valid profile digest."""
    left_digest = left.get("profile_digest")
    right_digest = right.get("profile_digest")
    return (
        isinstance(left_digest, str) and _DIGEST_RE.fullmatch(left_digest) is not None and left_digest == right_digest
    )

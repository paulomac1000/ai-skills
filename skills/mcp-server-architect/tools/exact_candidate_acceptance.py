"""Reusable exact-candidate MCP acceptance evidence for release gates."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

_SHA = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_UNPINNED = ("latest", "*", ">", "<", "^", "~")


class ExactCandidateAcceptanceError(ValueError):
    """Raised when exact-candidate evidence cannot prove the reviewed artifact."""


@dataclass(frozen=True)
class ExactCandidateEvidence:
    source_sha: str
    artifact_digest: str | None
    artifact_source_sha: str
    sdk_revision: str
    initialize_ok: bool
    tools_list_ok: bool
    schema_snapshot_digest: str
    schema_compatible: bool
    representative_invocation_ok: bool
    runtime_source_sha: str


def _require_sha(value: str, field: str) -> None:
    if not _SHA.fullmatch(value):
        raise ExactCandidateAcceptanceError(f"{field} must be an exact lowercase 40-hex SHA")


def validate_exact_candidate(evidence: ExactCandidateEvidence) -> ExactCandidateEvidence:
    """Fail closed unless one exact artifact completed the full MCP acceptance chain."""
    _require_sha(evidence.source_sha, "source_sha")
    _require_sha(evidence.artifact_source_sha, "artifact_source_sha")
    _require_sha(evidence.runtime_source_sha, "runtime_source_sha")
    if evidence.artifact_digest is None or not _DIGEST.fullmatch(evidence.artifact_digest):
        raise ExactCandidateAcceptanceError("artifact_digest is required and must be sha256")
    if evidence.artifact_source_sha != evidence.source_sha:
        raise ExactCandidateAcceptanceError("artifact source SHA does not match reviewed source SHA")
    if evidence.runtime_source_sha != evidence.source_sha:
        raise ExactCandidateAcceptanceError("runtime source SHA does not match reviewed source SHA")
    revision = evidence.sdk_revision.strip()
    if not revision or any(marker in revision.lower() for marker in _UNPINNED):
        raise ExactCandidateAcceptanceError("sdk_revision must name one pinned SDK revision")
    if not _DIGEST.fullmatch(evidence.schema_snapshot_digest):
        raise ExactCandidateAcceptanceError("schema_snapshot_digest must be sha256")
    phases = {
        "initialize": evidence.initialize_ok,
        "tools_list": evidence.tools_list_ok,
        "schema_compatibility": evidence.schema_compatible,
        "representative_invocation": evidence.representative_invocation_ok,
    }
    failed = [name for name, passed in phases.items() if not passed]
    if failed:
        raise ExactCandidateAcceptanceError(f"candidate acceptance phase failed: {','.join(failed)}")
    return evidence


def machine_evidence(evidence: ExactCandidateEvidence) -> dict[str, Any]:
    """Return a bounded machine-readable receipt after validation."""
    validate_exact_candidate(evidence)
    receipt = asdict(evidence)
    receipt["schema_version"] = 1
    receipt["verdict"] = "pass"
    receipt["identity_chain"] = [
        evidence.source_sha,
        evidence.artifact_digest,
        evidence.runtime_source_sha,
    ]
    return receipt

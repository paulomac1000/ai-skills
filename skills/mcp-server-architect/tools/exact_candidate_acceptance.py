"""Reusable exact-candidate MCP acceptance evidence for release gates.

Evidence is only accepted when it carries client provenance derived by
the canonical probe from a real session through the pinned official MCP
client. Caller-asserted session facts fail closed.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

_SHA = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_UNPINNED = ("latest", "*", ">", "<", "^", "~")
_PINNED_OFFICIAL_CLIENT = ("mcp", "2.0.0")
_MAX_INITIALIZE_PAYLOAD_CHARS = 4096
_REQUIRED_INITIALIZE_KEYS = ("protocolVersion", "serverInfo")


class ExactCandidateAcceptanceError(ValueError):
    """Raised when exact-candidate evidence cannot prove the reviewed artifact."""


@dataclass(frozen=True)
class ClientProvenance:
    """Receipt binding evidence to a real session through the official client."""

    package: str
    version: str
    protocol_revision: str
    transport: str
    initialize_payload: Mapping[str, Any]
    session_receipt: str

    def as_mapping(self) -> dict[str, Any]:
        return {
            "package": self.package,
            "version": self.version,
            "protocol_revision": self.protocol_revision,
            "transport": self.transport,
            "initialize_payload": dict(self.initialize_payload),
            "session_receipt": self.session_receipt,
        }


def canonical_receipt(initialize_payload: Mapping[str, Any], artifact_digest: str, client_version: str) -> str:
    """Deterministically derive the session receipt from real session facts."""
    canonical = json.dumps(
        {
            "artifact_digest": artifact_digest,
            "client_version": client_version,
            "initialize": initialize_payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_client_provenance(
    provenance: ClientProvenance | Mapping[str, Any] | None, artifact_digest: str
) -> ClientProvenance:
    """Fail closed unless provenance binds a real, well-formed client session."""
    if provenance is None:
        raise ExactCandidateAcceptanceError(
            "exact-candidate evidence requires client provenance from the canonical "
            "probe; caller-asserted session facts are rejected"
        )
    if isinstance(provenance, ClientProvenance):
        record = provenance.as_mapping()
    elif isinstance(provenance, Mapping):
        record = dict(provenance)
    else:
        raise ExactCandidateAcceptanceError("client provenance has an unsupported type")
    package, pinned_version = _PINNED_OFFICIAL_CLIENT
    if record.get("package") != package:
        raise ExactCandidateAcceptanceError("client provenance names a different client package")
    if record.get("version") != pinned_version:
        raise ExactCandidateAcceptanceError(
            f"client provenance version {record.get('version')!r} is not the pinned "
            f"official client {package}=={pinned_version}"
        )
    payload = record.get("initialize_payload")
    if not isinstance(payload, Mapping) or not payload:
        raise ExactCandidateAcceptanceError("client provenance initialize payload is missing")
    if len(json.dumps(payload, sort_keys=True)) > _MAX_INITIALIZE_PAYLOAD_CHARS:
        raise ExactCandidateAcceptanceError("initialize payload exceeds the bounded size")
    missing = [key for key in _REQUIRED_INITIALIZE_KEYS if key not in payload]
    if missing:
        raise ExactCandidateAcceptanceError(
            f"initialize payload is not a well-formed MCP initialize result; missing: {','.join(missing)}"
        )
    transport = record.get("transport")
    if not isinstance(transport, str) or not transport:
        raise ExactCandidateAcceptanceError("client provenance transport is missing")
    protocol_revision = record.get("protocol_revision")
    if not isinstance(protocol_revision, str) or not protocol_revision:
        raise ExactCandidateAcceptanceError("client provenance protocol revision is missing")
    receipt = record.get("session_receipt")
    expected = canonical_receipt(payload, artifact_digest, str(record["version"]))
    if not isinstance(receipt, str) or receipt != expected:
        raise ExactCandidateAcceptanceError(
            "client provenance session receipt does not match the recorded initialize "
            "payload; the evidence was not produced by a real client session"
        )
    return ClientProvenance(
        package=str(record["package"]),
        version=str(record["version"]),
        protocol_revision=protocol_revision,
        transport=transport,
        initialize_payload=payload,
        session_receipt=receipt,
    )


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
    client_provenance: ClientProvenance | None = field(default=None)


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
    validate_client_provenance(evidence.client_provenance, evidence.artifact_digest)
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
    provenance = receipt.get("client_provenance")
    if isinstance(provenance, ClientProvenance):
        receipt["client_provenance"] = provenance.as_mapping()
    receipt["schema_version"] = 1
    receipt["verdict"] = "pass"
    receipt["identity_chain"] = [
        evidence.source_sha,
        evidence.artifact_digest,
        evidence.runtime_source_sha,
    ]
    return receipt

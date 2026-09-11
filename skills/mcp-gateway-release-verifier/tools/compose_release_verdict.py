"""Compose existing MCP release contracts into one bounded fail-closed receipt."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass

MAX_PHASES = 16
MAX_SUMMARY_CHARS = 240
MAX_EVIDENCE_REF_CHARS = 512
MAX_RECEIPT_BYTES = 8192
REQUIRED_PHASES = (
    "preflight",
    "bootstrap",
    "exact_artifact_launch",
    "schema",
    "lifecycle",
    "degraded_health",
    "identity",
    "execution_integrity",
    "cleanup",
)
COMPOSED_CONTRACTS = {
    "preflight": "issue-49-exact-artifact-identity",
    "bootstrap": "ci-cd-architect/check_verification_bootstrap",
    "exact_artifact_launch": "issue-49-exact-artifact-identity",
    "schema": "mcp-server-architect/exact_candidate_acceptance",
    "lifecycle": "mcp-server-architect/transport_dogfood",
    "degraded_health": "mcp-server-architect/transport_dogfood",
    "identity": "issue-49-exact-artifact-identity",
    "execution_integrity": "ci-cd-architect/check_execution_integrity",
    "cleanup": "ci-cd-architect/verify_state_isolation",
}
_ALLOWED_STATUS = frozenset({"pass", "fail", "not_run"})


def _validate_probe_receipt(receipt: Mapping[str, object], artifact_digest: str) -> None:
    """Validate a canonical probe client receipt without importing probe runtime."""
    if receipt.get("package") != "mcp" or receipt.get("version") != "2.0.0":
        raise ReleaseCompositionError("probe client receipt must name the pinned official client mcp==2.0.0")
    payload = receipt.get("initialize_payload")
    if not isinstance(payload, Mapping) or "protocolVersion" not in payload:
        raise ReleaseCompositionError("probe client receipt is missing a well-formed initialize payload")
    session_receipt = receipt.get("session_receipt")
    if not isinstance(session_receipt, str) or len(session_receipt) != 64:
        raise ReleaseCompositionError("probe client receipt session_receipt must be sha256")
    expected = json.dumps(
        {
            "artifact_digest": artifact_digest,
            "client_version": receipt.get("version"),
            "initialize": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    import hashlib

    if hashlib.sha256(expected.encode("utf-8")).hexdigest() != session_receipt:
        raise ReleaseCompositionError("probe client receipt does not match the recorded initialize payload")


class ReleaseCompositionError(ValueError):
    """Raised when phase evidence is unbounded or claims the wrong owner contract."""


@dataclass(frozen=True)
class PhaseResult:
    name: str
    status: str
    contract_ref: str
    evidence_ref: str
    summary: str = ""


def _validate_phase(phase: PhaseResult) -> None:
    if phase.status not in _ALLOWED_STATUS:
        raise ReleaseCompositionError(f"invalid phase status: {phase.status}")
    if len(phase.summary) > MAX_SUMMARY_CHARS:
        raise ReleaseCompositionError("phase summary exceeds bound")
    if not phase.evidence_ref or len(phase.evidence_ref) > MAX_EVIDENCE_REF_CHARS:
        raise ReleaseCompositionError("phase evidence_ref exceeds bound")
    expected = COMPOSED_CONTRACTS.get(phase.name)
    if expected is not None and phase.contract_ref != expected:
        raise ReleaseCompositionError(f"phase {phase.name} must consume {expected}")


def compose_release_receipt(
    *,
    source_revision: str,
    artifact_digest: str,
    phases: tuple[PhaseResult, ...],
    probe_client_receipt: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Compose phase results; never reinterpret their owning contract semantics.

    The exact-artifact and schema phases are only accepted as ``pass`` when a
    valid canonical probe client receipt is provided; evidence derived without
    the pinned official MCP client cannot satisfy the composition.
    """
    if not source_revision or len(source_revision) > 128:
        raise ReleaseCompositionError("source_revision is missing or unbounded")
    if not artifact_digest or len(artifact_digest) > 128:
        raise ReleaseCompositionError("artifact_digest is missing or unbounded")
    if len(phases) > MAX_PHASES:
        raise ReleaseCompositionError("phase count exceeds bound")
    by_name: dict[str, PhaseResult] = {}
    for phase in phases:
        _validate_phase(phase)
        if phase.name in by_name:
            raise ReleaseCompositionError(f"duplicate phase: {phase.name}")
        by_name[phase.name] = phase
    probe_required = any(
        by_name.get(name, PhaseResult(name, "not_run", "", "", "")).status == "pass"
        for name in ("exact_artifact_launch", "schema")
    )
    if probe_required:
        if probe_client_receipt is None:
            raise ReleaseCompositionError(
                "passing exact-artifact/schema phases require a canonical probe "
                "client receipt; evidence without the pinned official client is "
                "rejected"
            )
        _validate_probe_receipt(probe_client_receipt, artifact_digest)

    ordered: list[PhaseResult] = []
    for name in REQUIRED_PHASES:
        if name in by_name:
            phase = by_name.pop(name)
        else:
            phase = PhaseResult(
                name=name,
                status="not_run",
                contract_ref=COMPOSED_CONTRACTS[name],
                evidence_ref="missing",
                summary="required phase missing",
            )
        ordered.append(phase)
    ordered.extend(by_name[name] for name in sorted(by_name))
    verdict = "pass" if all(phase.status == "pass" for phase in ordered) else "fail"
    receipt: dict[str, object] = {
        "schema_version": 1,
        "candidate": {
            "source_revision": source_revision,
            "artifact_digest": artifact_digest,
        },
        "phases": [asdict(phase) for phase in ordered],
        "verdict": verdict,
    }
    if len(json.dumps(receipt, sort_keys=True).encode("utf-8")) > MAX_RECEIPT_BYTES:
        raise ReleaseCompositionError("release receipt exceeds byte bound")
    return receipt

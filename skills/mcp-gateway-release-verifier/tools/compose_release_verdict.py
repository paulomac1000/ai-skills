"""Compose existing MCP release contracts into one bounded fail-closed receipt."""

from __future__ import annotations

import json
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
) -> dict[str, object]:
    """Compose phase results; never reinterpret their owning contract semantics."""
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

    ordered: list[PhaseResult] = []
    for name in REQUIRED_PHASES:
        phase = by_name.pop(name, None)
        if phase is None:
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

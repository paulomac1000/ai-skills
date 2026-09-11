"""Compose a local disposable MCP candidate acceptance lane and clean only owned state."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

OWNER_MARKER = ".mcp-acceptance-owner"
_REQUIRED_PASS_FIELDS = (
    "build_verdict",
    "migration_preflight_verdict",
    "launch_verdict",
    "exact_candidate_verdict",
    "transport_dogfood_verdict",
    "release_verifier_verdict",
    "durable_polling_verdict",
    "migration_invariants_verdict",
)


@dataclass(frozen=True)
class LocalCandidateEvidence:
    clean_candidate: bool
    disposable_state: bool
    config_isolated: bool
    ports: tuple[int, ...]
    occupied_ports: frozenset[int]
    build_verdict: str
    migration_preflight_verdict: str
    launch_verdict: str
    exact_candidate_verdict: str
    transport_dogfood_verdict: str
    release_verifier_verdict: str
    durable_polling_verdict: str
    migration_invariants_verdict: str


def compose_local_lane_receipt(evidence: LocalCandidateEvidence) -> dict[str, object]:
    """Return a deterministic fail-closed local candidate lane receipt."""
    failures: list[str] = []
    if not evidence.clean_candidate:
        failures.append("candidate_not_clean")
    if not evidence.disposable_state or not evidence.config_isolated:
        failures.append("state_or_config_not_disposable")
    if not evidence.ports or any(port <= 0 or port > 65535 for port in evidence.ports):
        failures.append("invalid_ports")
    if len(set(evidence.ports)) != len(evidence.ports):
        failures.append("duplicate_ports")
    conflicts = sorted(set(evidence.ports).intersection(evidence.occupied_ports))
    if conflicts:
        failures.append("port_conflict:" + ",".join(str(port) for port in conflicts))
    for field in _REQUIRED_PASS_FIELDS:
        if getattr(evidence, field) != "pass":
            failures.append(field)
    return {
        "schema_version": 1,
        "verdict": "pass" if not failures else "fail",
        "ports": list(evidence.ports),
        "failures": failures,
    }


def cleanup_owned_resources(
    *,
    sandbox_root: Path,
    owner_token: str,
    resources: tuple[Path, ...],
) -> tuple[Path, ...]:
    """Remove only marked resources that resolve strictly below sandbox_root."""
    if not owner_token:
        raise ValueError("owner_token is required")
    root = sandbox_root.resolve(strict=True)
    removed: list[Path] = []
    for resource in resources:
        resolved = resource.resolve(strict=False)
        if resolved == root or not resolved.is_relative_to(root) or not resolved.is_dir():
            continue
        marker = resolved / OWNER_MARKER
        try:
            marker_value = marker.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if marker_value != owner_token:
            continue
        shutil.rmtree(resolved)
        removed.append(resolved)
    return tuple(removed)

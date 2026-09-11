"""Validate real-transport MCP candidate dogfood evidence without duplicating generic gates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath

_REQUIRED_ENV = ("HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME")
_REQUIRED_TRANSPORTS = frozenset({"stdio", "streamable-http"})
_TERMINAL_SUCCESS = frozenset({"succeeded", "completed"})


class TransportDogfoodError(ValueError):
    """Raised when the real-transport candidate cannot be accepted."""


@dataclass(frozen=True)
class TransportDogfoodEvidence:
    exact_candidate_verdict: str
    execution_integrity_verdict: str
    sandbox_root: str
    environment: Mapping[str, str]
    transports: tuple[str, ...]
    official_client: bool
    initialize_ok: bool
    tools_list_ok: bool
    public_read_ok: bool
    public_write_ok: bool
    created_id: str
    status_id: str
    read_id: str
    async_statuses: tuple[str, ...]
    degradation_injected: bool
    degraded_health_observed: bool
    runtime_identity_present: bool
    persistence_roots: tuple[str, ...]
    diagnostics_bytes: int
    max_diagnostics_bytes: int
    artifact_digest: str
    client_provenance: Mapping[str, object] | None = None


def _load_probe_module():
    import importlib.util
    import sys
    from pathlib import Path

    probe_path = Path(__file__).resolve().parent / "mcp_exact_candidate_probe.py"
    spec = importlib.util.spec_from_file_location("transport_dogfood_probe", probe_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _under(root: str, candidate: str) -> bool:
    base = PurePosixPath(root)
    path = PurePosixPath(candidate)
    return path != base and base in path.parents


def validate_transport_dogfood(evidence: TransportDogfoodEvidence) -> TransportDogfoodEvidence:
    """Fail closed unless the exact candidate survives realistic transport dogfood."""
    if evidence.exact_candidate_verdict != "pass":
        raise TransportDogfoodError("exact-candidate acceptance did not pass")
    if not evidence.client_provenance:
        raise TransportDogfoodError(
            "dogfood evidence requires client provenance from the canonical probe; "
            "caller-asserted official_client flags are rejected"
        )
    _probe = _load_probe_module()
    try:
        _probe.validate_client_provenance(evidence.client_provenance, evidence.artifact_digest)
    except _probe.ExactCandidateAcceptanceError as exc:
        raise TransportDogfoodError(f"client provenance rejected: {exc}") from exc
    if evidence.execution_integrity_verdict != "pass":
        raise TransportDogfoodError("blocking background/runtime exception evidence")
    if not evidence.sandbox_root.startswith("/"):
        raise TransportDogfoodError("sandbox_root must be an absolute disposable root")
    for key in _REQUIRED_ENV:
        value = evidence.environment.get(key, "")
        if not value or not _under(evidence.sandbox_root, value):
            raise TransportDogfoodError(f"{key} is not isolated under sandbox_root")
    if not _REQUIRED_TRANSPORTS.issubset(evidence.transports):
        raise TransportDogfoodError("stdio and streamable-http must both be dogfooded")
    checks = {
        "official_client": evidence.official_client,
        "initialize": evidence.initialize_ok,
        "tools_list": evidence.tools_list_ok,
        "public_read": evidence.public_read_ok,
        "public_write": evidence.public_write_ok,
        "degradation_injected": evidence.degradation_injected,
        "degraded_health": evidence.degraded_health_observed,
        "runtime_identity": evidence.runtime_identity_present,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise TransportDogfoodError(f"dogfood check failed: {','.join(failed)}")
    if not evidence.created_id or not (evidence.created_id == evidence.status_id == evidence.read_id):
        raise TransportDogfoodError("public lifecycle ID chain is inconsistent")
    if not evidence.async_statuses or evidence.async_statuses[-1] not in _TERMINAL_SUCCESS:
        raise TransportDogfoodError("async status polling did not reach successful terminal state")
    if not evidence.persistence_roots or any(
        not _under(evidence.sandbox_root, path) for path in evidence.persistence_roots
    ):
        raise TransportDogfoodError("persistence roots escaped the disposable sandbox")
    if evidence.max_diagnostics_bytes <= 0 or not (0 <= evidence.diagnostics_bytes <= evidence.max_diagnostics_bytes):
        raise TransportDogfoodError("diagnostics exceeded the declared byte bound")
    return evidence

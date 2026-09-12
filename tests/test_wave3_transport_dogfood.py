"""Wave 3 regressions for real MCP transport dogfooding."""

from __future__ import annotations

import fnmatch
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
ARCHITECT = ROOT / "skills/mcp-server-architect"
TOOL = ARCHITECT / "tools/transport_dogfood.py"
MANIFEST = ARCHITECT / "manifest.yaml"
QUALITY_TARGETS = ROOT / "scripts/quality_targets.py"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _probe_receipt(artifact_digest: str) -> dict[str, object]:
    import hashlib
    import json

    payload = {
        "protocolVersion": "2025-06-18",
        "serverInfo": {"name": "candidate", "version": "1.0.0"},
    }
    canonical = json.dumps(
        {
            "artifact_digest": artifact_digest,
            "client_version": "2.0.0",
            "initialize": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return {
        "package": "mcp",
        "version": "2.0.0",
        "protocol_revision": "2025-06-18",
        "transport": "stdio",
        "initialize_payload": payload,
        "session_receipt": hashlib.sha256(canonical.encode()).hexdigest(),
        "artifact_digest": artifact_digest,
    }


def _evidence(module: ModuleType, **changes: object) -> object:
    root = "/tmp/mcp-dogfood"
    digest = "sha256:" + "b" * 64
    values: dict[str, object] = {
        "exact_candidate_verdict": "pass",
        "execution_integrity_verdict": "pass",
        "sandbox_root": root,
        "environment": {
            "HOME": f"{root}/home",
            "XDG_CONFIG_HOME": f"{root}/config",
            "XDG_STATE_HOME": f"{root}/state",
            "XDG_CACHE_HOME": f"{root}/cache",
        },
        "transports": ("stdio", "streamable-http"),
        "official_client": True,
        "initialize_ok": True,
        "tools_list_ok": True,
        "public_read_ok": True,
        "public_write_ok": True,
        "created_id": "job-1",
        "status_id": "job-1",
        "read_id": "job-1",
        "async_statuses": ("queued", "running", "succeeded"),
        "degradation_injected": True,
        "degraded_health_observed": True,
        "runtime_identity_present": True,
        "persistence_roots": (f"{root}/state/jobs",),
        "diagnostics_bytes": 2048,
        "max_diagnostics_bytes": 4096,
        "artifact_digest": digest,
        "client_provenance": _probe_receipt(digest),
    }
    values.update(changes)
    return module.TransportDogfoodEvidence(**values)


def _covered(targets: tuple[str, ...], path: str) -> bool:
    return any(
        path == target or path.startswith(f"{target.rstrip('/')}/") or ("*" in target and fnmatch.fnmatch(path, target))
        for target in targets
    )


def test_real_transport_reference_evidence_passes() -> None:
    module = _load("wave3_transport_happy", TOOL)
    assert module.validate_transport_dogfood(_evidence(module))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("exact_candidate_verdict", "fail", "exact-candidate"),
        ("official_client", False, "official_client"),
        ("initialize_ok", False, "initialize"),
        ("tools_list_ok", False, "tools_list"),
        ("public_read_ok", False, "public_read"),
        ("public_write_ok", False, "public_write"),
        ("degradation_injected", False, "degradation_injected"),
        ("degraded_health_observed", False, "degraded_health"),
        ("runtime_identity_present", False, "runtime_identity"),
    ],
)
def test_required_dogfood_cases_fail_closed(field: str, value: object, message: str) -> None:
    module = _load(f"wave3_transport_{field}", TOOL)
    with pytest.raises(module.TransportDogfoodError, match=message):
        module.validate_transport_dogfood(_evidence(module, **{field: value}))


def test_home_xdg_and_persistence_must_stay_in_disposable_root() -> None:
    module = _load("wave3_transport_isolation", TOOL)
    bad_env = dict(_evidence(module).environment)
    bad_env["HOME"] = "/home/operator"
    with pytest.raises(module.TransportDogfoodError, match="HOME"):
        module.validate_transport_dogfood(_evidence(module, environment=bad_env))
    with pytest.raises(module.TransportDogfoodError, match="persistence roots"):
        module.validate_transport_dogfood(_evidence(module, persistence_roots=("/var/lib/mcp",)))


def test_both_real_transports_and_one_lifecycle_id_are_required() -> None:
    module = _load("wave3_transport_protocol", TOOL)
    with pytest.raises(module.TransportDogfoodError, match="both be dogfooded"):
        module.validate_transport_dogfood(_evidence(module, transports=("stdio",)))
    with pytest.raises(module.TransportDogfoodError, match="ID chain"):
        module.validate_transport_dogfood(_evidence(module, status_id="job-2"))


def test_async_polling_and_diagnostics_are_bounded() -> None:
    module = _load("wave3_transport_bounds", TOOL)
    with pytest.raises(module.TransportDogfoodError, match="terminal"):
        module.validate_transport_dogfood(_evidence(module, async_statuses=("queued", "running")))
    with pytest.raises(module.TransportDogfoodError, match="byte bound"):
        module.validate_transport_dogfood(_evidence(module, diagnostics_bytes=4097))


def test_blocking_background_exception_from_generic_gate_fails_dogfood() -> None:
    module = _load("wave3_transport_execution_integrity", TOOL)
    with pytest.raises(module.TransportDogfoodError, match="background/runtime exception"):
        module.validate_transport_dogfood(_evidence(module, execution_integrity_verdict="fail"))


def test_transport_tool_is_manifested_and_in_all_quality_inventories() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert "tools/transport_dogfood.py" in manifest["required"]
    inventories = _load("wave3_quality_targets_transport", QUALITY_TARGETS)
    path = "skills/mcp-server-architect/tools/transport_dogfood.py"
    for targets in (
        inventories.QUALITY_PATHS,
        inventories.TYPE_PATHS,
        inventories.BANDIT_PATHS,
        inventories.POLICY_COVERAGE_PATHS,
    ):
        assert _covered(targets, path)


def test_dogfood_without_canonical_probe_client_provenance_fails_closed() -> None:
    module = _load("wave3_dogfood_masquerade", TOOL)
    try:
        module.validate_transport_dogfood(_evidence(module, client_provenance=None))
    except module.TransportDogfoodError as exc:
        assert "client provenance" in str(exc)
    else:
        raise AssertionError("dogfood passed without canonical probe client provenance")


def test_dogfood_rejects_inconsistent_probe_receipt() -> None:
    module = _load("wave3_dogfood_bad_receipt", TOOL)
    receipt = dict(_probe_receipt("sha256:" + "b" * 64))
    receipt["session_receipt"] = "f" * 64
    try:
        module.validate_transport_dogfood(
            _evidence(module, artifact_digest="sha256:" + "b" * 64, client_provenance=receipt)
        )
    except module.TransportDogfoodError as exc:
        assert "rejected" in str(exc)
    else:
        raise AssertionError("dogfood accepted an inconsistent probe receipt")


def test_dogfood_rejects_unpinned_client_version() -> None:
    module = _load("wave3_dogfood_bad_client", TOOL)
    receipt = _probe_receipt("sha256:" + "b" * 64)
    receipt["version"] = "9.9.9"
    try:
        module.validate_transport_dogfood(_evidence(module, client_provenance=receipt))
    except module.TransportDogfoodError as exc:
        assert "pinned official client" in str(exc)
    else:
        raise AssertionError("dogfood accepted an unpinned client version")

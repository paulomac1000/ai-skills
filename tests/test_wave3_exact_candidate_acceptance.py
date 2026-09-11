"""Wave 3 regressions for exact-candidate MCP release acceptance."""

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
TOOL = ARCHITECT / "tools/exact_candidate_acceptance.py"
MANIFEST = ARCHITECT / "manifest.yaml"
QUALITY_TARGETS = ROOT / "scripts/quality_targets.py"
SHA = "a" * 40
DIGEST = "sha256:" + "b" * 64
SCHEMA_DIGEST = "sha256:" + "c" * 64


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _provenance(module: ModuleType, artifact_digest: str) -> object:
    payload = {
        "protocolVersion": "2025-06-18",
        "serverInfo": {"name": "candidate", "version": "1.0.0"},
    }
    receipt = module.canonical_receipt(payload, artifact_digest, "2.0.0")
    return module.ClientProvenance(
        package="mcp",
        version="2.0.0",
        protocol_revision="2025-06-18",
        transport="stdio",
        initialize_payload=payload,
        session_receipt=receipt,
    )


def _evidence(module: ModuleType, **changes: object) -> object:
    values: dict[str, object] = {
        "source_sha": SHA,
        "artifact_digest": DIGEST,
        "artifact_source_sha": SHA,
        "sdk_revision": "mcp@2.0.0",
        "initialize_ok": True,
        "tools_list_ok": True,
        "schema_snapshot_digest": SCHEMA_DIGEST,
        "schema_compatible": True,
        "representative_invocation_ok": True,
        "runtime_source_sha": SHA,
        "client_provenance": _provenance(module, DIGEST),
    }
    values.update(changes)
    return module.ExactCandidateEvidence(**values)


def _covered(targets: tuple[str, ...], path: str) -> bool:
    return any(
        path == target or path.startswith(f"{target.rstrip('/')}/") or ("*" in target and fnmatch.fnmatch(path, target))
        for target in targets
    )


def test_exact_candidate_emits_machine_bound_identity_chain() -> None:
    module = _load("wave3_exact_candidate_happy", TOOL)
    receipt = module.machine_evidence(_evidence(module))
    assert receipt["verdict"] == "pass"
    assert receipt["artifact_digest"] == DIGEST
    assert receipt["source_sha"] == SHA
    assert receipt["sdk_revision"] == "mcp@2.0.0"
    assert receipt["identity_chain"] == [SHA, DIGEST, SHA]


def test_missing_artifact_digest_fails_closed() -> None:
    module = _load("wave3_exact_candidate_missing_digest", TOOL)
    with pytest.raises(module.ExactCandidateAcceptanceError, match="artifact_digest is required"):
        module.validate_exact_candidate(_evidence(module, artifact_digest=None))


def test_artifact_source_mismatch_fails_closed() -> None:
    module = _load("wave3_exact_candidate_source_mismatch", TOOL)
    with pytest.raises(module.ExactCandidateAcceptanceError, match="artifact source SHA"):
        module.validate_exact_candidate(_evidence(module, artifact_source_sha="d" * 40))


def test_runtime_source_or_unpinned_sdk_cannot_pass() -> None:
    module = _load("wave3_exact_candidate_runtime", TOOL)
    with pytest.raises(module.ExactCandidateAcceptanceError, match="runtime source SHA"):
        module.validate_exact_candidate(_evidence(module, runtime_source_sha="e" * 40))
    with pytest.raises(module.ExactCandidateAcceptanceError, match="pinned SDK"):
        module.validate_exact_candidate(_evidence(module, sdk_revision="latest"))


def test_failed_protocol_phase_cannot_emit_pass_receipt() -> None:
    module = _load("wave3_exact_candidate_phase", TOOL)
    with pytest.raises(module.ExactCandidateAcceptanceError, match="schema_compatibility"):
        module.machine_evidence(_evidence(module, schema_compatible=False))


def test_exact_candidate_tool_is_manifested_and_in_all_quality_inventories() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert "tools/exact_candidate_acceptance.py" in manifest["required"]
    inventories = _load("wave3_quality_targets_exact_candidate", QUALITY_TARGETS)
    path = "skills/mcp-server-architect/tools/exact_candidate_acceptance.py"
    for targets in (
        inventories.QUALITY_PATHS,
        inventories.TYPE_PATHS,
        inventories.BANDIT_PATHS,
        inventories.POLICY_COVERAGE_PATHS,
    ):
        assert _covered(targets, path)

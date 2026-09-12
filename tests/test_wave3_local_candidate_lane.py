"""Wave 3 regressions for local MCP candidate acceptance composition."""

from __future__ import annotations

import fnmatch
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/mcp-gateway-release-verifier"
TOOL = SKILL / "tools/local_candidate_lane.py"
QUALITY_TARGETS = ROOT / "scripts/quality_targets.py"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _covered(targets: tuple[str, ...], path: str) -> bool:
    return any(
        path == target or path.startswith(f"{target.rstrip('/')}/") or ("*" in target and fnmatch.fnmatch(path, target))
        for target in targets
    )


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
    values: dict[str, object] = {
        "clean_candidate": True,
        "disposable_state": True,
        "config_isolated": True,
        "ports": (43101, 43102),
        "occupied_ports": frozenset(),
        "build_verdict": "pass",
        "migration_preflight_verdict": "pass",
        "launch_verdict": "pass",
        "exact_candidate_verdict": "pass",
        "transport_dogfood_verdict": "pass",
        "release_verifier_verdict": "pass",
        "durable_polling_verdict": "pass",
        "migration_invariants_verdict": "pass",
        "artifact_digest": "sha256:" + "d" * 64,
        "probe_client_receipt": _probe_receipt("sha256:" + "d" * 64),
    }
    values.update(changes)
    return module.LocalCandidateEvidence(**values)


def test_complete_local_candidate_lane_passes() -> None:
    module = _load("wave3_local_lane_happy", TOOL)
    receipt = module.compose_local_lane_receipt(_evidence(module))
    assert receipt == {
        "schema_version": 1,
        "verdict": "pass",
        "ports": [43101, 43102],
        "failures": [],
    }


def test_port_conflict_fails_closed_before_release_confidence() -> None:
    module = _load("wave3_local_lane_port", TOOL)
    receipt = module.compose_local_lane_receipt(_evidence(module, occupied_ports=frozenset({43102})))
    assert receipt["verdict"] == "fail"
    assert receipt["failures"] == ["port_conflict:43102"]


def test_any_composed_acceptance_phase_failure_is_non_green() -> None:
    module = _load("wave3_local_lane_phase", TOOL)
    receipt = module.compose_local_lane_receipt(
        _evidence(module, migration_preflight_verdict="fail", durable_polling_verdict="fail")
    )
    assert receipt["verdict"] == "fail"
    assert "migration_preflight_verdict" in receipt["failures"]
    assert "durable_polling_verdict" in receipt["failures"]


def test_cleanup_after_failure_removes_only_owned_resources(tmp_path: Path) -> None:
    module = _load("wave3_local_lane_cleanup", TOOL)
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    owned = sandbox / "owned"
    foreign = sandbox / "foreign"
    owned.mkdir()
    foreign.mkdir()
    (owned / module.OWNER_MARKER).write_text("run-1\n", encoding="utf-8")
    (foreign / module.OWNER_MARKER).write_text("other-run\n", encoding="utf-8")
    removed = module.cleanup_owned_resources(
        sandbox_root=sandbox,
        owner_token="run-1",
        resources=(owned, foreign, tmp_path),
    )
    assert removed == (owned.resolve(),)
    assert not owned.exists()
    assert foreign.exists()
    assert tmp_path.exists()


def test_local_lane_tool_is_manifested_and_in_all_quality_inventories() -> None:
    manifest = yaml.safe_load((SKILL / "manifest.yaml").read_text(encoding="utf-8"))
    assert "tools/local_candidate_lane.py" in manifest["required"]
    inventories = _load("wave3_quality_targets_local_lane", QUALITY_TARGETS)
    path = "skills/mcp-gateway-release-verifier/tools/local_candidate_lane.py"
    for targets in (
        inventories.QUALITY_PATHS,
        inventories.TYPE_PATHS,
        inventories.BANDIT_PATHS,
        inventories.POLICY_COVERAGE_PATHS,
    ):
        assert _covered(targets, path)

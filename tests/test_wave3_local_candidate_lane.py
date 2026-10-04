"""Wave 3 regressions for local MCP candidate acceptance composition."""

from __future__ import annotations

import fnmatch
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
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


def _change_acceptance_contract(*, migration: bool) -> dict[str, object]:
    import hashlib
    import json

    obligation_kind = "migration" if migration else "functional"
    obligation_id = "migration-scope" if migration else "non-migration-scope"
    contract: dict[str, object] = {
        "schema_version": 1,
        "change_id": "candidate-scope",
        "revision": "scope-v1",
        "obligations": [
            {
                "id": obligation_id,
                "kind": obligation_kind,
                "statement": "Declare whether persistent migration acceptance is required.",
                "source_ref": "policy:candidate-scope",
                "required": True,
            }
        ],
        "criteria": [
            {
                "id": "scope-proof",
                "obligation_refs": [obligation_id],
                "expected_outcome": "Candidate scope is admitted before local acceptance.",
                "rejection_condition": "Candidate scope is missing, stale, or invalid.",
                "required": True,
            }
        ],
    }
    encoded = json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    contract["digest"] = "sha256:" + hashlib.sha256(encoded).hexdigest()
    return contract


def _candidate_scope(
    module: ModuleType,
    *,
    migration: bool = False,
    candidate_revision: str = "candidate-1",
    contract_valid: bool = True,
    require_current_rerun: bool = False,
) -> object:
    import hashlib

    contract = _change_acceptance_contract(migration=migration)
    if not contract_valid:
        contract["digest"] = "sha256:" + "0" * 64
    source_digest = hashlib.sha256(b"candidate-scope-policy-v1").hexdigest()
    identity = module.CandidateScopeIdentity(
        candidate_revision=candidate_revision,
        acceptance_contract_digest=contract["digest"],
    )
    binding = module.TrustedCandidateScopeBinding(
        identity=identity,
        source=f"admission:sha256:{source_digest}",
    )
    return module.TrustedCandidateScopeEvidence(
        acceptance_contract=contract,
        binding=binding,
        require_current_rerun=require_current_rerun,
    )


def _compose(
    module: ModuleType,
    *,
    migration_scope: bool = False,
    scope: object | None = None,
    **changes: object,
) -> dict[str, object]:
    trusted_scope = _candidate_scope(module, migration=migration_scope) if scope is None else scope
    return module.compose_local_lane_receipt(
        _evidence(module, **changes),
        trusted_candidate_scope=trusted_scope,
    )


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
        "candidate_revision": "candidate-1",
    }
    values.update(changes)
    return module.LocalCandidateEvidence(**values)


def test_complete_local_candidate_lane_passes() -> None:
    module = _load("wave3_local_lane_happy", TOOL)
    receipt = _compose(module)
    assert receipt["schema_version"] == 1
    assert receipt["verdict"] == "pass"
    assert receipt["ports"] == [43101, 43102]
    assert receipt["failures"] == []
    scope = receipt["candidate_scope"]
    assert isinstance(scope, dict)
    assert scope["candidate_revision"] == "candidate-1"
    assert scope["migration_required"] is False
    assert scope["source"].startswith("admission:sha256:")


def test_port_conflict_fails_closed_before_release_confidence() -> None:
    module = _load("wave3_local_lane_port", TOOL)
    receipt = _compose(module, occupied_ports=frozenset({43102}))
    assert receipt["verdict"] == "fail"
    assert receipt["failures"] == ["port_conflict:43102"]


def test_any_composed_acceptance_phase_failure_is_non_green() -> None:
    module = _load("wave3_local_lane_phase", TOOL)
    receipt = _compose(module, migration_preflight_verdict="fail", durable_polling_verdict="fail")
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


def _migration_payload(*, candidate_revision: str = "candidate-1", valid: bool = True) -> dict[str, object]:
    entrypoint = "app.Migrations.run"
    entrypoint_revision = "sha256:migrator-v2"
    legacy_refs = ["schema:legacy-column"] if valid else []
    return {
        "schema_version": 1,
        "candidate_revision": candidate_revision,
        "current_schema": "v2",
        "production_entrypoint": entrypoint,
        "production_entrypoint_revision": entrypoint_revision,
        "supported_inputs": [
            {"input_ref": "fresh", "kind": "fresh", "schema_identity": None},
            {"input_ref": "v1", "kind": "legacy", "schema_identity": "v1"},
        ],
        "unsupported_inputs": [
            {"input_ref": "v0", "kind": "unsupported", "schema_identity": "v0"},
        ],
        "cases": [
            {
                "input_ref": "fresh",
                "fixture_identity": "fixture:fresh:sha256:abc",
                "observed_pre_schema": None,
                "legacy_characteristic_refs": [],
                "absent_current_characteristic_refs": [],
                "exercised_entrypoint": entrypoint,
                "exercised_entrypoint_revision": entrypoint_revision,
                "result": "pass",
                "observed_post_schema": "v2",
                "data_invariant_refs": [],
                "recovery_evidence_refs": [],
            },
            {
                "input_ref": "v1",
                "fixture_identity": "fixture:v1:sha256:def",
                "observed_pre_schema": "v1",
                "legacy_characteristic_refs": legacy_refs,
                "absent_current_characteristic_refs": ["schema:no-current-column"],
                "exercised_entrypoint": entrypoint,
                "exercised_entrypoint_revision": entrypoint_revision,
                "result": "pass",
                "observed_post_schema": "v2",
                "data_invariant_refs": ["data:representative-row"],
                "recovery_evidence_refs": [],
            },
            {
                "input_ref": "v0",
                "fixture_identity": "fixture:v0:sha256:ghi",
                "observed_pre_schema": "v0",
                "legacy_characteristic_refs": [],
                "absent_current_characteristic_refs": ["schema:no-current-column"],
                "exercised_entrypoint": entrypoint,
                "exercised_entrypoint_revision": entrypoint_revision,
                "result": "reject",
                "observed_post_schema": "v0",
                "data_invariant_refs": [],
                "recovery_evidence_refs": [],
            },
            {
                "input_ref": "v1",
                "fixture_identity": "fixture:v1:sha256:def",
                "observed_pre_schema": "v1",
                "legacy_characteristic_refs": legacy_refs,
                "absent_current_characteristic_refs": ["schema:no-current-column"],
                "exercised_entrypoint": entrypoint,
                "exercised_entrypoint_revision": entrypoint_revision,
                "result": "interrupted",
                "observed_post_schema": "v1",
                "data_invariant_refs": [],
                "recovery_evidence_refs": ["recovery:transaction-rolled-back"],
            },
        ],
    }


def test_non_migration_candidate_requires_trusted_scope_but_not_migration_payload() -> None:
    module = _load("wave3_local_lane_non_migration", TOOL)
    receipt = _compose(module)
    assert receipt["verdict"] == "pass"
    assert "migration_acceptance" not in receipt
    assert receipt["candidate_scope"]["migration_required"] is False


def test_migration_candidate_requires_green_exact_candidate_migration_payload() -> None:
    module = _load("wave3_local_lane_migration", TOOL)
    missing = _compose(
        module,
        migration_scope=True,
        candidate_revision="candidate-1",
    )
    assert missing["verdict"] == "fail"
    assert "migration_acceptance_payload_missing" in missing["failures"]

    valid = _compose(
        module,
        migration_scope=True,
        candidate_revision="candidate-1",
        migration_acceptance_payload=_migration_payload(),
    )
    assert valid["verdict"] == "pass"
    assert valid["migration_acceptance"] == {
        "verdict": "pass",
        "candidate_revision": "candidate-1",
        "current_schema": "v2",
        "production_entrypoint": "app.Migrations.run",
        "production_entrypoint_revision": "sha256:migrator-v2",
        "exercised_inputs": [
            {"input_ref": "fresh", "kind": "fresh", "schema_identity": None},
            {"input_ref": "v0", "kind": "unsupported", "schema_identity": "v0"},
            {"input_ref": "v1", "kind": "legacy", "schema_identity": "v1"},
        ],
    }


def test_migration_candidate_rejects_stale_or_non_green_migration_payload() -> None:
    module = _load("wave3_local_lane_migration_stale", TOOL)
    stale_scope = _candidate_scope(module, migration=True, candidate_revision="candidate-2")
    stale = module.compose_local_lane_receipt(
        _evidence(
            module,
            candidate_revision="candidate-2",
            migration_acceptance_payload=_migration_payload(candidate_revision="candidate-1"),
        ),
        trusted_candidate_scope=stale_scope,
    )
    assert stale["verdict"] == "fail"
    assert "migration_acceptance_receipt_candidate_mismatch" in stale["failures"]

    failed = _compose(
        module,
        migration_scope=True,
        candidate_revision="candidate-1",
        migration_acceptance_payload=_migration_payload(valid=False),
    )
    assert failed["verdict"] == "fail"
    assert any(item.startswith("migration_acceptance_failed:") for item in failed["failures"])


def test_caller_authored_receipt_shape_cannot_bypass_canonical_migration_evaluator() -> None:
    module = _load("wave3_local_lane_forged_receipt", TOOL)
    forged_receipt = {
        "schema_version": 1,
        "verdict": "pass",
        "candidate_revision": "candidate-1",
        "current_schema": "v2",
        "production_entrypoint": "app.Migrations.run",
        "production_entrypoint_revision": "sha256:migrator-v2",
        "exercised_inputs": [],
        "failures": [],
    }
    receipt = _compose(
        module,
        migration_scope=True,
        candidate_revision="candidate-1",
        migration_acceptance_payload=forged_receipt,
    )
    assert receipt["verdict"] == "fail"
    assert any(item.startswith("migration_acceptance_failed:") for item in receipt["failures"])


def test_candidate_scope_is_mandatory_exact_candidate_bound_and_cannot_be_suppressed_by_flag() -> None:
    module = _load("wave3_local_lane_candidate_scope", TOOL)
    missing = module.compose_local_lane_receipt(_evidence(module))
    assert missing["verdict"] == "fail"
    assert "candidate_scope_missing_or_untrusted" in missing["failures"]

    forged_raw_scope = module.compose_local_lane_receipt(
        _evidence(module),
        trusted_candidate_scope={
            "binding": "caller:forged",
            "acceptance_contract": _change_acceptance_contract(migration=False),
        },
    )
    assert forged_raw_scope["verdict"] == "fail"
    assert "candidate_scope_missing_or_untrusted" in forged_raw_scope["failures"]

    stale_scope = _candidate_scope(module, candidate_revision="candidate-2")
    stale = module.compose_local_lane_receipt(
        _evidence(module, candidate_revision="candidate-1"),
        trusted_candidate_scope=stale_scope,
    )
    assert stale["verdict"] == "fail"
    assert "candidate_scope_candidate_mismatch" in stale["failures"]
    assert "migration_acceptance_required" not in module.LocalCandidateEvidence.__dataclass_fields__


def test_invalid_admitted_scope_contract_fails_closed() -> None:
    module = _load("wave3_local_lane_invalid_scope", TOOL)
    invalid_scope = _candidate_scope(module, contract_valid=False)
    receipt = module.compose_local_lane_receipt(
        _evidence(module),
        trusted_candidate_scope=invalid_scope,
    )
    assert receipt["verdict"] == "fail"
    assert any(item.startswith("candidate_scope_contract_rejected:") for item in receipt["failures"])


def test_required_migration_scope_cannot_be_bypassed_by_omitting_payload() -> None:
    module = _load("wave3_local_lane_scope_migration_required", TOOL)
    receipt = _compose(module, migration_scope=True)
    assert receipt["verdict"] == "fail"
    assert receipt["candidate_scope"]["migration_required"] is True
    assert "migration_acceptance_payload_missing" in receipt["failures"]


def test_non_migration_scope_rejects_contradictory_migration_payload() -> None:
    module = _load("wave3_local_lane_scope_contradiction", TOOL)
    receipt = _compose(module, migration_acceptance_payload=_migration_payload())
    assert receipt["verdict"] == "fail"
    assert "migration_acceptance_payload_out_of_scope" in receipt["failures"]


def test_candidate_scope_requires_identity_bound_immutable_provenance() -> None:
    module = _load("wave3_local_lane_scope_provenance", TOOL)
    contract = _change_acceptance_contract(migration=False)
    identity = module.CandidateScopeIdentity(
        candidate_revision="candidate-1",
        acceptance_contract_digest=contract["digest"],
    )
    with pytest.raises(ValueError, match="immutable"):
        module.TrustedCandidateScopeBinding(identity=identity, source="caller:forged")

    wrong_identity = module.CandidateScopeIdentity(
        candidate_revision="candidate-1",
        acceptance_contract_digest="sha256:" + "f" * 64,
    )
    import hashlib

    source = "admission:sha256:" + hashlib.sha256(b"scope-policy").hexdigest()
    wrong_scope = module.TrustedCandidateScopeEvidence(
        acceptance_contract=contract,
        binding=module.TrustedCandidateScopeBinding(identity=wrong_identity, source=source),
    )
    receipt = module.compose_local_lane_receipt(
        _evidence(module),
        trusted_candidate_scope=wrong_scope,
    )
    assert receipt["verdict"] == "fail"
    assert "candidate_scope_contract_digest_mismatch" in receipt["failures"]


def test_raw_migration_payload_cannot_disable_recovery_or_set_rerun_policy() -> None:
    module = _load("wave3_local_lane_raw_policy", TOOL)
    payload = _migration_payload()
    payload["cases"] = [case for case in payload["cases"] if case["result"] != "interrupted"]
    payload["require_interrupted_recovery"] = False
    payload["require_current_rerun"] = False

    receipt = _compose(
        module,
        migration_scope=True,
        migration_acceptance_payload=payload,
    )
    assert receipt["verdict"] == "fail"
    assert any(
        "unknown fields: require_current_rerun, require_interrupted_recovery" in item
        for item in receipt["failures"]
    )
    assert any("interrupted mutating supported migration recovery case is required" in item for item in receipt["failures"])


def test_current_rerun_policy_comes_from_trusted_candidate_scope() -> None:
    module = _load("wave3_local_lane_current_rerun_policy", TOOL)
    payload = _migration_payload()
    payload["supported_inputs"].append(
        {"input_ref": "current", "kind": "current", "schema_identity": "v2"}
    )
    scope = _candidate_scope(module, migration=True, require_current_rerun=True)
    receipt = module.compose_local_lane_receipt(
        _evidence(module, migration_acceptance_payload=payload),
        trusted_candidate_scope=scope,
    )
    assert receipt["verdict"] == "fail"
    assert any("supported migration input not exercised: current" in item for item in receipt["failures"])

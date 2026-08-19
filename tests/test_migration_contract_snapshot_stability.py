"""Regressions for stable candidate-owned migration contract snapshots."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _upstream_contract() -> dict[str, object]:
    return {
        "schema_version": 1,
        "upstream": {"name": "legacy-api", "classification": "legacy"},
        "observations": [
            {
                "operation": "create-item",
                "method": "POST",
                "endpoint": "/items",
                "request_encoding": "form",
                "success_statuses": [201],
                "response_body": "empty",
                "credential_placement": "query",
                "confidence": "observed",
                "mutation_outcome": {
                    "completion": "confirmed-success",
                    "identity": "unavailable",
                    "representation": "unavailable",
                    "reconciliation_required": True,
                },
                "evidence": ["controlled disposable-backend probe"],
            }
        ],
    }


def _live_policy() -> dict[str, object]:
    return {
        "schema_version": 1,
        "default_execution": "excluded",
        "mutations": {
            "enabled_by_default": False,
            "independent_opt_ins": 2,
            "credential_access": "after-opt-in",
            "unique_namespace": True,
            "target_identity": {
                "verified_before_mutation": True,
                "exclusive_disposable_environment": True,
                "proof": "known disposable sandbox identity",
            },
            "cleanup": {
                "capture_created_ids": True,
                "reconcile_by_marker": True,
                "report_unreconciled": True,
                "preclean_after_target_verification": True,
                "strategies": ["captured-id", "unique-namespace"],
            },
        },
    }


def test_upstream_validation_stays_bound_to_one_stable_candidate_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator = _load("upstream_snapshot_stability", CONTRACTS / "validate_upstream_contract.py")
    contract = tmp_path / "upstream-contract.yaml"
    contract.write_text(yaml.safe_dump(_upstream_contract()), encoding="utf-8")
    real_read = validator.read_utf8_bounded
    snapshots = 0

    def read_then_replace(path: Path, root: Path, max_bytes: int) -> tuple[str, int]:
        nonlocal snapshots
        text, size = real_read(path, root, max_bytes)
        if path == contract:
            snapshots += 1
            contract.write_text("schema_version: 1\n", encoding="utf-8")
        return text, size

    monkeypatch.setattr(validator, "read_utf8_bounded", read_then_replace)

    assert validator.validate_contract(contract, require_observed=True) == []
    assert snapshots == 1
    assert yaml.safe_load(contract.read_text(encoding="utf-8")) == {"schema_version": 1}


def test_live_policy_validation_stays_bound_to_one_stable_candidate_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator = _load("live_policy_snapshot_stability", CONTRACTS / "validate_live_backend_test_policy.py")
    policy = tmp_path / "live-backend-test-policy.yaml"
    policy.write_text(yaml.safe_dump(_live_policy()), encoding="utf-8")
    real_read = validator.read_utf8_bounded
    snapshots = 0

    def read_then_replace(path: Path, root: Path, max_bytes: int) -> tuple[str, int]:
        nonlocal snapshots
        text, size = real_read(path, root, max_bytes)
        if path == policy:
            snapshots += 1
            policy.write_text("schema_version: 1\n", encoding="utf-8")
        return text, size

    monkeypatch.setattr(validator, "read_utf8_bounded", read_then_replace)

    assert validator.validate_policy(policy) == []
    assert snapshots == 1
    assert yaml.safe_load(policy.read_text(encoding="utf-8")) == {"schema_version": 1}

"""Wave 2 regressions for scoped health and public-ID referential integrity."""

from __future__ import annotations

import fnmatch
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONSUMER = ROOT / "skills/mcp-server-consumer"
TOOL = CONSUMER / "tools/consumer_contracts.py"
MANIFEST = CONSUMER / "manifest.yaml"
QUALITY_TARGETS = ROOT / "scripts/quality_targets.py"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _identity() -> dict[str, object]:
    return {
        "schema_version": 1,
        "runtime_id": "runtime-a",
        "instance_generation": "generation-7",
        "source_revision": "abc123",
    }


def _covered(targets: tuple[str, ...], path: str) -> bool:
    return any(
        path == target
        or path.startswith(f"{target.rstrip('/')}/")
        or ("*" in target and fnmatch.fnmatch(path, target))
        for target in targets
    )


def test_read_good_write_bad_stays_scoped_and_not_whole_service_green() -> None:
    contracts = _load("wave2_consumer_contracts_health", TOOL)
    health = contracts.ProviderHealth(
        provider="provider-a",
        runtime_identity=_identity(),
        fresh=True,
        process=contracts.HealthState.READY,
        transport=contracts.HealthState.READY,
        auth=contracts.HealthState.READY,
        read=contracts.HealthState.READY,
        write=contracts.HealthState.DEGRADED,
    )

    assert health.ready_for("read") is True
    assert health.ready_for("write") is False
    assert health.fully_ready is False


def test_create_status_read_preserves_typed_public_id_and_runtime_provenance() -> None:
    contracts = _load("wave2_consumer_contracts_ids", TOOL)
    created = contracts.PublicResourceRef("job-42", "analysis-job", "create", _identity())
    status = contracts.PublicResourceRef("job-42", "analysis-job", "status", _identity())
    read = contracts.PublicResourceRef("job-42", "analysis-job", "read", _identity())

    assert contracts.verify_public_id_handoff(created, [status, read]) is created


def test_public_id_namespace_or_value_mismatch_fails_closed() -> None:
    contracts = _load("wave2_consumer_contracts_mismatch", TOOL)
    created = contracts.PublicResourceRef("job-42", "analysis-job", "create", _identity())
    wrong_id = contracts.PublicResourceRef("job-43", "analysis-job", "status", _identity())
    wrong_kind = contracts.PublicResourceRef("job-42", "report", "read", _identity())

    with pytest.raises(ValueError, match="handoff mismatch"):
        contracts.verify_public_id_handoff(created, [wrong_id])
    with pytest.raises(ValueError, match="handoff mismatch"):
        contracts.verify_public_id_handoff(created, [wrong_kind])


def test_public_id_rejects_invented_legacy_runtime_identity_fields() -> None:
    contracts = _load("wave2_consumer_contracts_legacy", TOOL)
    legacy = {"schema_version": 1, "server_id": "runtime-a", "generation": "generation-7"}
    with pytest.raises(ValueError, match="canonical"):
        contracts.PublicResourceRef("job-42", "analysis-job", "create", legacy)


def test_consumer_contract_tool_is_required_and_in_all_quality_inventories() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert "tools/consumer_contracts.py" in manifest["required"]
    inventories = _load("wave2_quality_targets_contracts", QUALITY_TARGETS)
    path = "skills/mcp-server-consumer/tools/consumer_contracts.py"
    for targets in (
        inventories.QUALITY_PATHS,
        inventories.TYPE_PATHS,
        inventories.BANDIT_PATHS,
        inventories.POLICY_COVERAGE_PATHS,
    ):
        assert _covered(targets, path)

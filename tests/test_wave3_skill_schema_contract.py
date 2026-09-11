"""Wave 3 regressions for skill-to-live-schema contractRefs."""

from __future__ import annotations

import fnmatch
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/skill_schema_contract.py"
ARCH_TOOL = ROOT / "skills/mcp-server-architect/tools/skill_schema_contract.py"
CONSUMER_TOOL = ROOT / "skills/mcp-server-consumer/tools/contract_refs.py"
ARCH_MANIFEST = ROOT / "skills/mcp-server-architect/manifest.yaml"
CONSUMER_MANIFEST = ROOT / "skills/mcp-server-consumer/manifest.yaml"
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


def _ref(module: ModuleType) -> object:
    return module.ContractRef(
        capability="items.write",
        required_fields=("item_id", "value", "mode"),
        required_semantics={"mode.enum": ("safe", "force"), "id.stable": True},
        minimum_revision="2.1",
    )


def _snapshot(module: ModuleType, **changes: object) -> object:
    values: dict[str, object] = {
        "available": True,
        "capability": "items.write",
        "revision": "2.1",
        "skill_revision": "skill-sha-1",
        "fields": frozenset({"item_id", "value", "mode"}),
        "enums": {"mode": ("safe", "force")},
        "semantics": {"id.stable": True},
    }
    values.update(changes)
    return module.SchemaSnapshot(**values)


def test_exact_snapshot_is_compatible_and_additive_field_is_classified() -> None:
    module = _load("wave3_schema_contract_happy", CONTRACT)
    assert (
        module.classify_contract(_ref(module), skill_revision="skill-sha-1", snapshot=_snapshot(module))
        == module.Compatibility.COMPATIBLE
    )
    assert (
        module.classify_contract(
            _ref(module),
            skill_revision="skill-sha-1",
            snapshot=_snapshot(module, fields=frozenset({"item_id", "value", "mode", "note"})),
        )
        == module.Compatibility.COMPATIBLE_ADDITION
    )


def test_required_field_removal_is_incompatible() -> None:
    module = _load("wave3_schema_contract_removal", CONTRACT)
    result = module.classify_contract(
        _ref(module),
        skill_revision="skill-sha-1",
        snapshot=_snapshot(module, fields=frozenset({"item_id", "mode"})),
    )
    assert result == module.Compatibility.INCOMPATIBLE_REMOVAL


def test_enum_change_requires_review() -> None:
    module = _load("wave3_schema_contract_enum", CONTRACT)
    result = module.classify_contract(
        _ref(module),
        skill_revision="skill-sha-1",
        snapshot=_snapshot(module, enums={"mode": ("safe", "force", "auto")}),
    )
    assert result == module.Compatibility.ENUM_REVIEW_REQUIRED


def test_semantic_change_or_old_revision_requires_review() -> None:
    module = _load("wave3_schema_contract_semantics", CONTRACT)
    assert (
        module.classify_contract(
            _ref(module),
            skill_revision="skill-sha-1",
            snapshot=_snapshot(module, semantics={"id.stable": False}),
        )
        == module.Compatibility.SEMANTIC_REVIEW_REQUIRED
    )
    assert (
        module.classify_contract(_ref(module), skill_revision="skill-sha-1", snapshot=_snapshot(module, revision="2.0"))
        == module.Compatibility.SEMANTIC_REVIEW_REQUIRED
    )


def test_runtime_down_or_wrong_skill_revision_is_not_verified() -> None:
    module = _load("wave3_schema_contract_unavailable", CONTRACT)
    assert (
        module.classify_contract(_ref(module), skill_revision="skill-sha-1", snapshot=None)
        == module.Compatibility.NOT_VERIFIED
    )
    assert (
        module.classify_contract(
            _ref(module),
            skill_revision="skill-sha-1",
            snapshot=_snapshot(module, available=False),
        )
        == module.Compatibility.NOT_VERIFIED
    )
    assert (
        module.classify_contract(_ref(module), skill_revision="other", snapshot=_snapshot(module))
        == module.Compatibility.NOT_VERIFIED
    )


def test_architect_and_consumer_export_same_canonical_model() -> None:
    canonical = _load("contracts.skill_schema_contract", CONTRACT)
    architect = _load("wave3_arch_contract_ref", ARCH_TOOL)
    consumer = _load("wave3_consumer_contract_ref", CONSUMER_TOOL)
    assert architect.ContractRef is canonical.ContractRef
    assert consumer.ContractRef is canonical.ContractRef
    assert architect.classify_contract is canonical.classify_contract
    assert consumer.classify_contract is canonical.classify_contract


def test_contract_tools_are_manifested_and_in_all_quality_inventories() -> None:
    assert "tools/skill_schema_contract.py" in yaml.safe_load(ARCH_MANIFEST.read_text(encoding="utf-8"))["required"]
    assert "tools/contract_refs.py" in yaml.safe_load(CONSUMER_MANIFEST.read_text(encoding="utf-8"))["required"]
    inventories = _load("wave3_quality_targets_schema_contract", QUALITY_TARGETS)
    for path in (
        "contracts/skill_schema_contract.py",
        "skills/mcp-server-architect/tools/skill_schema_contract.py",
        "skills/mcp-server-consumer/tools/contract_refs.py",
    ):
        for targets in (
            inventories.QUALITY_PATHS,
            inventories.TYPE_PATHS,
            inventories.BANDIT_PATHS,
            inventories.POLICY_COVERAGE_PATHS,
        ):
            assert _covered(targets, path), (path, targets)

"""Wave 3 regressions for volatile runtime facts in AGENTS.md."""

from __future__ import annotations

import fnmatch
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/agents-md-architect"
TOOL = SKILL / "tools/runtime_fact_classification.py"
AUDIT = SKILL / "tools/audit_agents_md.py"
MANIFEST = SKILL / "manifest.yaml"
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
        path == target
        or path.startswith(f"{target.rstrip('/')}/")
        or ("*" in target and fnmatch.fnmatch(path, target))
        for target in targets
    )


def test_runtime_fact_classes_cover_stable_compat_owner_volatile_and_private() -> None:
    module = _load("wave3_runtime_fact_classes", TOOL)
    assert (
        module.classify_runtime_fact("Stable invariant: writes require explicit authority.")
        == module.RuntimeFactClass.STABLE_INVARIANT
    )
    assert (
        module.classify_runtime_fact("Compatibility contract: supported versions >= 2.0.")
        == module.RuntimeFactClass.COMPATIBILITY_CONTRACT
    )
    assert (
        module.classify_runtime_fact(
            "Logical capability owner: billing-mcp; resolve through RuntimeIdentity."
        )
        == module.RuntimeFactClass.LOGICAL_CAPABILITY_OWNER
    )
    assert (
        module.classify_runtime_fact("Current MCP host/version: gateway.internal v3.2.1.")
        == module.RuntimeFactClass.VOLATILE_OBSERVATION
    )
    assert (
        module.classify_runtime_fact("Use 10.0.0.5:8123 for MCP.")
        == module.RuntimeFactClass.PRIVATE_BINDING
    )


def test_current_mcp_host_or_version_as_timeless_truth_requires_owner() -> None:
    module = _load("wave3_runtime_fact_current", TOOL)
    message = module.volatile_binding_message("Current MCP host/version: gateway.internal v3.2.1.")
    assert message is not None
    assert "logical capability owner" in message
    assert "RuntimeIdentity" in message


def test_repository_release_version_language_is_not_a_runtime_binding() -> None:
    module = _load("wave3_runtime_fact_repository_version", TOOL)
    line = (
        "Preserve prerelease examples only when they test generic SemVer behavior and cannot be "
        "confused with the current repository version."
    )
    assert module.classify_runtime_fact(line) == module.RuntimeFactClass.STABLE_INVARIANT
    assert module.volatile_binding_message(line) is None


def test_unjustified_ip_or_port_requires_owner_but_scoped_observation_is_allowed() -> None:
    module = _load("wave3_runtime_fact_private", TOOL)
    assert module.volatile_binding_message("Connect to MCP at 10.0.0.5:8123.") is not None
    assert (
        module.volatile_binding_message(
            "Volatile observation: local development only endpoint is 10.0.0.5:8123."
        )
        is None
    )


def test_symbolic_capability_owner_and_compatibility_contract_are_stable() -> None:
    module = _load("wave3_runtime_fact_symbolic", TOOL)
    assert (
        module.volatile_binding_message(
            "Logical capability owner: inventory-mcp; resolve the live target through RuntimeIdentity before use."
        )
        is None
    )
    assert (
        module.volatile_binding_message(
            "Compatibility contract: supported MCP protocol versions are 2026-07-28 and 2025-11-25."
        )
        is None
    )


def test_main_agents_audit_emits_stable_runtime_binding_finding(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Repository instructions\n\nCurrent MCP host/version: gateway.internal v3.2.1.\n",
        encoding="utf-8",
    )
    audit = _load("wave3_agents_runtime_audit", AUDIT)
    _discovery, findings = audit.audit(tmp_path)
    matches = [item for item in findings if item.code == "VOLATILE_RUNTIME_BINDING_REQUIRES_OWNER"]
    assert len(matches) == 1
    assert matches[0].path == "AGENTS.md"
    assert matches[0].line == 3


def test_runtime_fact_tool_and_reference_are_manifested_and_quality_gated() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert "tools/runtime_fact_classification.py" in manifest["required"]
    assert "references/runtime-fact-classification.md" in manifest["required"]
    reference = (SKILL / "references/runtime-fact-classification.md").read_text(encoding="utf-8")
    assert "VOLATILE_RUNTIME_BINDING_REQUIRES_OWNER" in reference
    inventories = _load("wave3_quality_targets_runtime_facts", QUALITY_TARGETS)
    path = "skills/agents-md-architect/tools/runtime_fact_classification.py"
    for targets in (
        inventories.QUALITY_PATHS,
        inventories.TYPE_PATHS,
        inventories.BANDIT_PATHS,
        inventories.POLICY_COVERAGE_PATHS,
    ):
        assert _covered(targets, path)

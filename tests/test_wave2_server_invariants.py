"""Wave 2 executable regressions for the seven MCP server runtime/API invariants."""

from __future__ import annotations

import fnmatch
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
ARCHITECT = ROOT / "skills/mcp-server-architect"
TOOL = ARCHITECT / "tools/server_invariants.py"
MANIFEST = ARCHITECT / "manifest.yaml"
FIXTURES = ROOT / "tests/fixtures/mcp_server_invariants"
QUALITY_TARGETS = ROOT / "scripts/quality_targets.py"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _inventory_covers(targets: tuple[str, ...], relative_path: str) -> bool:
    return any(
        relative_path == target
        or relative_path.startswith(f"{target.rstrip('/')}/")
        or ("*" in target and fnmatch.fnmatch(relative_path, target))
        for target in targets
    )


@pytest.mark.parametrize(
    "invariant",
    [
        "runtime_identity",
        "diagnostic_parity",
        "actionable_preconditions",
        "managed_resource_ownership",
        "durable_async_progress",
        "bounded_results",
        "scoped_health",
    ],
)
def test_each_invariant_has_positive_and_negative_executable_fixture(invariant: str) -> None:
    checks = _load("wave2_server_invariants", TOOL)
    fixture = json.loads((FIXTURES / f"{invariant}.json").read_text(encoding="utf-8"))

    assert checks.evaluate_runtime_api_invariants(fixture["positive"])[invariant] is True
    assert checks.evaluate_runtime_api_invariants(fixture["negative"])[invariant] is False
    assert invariant not in checks.invariant_violations(fixture["positive"])
    assert invariant in checks.invariant_violations(fixture["negative"])


def test_server_invariant_tool_is_required_and_in_all_quality_inventories() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert "tools/server_invariants.py" in manifest["required"]

    inventories = _load("wave2_quality_targets", QUALITY_TARGETS)
    path = "skills/mcp-server-architect/tools/server_invariants.py"
    for targets in (
        inventories.QUALITY_PATHS,
        inventories.TYPE_PATHS,
        inventories.BANDIT_PATHS,
        inventories.POLICY_COVERAGE_PATHS,
    ):
        assert _inventory_covers(targets, path)

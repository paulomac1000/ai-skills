"""Wave 2 regressions for bounded agent-backed semantic façades."""

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
TOOL = ARCHITECT / "tools/semantic_facade.py"
STANDARD = ARCHITECT / "STANDARD.md"
MANIFEST = ARCHITECT / "manifest.yaml"
QUALITY_TARGETS = ROOT / "scripts/quality_targets.py"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _valid_design(facade: ModuleType, **changes: object) -> object:
    values: dict[str, object] = {
        "public_tools": ("diagnose", "plan", "execute", "verify", "status"),
        "public_schema_bytes": 18_000,
        "max_public_tools": 8,
        "max_public_schema_bytes": 24_000,
        "upstream_tools_internal": True,
        "deterministic_core": True,
        "bounded_llm": True,
        "durable_jobs": True,
        "typed_mutations": True,
        "evidence_by_reference": True,
        "unrestricted_mutation_prompt": False,
    }
    values.update(changes)
    return facade.SemanticFacadeDesign(**values)


def _covered(targets: tuple[str, ...], path: str) -> bool:
    return any(
        path == target
        or path.startswith(f"{target.rstrip('/')}/")
        or ("*" in target and fnmatch.fnmatch(path, target))
        for target in targets
    )


def test_reference_semantic_facade_passes_with_internal_upstreams_and_typed_jobs() -> None:
    facade = _load("wave2_semantic_facade_valid", TOOL)
    design = _valid_design(facade)
    assert facade.validate_semantic_facade(design) is design


@pytest.mark.parametrize(
    "changes",
    [
        {"public_tools": tuple(f"op-{index}" for index in range(11)), "max_public_tools": 10},
        {"public_schema_bytes": 24_001, "max_public_schema_bytes": 24_000},
    ],
)
def test_design_exceeding_tool_or_schema_budget_fails(changes: dict[str, object]) -> None:
    facade = _load("wave2_semantic_facade_budget", TOOL)
    with pytest.raises(ValueError, match="budget"):
        facade.validate_semantic_facade(_valid_design(facade, **changes))


def test_unbounded_llm_or_untyped_prompt_mutation_fails_profile() -> None:
    facade = _load("wave2_semantic_facade_safety", TOOL)
    with pytest.raises(ValueError, match="LLM reasoning"):
        facade.validate_semantic_facade(_valid_design(facade, bounded_llm=False))
    with pytest.raises(ValueError, match="typed target/action"):
        facade.validate_semantic_facade(_valid_design(facade, unrestricted_mutation_prompt=True))


def test_standard_documents_semantic_profile_and_tool_is_quality_gated() -> None:
    text = STANDARD.read_text(encoding="utf-8")
    for phrase in (
        "at most ten semantic operations",
        "max_public_schema_bytes",
        "deterministic discovery/probes/policy",
        "Long work uses durable jobs",
        "privileged mutations use typed targets/actions/constraints",
    ):
        assert phrase in text

    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert "tools/semantic_facade.py" in manifest["required"]
    inventories = _load("wave2_quality_targets_facade", QUALITY_TARGETS)
    path = "skills/mcp-server-architect/tools/semantic_facade.py"
    for targets in (
        inventories.QUALITY_PATHS,
        inventories.TYPE_PATHS,
        inventories.BANDIT_PATHS,
        inventories.POLICY_COVERAGE_PATHS,
    ):
        assert _covered(targets, path)

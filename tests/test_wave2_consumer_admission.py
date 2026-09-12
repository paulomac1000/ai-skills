"""Wave 2 regressions for deterministic consumer admission classification."""

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
TOOL = CONSUMER / "tools/admission.py"
MANIFEST = CONSUMER / "manifest.yaml"
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


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, "MATCH"),
        ({"observed_matches_expected": False, "exact_runtime_identity_available": False}, "SUSPECTED_DRIFT"),
        ({"observed_matches_expected": False}, "CONFIRMED_DRIFT"),
        ({"owner_known": False}, "OWNER_UNKNOWN"),
        ({"runtime_fresh": None}, "RUNTIME_STALE_OR_UNKNOWN"),
        ({"capability_ready": False}, "CAPABILITY_DEGRADED"),
    ],
)
def test_all_six_admission_classifications(changes: dict[str, object], expected: str) -> None:
    admission = _load("wave2_admission", TOOL)
    values: dict[str, object] = {
        "owner_known": True,
        "target_resolved": True,
        "runtime_fresh": True,
        "capability_ready": True,
        "observed_matches_expected": True,
        "exact_runtime_identity_available": True,
    }
    values.update(changes)
    evidence = admission.AdmissionEvidence(**values)
    assert admission.classify_admission(evidence).value == expected


def test_unknown_owner_and_ambiguous_target_block_mutation() -> None:
    admission = _load("wave2_admission_gate", TOOL)
    baseline = {
        "owner_known": True,
        "target_resolved": True,
        "runtime_fresh": True,
        "capability_ready": True,
        "observed_matches_expected": True,
        "exact_runtime_identity_available": True,
    }
    assert admission.mutation_allowed(admission.AdmissionEvidence(**baseline)) is True
    assert admission.mutation_allowed(admission.AdmissionEvidence(**(baseline | {"owner_known": False}))) is False
    assert admission.mutation_allowed(admission.AdmissionEvidence(**(baseline | {"target_resolved": False}))) is False


def test_admission_tool_is_required_and_in_all_quality_inventories() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert "tools/admission.py" in manifest["required"]
    inventories = _load("wave2_quality_targets_admission", QUALITY_TARGETS)
    path = "skills/mcp-server-consumer/tools/admission.py"
    for targets in (
        inventories.QUALITY_PATHS,
        inventories.TYPE_PATHS,
        inventories.BANDIT_PATHS,
        inventories.POLICY_COVERAGE_PATHS,
    ):
        assert _covered(targets, path)

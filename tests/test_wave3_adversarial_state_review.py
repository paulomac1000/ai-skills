"""Wave 3 adversarial state-transition playbook regressions."""

from __future__ import annotations

import fnmatch
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import yaml

ROOT = Path(__file__).resolve().parents[1]
CI_SKILL = ROOT / "skills/ci-cd-architect"
TOOL = CI_SKILL / "tools/review_state_transitions.py"
FIXTURES = CI_SKILL / "references/adversarial-state-transition-fixtures.yaml"
MANIFEST = CI_SKILL / "manifest.yaml"
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


def test_each_baseline_fixture_produces_only_its_expected_finding() -> None:
    module = _load("wave3_state_transition_fixtures", TOOL)
    document = yaml.safe_load(FIXTURES.read_text(encoding="utf-8"))
    cases = document["cases"]
    assert len(cases) == 9
    fields = {case["field"] for case in cases}
    assert fields == {field for field, _ in module._FINDINGS}
    for case in cases:
        probe = module.TransitionProbe(**{case["field"]: True})
        assert module.review_transition_probe(probe) == (case["expected"],)


def test_combined_adversarial_conditions_are_not_collapsed() -> None:
    module = _load("wave3_state_transition_combined", TOOL)
    probe = module.TransitionProbe(
        stale_generation=True,
        timeout_after_effect_unreconciled=True,
        partial_effect_unrecovered=True,
    )
    assert module.review_transition_probe(probe) == (
        "STALE_GENERATION_ACCEPTED",
        "TIMEOUT_AFTER_EFFECT_UNRECONCILED",
        "PARTIAL_EFFECT_UNRECOVERED",
    )
    assert module.review_transition_probe(module.TransitionProbe()) == ()


def test_playbook_and_tool_are_governed_and_quality_gated() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    for path in (
        "references/adversarial-state-transition-review.md",
        "references/adversarial-state-transition-fixtures.yaml",
        "tools/review_state_transitions.py",
    ):
        assert path in manifest["required"]
    text = (CI_SKILL / "references/adversarial-state-transition-review.md").read_text(encoding="utf-8")
    for phrase in (
        "stale generation",
        "timeout after an effect",
        "Concurrent writers",
        "Tombstones",
        "Recovery on a new generation",
    ):
        assert phrase in text
    inventories = _load("wave3_quality_targets_state_review", QUALITY_TARGETS)
    path = "skills/ci-cd-architect/tools/review_state_transitions.py"
    for targets in (
        inventories.QUALITY_PATHS,
        inventories.TYPE_PATHS,
        inventories.BANDIT_PATHS,
        inventories.POLICY_COVERAGE_PATHS,
    ):
        assert _covered(targets, path)

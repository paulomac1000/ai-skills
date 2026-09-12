"""Wave 3 evaluations for risk-based QA change verification."""

from __future__ import annotations

import fnmatch
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/qa-change-verifier"
TOOL = SKILL / "tools/plan_verification.py"
QUALITY_TARGETS = ROOT / "scripts/quality_targets.py"
README = ROOT / "README.md"


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


def test_low_risk_plan_requires_static_and_unit_only() -> None:
    module = _load("wave3_qa_low", TOOL)
    plan = module.plan_verification(module.ChangeRisk(change_surface="docs", blast_radius="local"))
    assert plan.risk == module.RiskLevel.LOW
    assert plan.required_layers == ("static", "unit")


def test_medium_risk_plan_adds_integration_and_exact_artifact() -> None:
    module = _load("wave3_qa_medium", TOOL)
    plan = module.plan_verification(
        module.ChangeRisk(change_surface="internal", blast_radius="component", stateful=True)
    )
    assert plan.risk == module.RiskLevel.MEDIUM
    assert plan.required_layers == (
        "static",
        "unit",
        "integration",
        "exact_artifact",
    )


def test_high_risk_plan_requires_full_verification_stack() -> None:
    module = _load("wave3_qa_high", TOOL)
    plan = module.plan_verification(
        module.ChangeRisk(
            change_surface="public_contract",
            blast_radius="external",
            stateful=True,
            security_sensitive=True,
            external_dependency=True,
            post_deploy_observable=True,
        )
    )
    assert plan.risk == module.RiskLevel.HIGH
    assert plan.required_layers == module.LAYERS


def test_stale_simulator_is_invalidated_for_candidate() -> None:
    module = _load("wave3_qa_simulator", TOOL)
    stale = module.plan_verification(
        module.ChangeRisk(
            change_surface="internal",
            blast_radius="component",
            candidate_revision="sha-new",
            simulator_revision="sha-old",
        )
    )
    fresh = module.plan_verification(
        module.ChangeRisk(
            change_surface="internal",
            blast_radius="component",
            candidate_revision="sha-new",
            simulator_revision="sha-new",
        )
    )
    assert stale.simulator_valid is False
    assert fresh.simulator_valid is True


def test_exact_evidence_binding_rejects_stale_revision_or_missing_digest() -> None:
    module = _load("wave3_qa_evidence", TOOL)
    digest = "sha256:" + "a" * 64
    assert module.validate_exact_evidence(module.ExactEvidenceBinding("sha-1", "sha-1", digest), artifact_required=True)
    assert not module.validate_exact_evidence(
        module.ExactEvidenceBinding("sha-1", "sha-0", digest), artifact_required=True
    )
    assert not module.validate_exact_evidence(
        module.ExactEvidenceBinding("sha-1", "sha-1", None), artifact_required=True
    )


def test_harness_and_product_failures_are_not_conflated() -> None:
    module = _load("wave3_qa_failure", TOOL)
    assert module.classify_failure(harness_failure=True, product_failure=False) == module.FailureClass.HARNESS_FAILURE
    assert module.classify_failure(harness_failure=False, product_failure=True) == module.FailureClass.PRODUCT_FAILURE
    assert module.classify_failure(harness_failure=True, product_failure=True) == module.FailureClass.MIXED_FAILURE
    assert module.classify_failure(harness_failure=False, product_failure=False) == module.FailureClass.NONE


def test_skill_is_catalogued_manifested_and_quality_gated() -> None:
    manifest = yaml.safe_load((SKILL / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["name"] == "qa-change-verifier"
    assert "tools/plan_verification.py" in manifest["required"]
    assert "`qa-change-verifier`" in README.read_text(encoding="utf-8")
    inventories = _load("wave3_quality_targets_qa", QUALITY_TARGETS)
    path = "skills/qa-change-verifier/tools/plan_verification.py"
    for targets in (
        inventories.QUALITY_PATHS,
        inventories.TYPE_PATHS,
        inventories.BANDIT_PATHS,
        inventories.POLICY_COVERAGE_PATHS,
    ):
        assert _covered(targets, path)

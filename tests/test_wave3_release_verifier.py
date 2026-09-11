"""Wave 3 regressions for the reusable MCP gateway release verifier."""

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
TOOL = SKILL / "tools/compose_release_verdict.py"
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


def _phases(module: ModuleType, **status_overrides: str) -> tuple[object, ...]:
    return tuple(
        module.PhaseResult(
            name=name,
            status=status_overrides.get(name, "pass"),
            contract_ref=module.COMPOSED_CONTRACTS[name],
            evidence_ref=f"evidence://{name}",
            summary=f"{name} verified",
        )
        for name in module.REQUIRED_PHASES
    )


def test_all_composed_phases_produce_bounded_pass_receipt() -> None:
    module = _load("wave3_release_verifier_happy", TOOL)
    receipt = module.compose_release_receipt(
        source_revision="a" * 40,
        artifact_digest="sha256:" + "b" * 64,
        phases=_phases(module),
    )
    assert receipt["verdict"] == "pass"
    assert [phase["name"] for phase in receipt["phases"]] == list(module.REQUIRED_PHASES)
    assert len(str(receipt)) < module.MAX_RECEIPT_BYTES


def test_any_failed_or_missing_required_phase_fails_closed() -> None:
    module = _load("wave3_release_verifier_fail", TOOL)
    failed = module.compose_release_receipt(
        source_revision="a" * 40,
        artifact_digest="sha256:" + "b" * 64,
        phases=_phases(module, lifecycle="fail"),
    )
    assert failed["verdict"] == "fail"
    missing = module.compose_release_receipt(
        source_revision="a" * 40,
        artifact_digest="sha256:" + "b" * 64,
        phases=tuple(phase for phase in _phases(module) if phase.name != "cleanup"),
    )
    assert missing["verdict"] == "fail"
    assert next(phase for phase in missing["phases"] if phase["name"] == "cleanup")["status"] == "not_run"


def test_required_phase_cannot_claim_a_competing_contract_owner() -> None:
    module = _load("wave3_release_verifier_owner", TOOL)
    phases = list(_phases(module))
    phases[3] = module.PhaseResult(
        name="schema",
        status="pass",
        contract_ref="forked-schema-rule",
        evidence_ref="evidence://schema",
    )
    with pytest.raises(module.ReleaseCompositionError, match="must consume"):
        module.compose_release_receipt(
            source_revision="a" * 40,
            artifact_digest="sha256:" + "b" * 64,
            phases=tuple(phases),
        )


def test_phase_and_output_boundaries_reject_unbounded_content() -> None:
    module = _load("wave3_release_verifier_bounds", TOOL)
    phase = module.PhaseResult(
        name="extension",
        status="pass",
        contract_ref="project/extension",
        evidence_ref="evidence://extension",
        summary="x" * (module.MAX_SUMMARY_CHARS + 1),
    )
    with pytest.raises(module.ReleaseCompositionError, match="summary exceeds"):
        module.compose_release_receipt(
            source_revision="a" * 40,
            artifact_digest="sha256:" + "b" * 64,
            phases=_phases(module) + (phase,),
        )
    extensions = tuple(
        module.PhaseResult(
            name=f"extension-{index}",
            status="pass",
            contract_ref="project/extension",
            evidence_ref=f"evidence://extension-{index}",
        )
        for index in range(module.MAX_PHASES + 1)
    )
    with pytest.raises(module.ReleaseCompositionError, match="phase count"):
        module.compose_release_receipt(
            source_revision="a" * 40,
            artifact_digest="sha256:" + "b" * 64,
            phases=extensions,
        )


def test_skill_manifest_and_quality_inventory_are_complete() -> None:
    manifest = yaml.safe_load((SKILL / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["name"] == "mcp-gateway-release-verifier"
    assert "tools/compose_release_verdict.py" in manifest["required"]
    standard = (SKILL / "STANDARD.md").read_text(encoding="utf-8")
    for phrase in ("consume, not redefine", "exact-artifact launch", "execution integrity", "bounded"):
        assert phrase in standard
    inventories = _load("wave3_quality_targets_release_verifier", QUALITY_TARGETS)
    path = "skills/mcp-gateway-release-verifier/tools/compose_release_verdict.py"
    for targets in (
        inventories.QUALITY_PATHS,
        inventories.TYPE_PATHS,
        inventories.BANDIT_PATHS,
        inventories.POLICY_COVERAGE_PATHS,
    ):
        assert _covered(targets, path)

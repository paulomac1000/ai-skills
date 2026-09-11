"""Wave 2 regressions for canonical authority, projection outbox, and retarget identity."""

from __future__ import annotations

import fnmatch
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import yaml

ROOT = Path(__file__).resolve().parents[1]
ARCHITECT = ROOT / "skills/mcp-server-architect"
TOOL = ARCHITECT / "tools/control_plane_invariants.py"
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


def _covered(targets: tuple[str, ...], path: str) -> bool:
    return any(
        path == target
        or path.startswith(f"{target.rstrip('/')}/")
        or ("*" in target and fnmatch.fnmatch(path, target))
        for target in targets
    )


def test_outbox_ambiguity_requires_authoritative_reconciliation() -> None:
    control = _load("wave2_control_plane_outbox", TOOL)
    pending = control.ProjectionOutboxEntry("entity-7", "projection-gen-4", "idem-9")
    ambiguous = control.mark_projection_ambiguous(pending)

    assert ambiguous.state.value == "RECONCILE_REQUIRED"
    assert control.reconcile_projection_delivery(ambiguous, None) is ambiguous
    assert control.reconcile_projection_delivery(ambiguous, True).state.value == "CONFIRMED"
    assert control.reconcile_projection_delivery(ambiguous, False).state.value == "DISPROVEN"


def test_retarget_preserves_canonical_identity_and_audits_transition() -> None:
    control = _load("wave2_control_plane_retarget", TOOL)
    original = control.CanonicalEntity("entity-7", "canonical-store", "board-a/item-3")
    moved = control.retarget_projection(original, "board-b/item-8", reason="provider transfer")

    assert moved.canonical_id == original.canonical_id
    assert moved.owner == original.owner
    assert moved.projection_target == "board-b/item-8"
    assert moved.transition_history[-1].startswith("retarget:board-a/item-3->board-b/item-8:")


def test_standard_covers_complete_canonical_projection_pattern_bundle() -> None:
    text = STANDARD.read_text(encoding="utf-8")
    for phrase in (
        "one canonical store/authority",
        "Ingress records both observation context and affected canonical owner",
        "durable idempotent outbox",
        "Raw provider adapters refuse mutation",
        "preserves canonical entity identity/history",
        "completed externally or by an operator",
        "bounded actionable brief/status",
    ):
        assert phrase in text


def test_control_plane_tool_is_required_and_in_all_quality_inventories() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert "tools/control_plane_invariants.py" in manifest["required"]
    inventories = _load("wave2_quality_targets_control_plane", QUALITY_TARGETS)
    path = "skills/mcp-server-architect/tools/control_plane_invariants.py"
    for targets in (
        inventories.QUALITY_PATHS,
        inventories.TYPE_PATHS,
        inventories.BANDIT_PATHS,
        inventories.POLICY_COVERAGE_PATHS,
    ):
        assert _covered(targets, path)

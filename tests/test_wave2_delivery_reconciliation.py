"""Wave 2 regressions for NO_ACK authoritative reconciliation."""

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
TOOL = CONSUMER / "tools/delivery_reconciliation.py"
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
    return {"schema_version": 1, "runtime_id": "runtime-a", "instance_generation": "gen-9"}


def _context(reconcile: ModuleType) -> object:
    return reconcile.DeliveryContext("target-a", "op-42", "idem-42", _identity())


def _covered(targets: tuple[str, ...], path: str) -> bool:
    return any(
        path == target
        or path.startswith(f"{target.rstrip('/')}/")
        or ("*" in target and fnmatch.fnmatch(path, target))
        for target in targets
    )


def test_no_ack_requires_reconciliation_and_never_speculatively_resends() -> None:
    reconcile = _load("wave2_delivery_no_ack", TOOL)
    decision = reconcile.ambiguous_transport_outcome("NO_ACK", _context(reconcile))

    assert decision.state.value == "RECONCILE_REQUIRED"
    assert decision.safe_to_retry is False
    assert reconcile.should_resend(decision) is False


def test_authoritative_read_back_confirms_delivery_after_no_ack() -> None:
    reconcile = _load("wave2_delivery_confirm", TOOL)
    initial = reconcile.ambiguous_transport_outcome("NO_ACK", _context(reconcile))
    confirmed = reconcile.apply_authoritative_read_back(initial, True)

    assert confirmed.state.value == "DELIVERED"
    assert confirmed.context is initial.context
    assert reconcile.should_resend(confirmed) is False


def test_retry_requires_disproven_delivery_and_explicit_exact_replay_safety() -> None:
    reconcile = _load("wave2_delivery_retry", TOOL)
    initial = reconcile.ambiguous_transport_outcome("NO_ACK", _context(reconcile))
    disproven = reconcile.apply_authoritative_read_back(initial, False, exact_replay_safe=False)
    replay_safe = reconcile.apply_authoritative_read_back(initial, False, exact_replay_safe=True)

    assert reconcile.should_resend(disproven) is False
    assert reconcile.should_resend(replay_safe) is True


def test_reconciliation_preserves_canonical_identity_without_legacy_fields() -> None:
    reconcile = _load("wave2_delivery_identity", TOOL)
    initial = reconcile.ambiguous_transport_outcome("NO_ACK", _context(reconcile))
    confirmed = reconcile.apply_authoritative_read_back(initial, True)

    identity = dict(confirmed.context.runtime_identity)
    assert identity == _identity()
    assert "server_id" not in identity
    assert "generation" not in identity
    assert "provenance" not in identity

    with pytest.raises(ValueError, match="canonical runtime_id"):
        reconcile.DeliveryContext(
            "target-a",
            "op-42",
            "idem-42",
            {"schema_version": 1, "server_id": "runtime-a", "generation": "gen-9"},
        )


def test_delivery_tool_is_required_and_in_all_quality_inventories() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert "tools/delivery_reconciliation.py" in manifest["required"]
    inventories = _load("wave2_quality_targets_delivery", QUALITY_TARGETS)
    path = "skills/mcp-server-consumer/tools/delivery_reconciliation.py"
    for targets in (
        inventories.QUALITY_PATHS,
        inventories.TYPE_PATHS,
        inventories.BANDIT_PATHS,
        inventories.POLICY_COVERAGE_PATHS,
    ):
        assert _covered(targets, path)

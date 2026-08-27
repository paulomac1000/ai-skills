"""Consumer risk provenance remains complete for compatibility and orthogonal sensitivity signals."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "skills/mcp-server-consumer/tools/decision_engine.py"
REFERENCE = ROOT / "skills/mcp-server-consumer/references/risk-and-trust.md"


def _engine() -> ModuleType:
    spec = importlib.util.spec_from_file_location("consumer_provenance_contract", ENGINE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_sensitive_provenance_survives_stronger_ordered_risk() -> None:
    engine = _engine()

    profile = engine.infer_capability_profile(
        "[DANGEROUS] execute",
        {"sensitive": True},
    )

    assert profile.risk is engine.Risk.DANGEROUS
    assert profile.sensitive is True
    assert "name-prefix-escalation" in profile.source.split("+")
    assert "sensitive" in profile.source.split("+")


def test_legacy_unbound_escalations_are_explicit_and_documented() -> None:
    engine = _engine()
    policy = engine.infer_capability_profile(
        "inventory.update",
        {},
        trusted_policy=engine.TrustedCapabilityPolicy(engine.Risk.WRITE),
    )
    contract = engine.infer_capability_profile(
        "inventory.update",
        {},
        trusted_contract=engine.TrustedCapabilityContract(engine.Risk.WRITE),
    )

    assert "legacy-unbound-policy-escalation" in policy.source.split("+")
    assert "legacy-unbound-contract-escalation" in contract.source.split("+")

    reference = REFERENCE.read_text(encoding="utf-8")
    assert "`legacy-unbound-policy-escalation`" in reference
    assert "`legacy-unbound-contract-escalation`" in reference

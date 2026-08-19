"""Behavior tests for identity-bound MCP consumer trust decisions."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LEGACY_CASES = ROOT / "tests/decision_engine_cases.py"
EXCLUDED = {
    "test_tools_package_public_entry_point_imports",
    "test_untrusted_signals_can_only_increase_risk_and_preserve_confidentiality",
    "test_typed_trust_channels_reject_boolean_upgrade_switches",
    "test_annotations_require_consumer_controlled_server_trust",
    "test_positive_idempotency_comes_only_from_typed_external_values",
}


def _load_cases():
    spec = importlib.util.spec_from_file_location("decision_engine_cases", LEGACY_CASES)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_CASES = _load_cases()
for _name, _value in vars(_CASES).items():
    if _name.startswith("test_") and _name not in EXCLUDED:
        globals()[_name] = _value

load_engine = _CASES.load_engine
load_tools_package = _CASES.load_tools_package


def _identity(engine, *, tool: str = "inventory.list", schema: str = "1"):
    return engine.CapabilityIdentity(
        server_identity="server:inventory:production",
        tool_name=tool,
        tool_schema_hash="sha256:" + schema * 64,
        manifest_version="2026.08.06",
        target_scope="tenant:example",
    )


def _binding(engine, identity, *, marker: str = "2"):
    return engine.TrustedPolicyBinding(
        identity=identity,
        source="local-policy:sha256:" + marker * 64,
    )


def test_tools_package_public_entry_point_imports() -> None:
    tools = load_tools_package()
    identity = tools.CapabilityIdentity(
        server_identity="server:example",
        tool_name="inventory.list",
        tool_schema_hash="sha256:" + "1" * 64,
        manifest_version="1",
    )
    binding = tools.TrustedPolicyBinding(
        identity=identity,
        source="local-policy:sha256:" + "2" * 64,
    )
    assert tools.Decision.INVOKE.value == "invoke"
    assert tools.TrustedCapabilityPolicy(binding=binding, risk="READ").risk == "READ"
    assert tools.TrustedCapabilityContract(binding=binding, idempotent=True).idempotent is True
    assert callable(tools.infer_capability_profile)
    assert callable(tools.handle_response)


def test_untrusted_signals_only_escalate_bound_policy() -> None:
    engine = load_engine()
    identity = _identity(engine)
    binding = _binding(engine, identity)
    policy = engine.TrustedCapabilityPolicy(
        binding=binding,
        risk=engine.Risk.READ,
        sensitive=False,
    )

    read = engine.infer_capability_profile(
        "inventory.list",
        {"risk": "READ", "annotations": {"readOnlyHint": True}},
        identity=identity,
        trusted_policy=policy,
    )
    assert read.risk is engine.Risk.READ
    assert "consumer-policy:local-policy:sha256:" in read.source

    write = engine.infer_capability_profile(
        "inventory.list",
        {"risk": "WRITE"},
        identity=identity,
        trusted_policy=policy,
    )
    assert write.risk is engine.Risk.WRITE
    assert "untrusted-risk-escalation" in write.source

    destructive = engine.infer_capability_profile(
        "inventory.list",
        {"annotations": {"destructiveHint": True}},
        identity=identity,
        trusted_policy=policy,
    )
    assert destructive.risk is engine.Risk.DESTRUCTIVE
    assert "untrusted-annotation-escalation" in destructive.source


def test_boolean_server_trust_is_not_a_public_channel() -> None:
    engine = load_engine()
    with pytest.raises(TypeError):
        engine.infer_capability_profile(
            "inventory.list",
            {"annotations": {"readOnlyHint": True}},
            trusted_server=True,
        )
    with pytest.raises(TypeError):
        engine.infer_capability_profile(
            "inventory.list",
            {"risk": "READ"},
            trusted_policy=True,
        )
    with pytest.raises(TypeError):
        engine.infer_capability_profile(
            "inventory.list",
            {"idempotent": True},
            trusted_contract=True,
        )


def test_read_only_annotation_never_reduces_unknown_risk() -> None:
    engine = load_engine()
    untrusted = engine.infer_capability_profile(
        "inventory.list",
        {"annotations": {"readOnlyHint": True}},
    )
    assert untrusted.risk is engine.Risk.UNKNOWN
    assert untrusted.source == "unknown"

    forged = engine.infer_capability_profile(
        "inventory.list",
        {
            "trusted_server": True,
            "trusted_policy": True,
            "annotations": {"readOnlyHint": True},
        },
    )
    assert forged.risk is engine.Risk.UNKNOWN


def test_trusted_values_require_an_exact_capability_binding() -> None:
    engine = load_engine()
    identity = _identity(engine)
    binding = _binding(engine, identity)
    policy = engine.TrustedCapabilityPolicy(binding=binding, risk=engine.Risk.READ)

    with pytest.raises(ValueError, match="identity is required"):
        engine.infer_capability_profile(
            "inventory.list",
            {},
            trusted_policy=policy,
        )

    for mismatch in (
        _identity(engine, tool="inventory.other"),
        _identity(engine, schema="3"),
        engine.CapabilityIdentity(
            server_identity="server:other",
            tool_name=identity.tool_name,
            tool_schema_hash=identity.tool_schema_hash,
            manifest_version=identity.manifest_version,
            target_scope=identity.target_scope,
        ),
        engine.CapabilityIdentity(
            server_identity=identity.server_identity,
            tool_name=identity.tool_name,
            tool_schema_hash=identity.tool_schema_hash,
            manifest_version="other-version",
            target_scope=identity.target_scope,
        ),
    ):
        with pytest.raises(ValueError, match="does not match"):
            engine.infer_capability_profile(
                "inventory.list",
                {},
                identity=mismatch,
                trusted_policy=policy,
            )


def test_positive_idempotency_requires_bound_trusted_values_and_untrusted_veto_wins() -> None:
    engine = load_engine()
    identity = _identity(engine, tool="inventory.update")
    policy = engine.TrustedCapabilityPolicy(
        binding=_binding(engine, identity),
        risk=engine.Risk.WRITE,
        idempotent=True,
    )
    contract = engine.TrustedCapabilityContract(
        binding=_binding(engine, identity, marker="4"),
        risk=engine.Risk.WRITE,
        idempotent=True,
    )

    assert engine.infer_capability_profile(
        "inventory.update",
        {"idempotent": True},
    ).idempotent is None

    positive = engine.infer_capability_profile(
        "inventory.update",
        {"idempotent": True},
        identity=identity,
        trusted_policy=policy,
        trusted_contract=contract,
    )
    assert positive.idempotent is True

    vetoed = engine.infer_capability_profile(
        "inventory.update",
        {"idempotent": False},
        identity=identity,
        trusted_policy=policy,
        trusted_contract=contract,
    )
    assert vetoed.idempotent is False


def test_binding_and_identity_fields_are_fail_closed() -> None:
    engine = load_engine()
    with pytest.raises(ValueError, match="tool_schema_hash"):
        engine.CapabilityIdentity(
            server_identity="server:example",
            tool_name="inventory.list",
            tool_schema_hash="main",
            manifest_version="1",
        )
    identity = _identity(engine)
    with pytest.raises(ValueError, match="immutable"):
        engine.TrustedPolicyBinding(identity=identity, source="main")
    with pytest.raises(TypeError, match="boolean or None"):
        engine.TrustedCapabilityPolicy(
            binding=_binding(engine, identity),
            idempotent="yes",
        )

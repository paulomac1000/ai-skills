"""Regression tests for executable findings from the exact-head bot review."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_consumer_policy_identity_must_match_invoked_tool_name() -> None:
    engine = _load(
        ROOT / "skills/mcp-server-consumer/tools/decision_engine.py",
        "review_followup_decision_engine",
    )
    identity = engine.CapabilityIdentity(
        server_identity="server:inventory",
        tool_name="inventory.list",
        tool_schema_hash="sha256:" + "1" * 64,
        manifest_version="1",
    )
    policy = engine.TrustedCapabilityPolicy(
        binding=engine.TrustedPolicyBinding(
            identity=identity,
            source="reviewed-policy:sha256:" + "2" * 64,
        ),
        risk=engine.Risk.READ,
    )
    with pytest.raises(ValueError, match="invoked capability name"):
        engine.infer_capability_profile(
            "inventory.delete",
            {},
            identity=identity,
            trusted_policy=policy,
        )


def test_capability_schema_separates_lifecycle_from_operation_kind() -> None:
    schema = json.loads((ROOT / "contracts/capability-manifest.schema.json").read_text(encoding="utf-8"))
    assert schema["properties"]["operation_kind"]["enum"] == [
        "read",
        "write",
        "destructive",
    ]
    assert schema["properties"]["active_state"]["enum"] == [
        "active",
        "inactive",
        "deprecated",
    ]
    approval = schema["properties"]["approval"]["properties"]["binds"]
    assert "expires-at" in approval["items"]["enum"]
    assert any(condition.get("contains", {}).get("const") == "expires-at" for condition in approval["allOf"])


def test_generated_manifests_are_active_and_read_flags_fail_closed() -> None:
    capability_dir = ROOT / "skills/mcp-server-architect/tools/python-template/src/__PACKAGE__/capabilities"
    paths = sorted(capability_dir.glob("*.json.template"))
    assert {path.name for path in paths} == {
        "describe_capabilities.json.template",
        "list_items.json.template",
        "put_item.json.template",
    }
    for path in paths:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["active_state"] == "active"
        if manifest["operation_kind"] == "read":
            assert manifest["impact"] == "none"
            for field in (
                "retryable",
                "reversible",
                "requires_confirmation",
                "idempotency_key_required",
            ):
                assert manifest[field] is False
        if manifest["requires_confirmation"]:
            assert "expires-at" in manifest["approval"]["binds"]


def test_dotnet_projection_preserves_lifecycle_and_expiry_binding() -> None:
    adapter = (
        ROOT / "skills/mcp-server-architect/tools/dotnet-template/src/"
        "__NAMESPACE__.Mcp.Server/CanonicalCapabilityManifest.cs.template"
    ).read_text(encoding="utf-8")
    assert "var activeState = manifest.ActiveState switch" in adapter
    assert 'CapabilityActiveState.Active => "active"' in adapter
    assert (
        "CapabilityActiveState.Disabled or CapabilityActiveState.Degraded or "
        'CapabilityActiveState.Unavailable => "inactive"' in adapter
    )
    assert 'CapabilityActiveState.Deprecated => "deprecated"' in adapter
    assert '"expires-at"' in adapter
    assert "only active capabilities may be registered" in adapter
    assert 'operationKind == "read" ? "read" : "write"' not in adapter


def test_windows_atomic_publication_normalizes_existing_target() -> None:
    generator = (ROOT / "skills/mcp-server-architect/tools/generate_dotnet_server.py").read_text(encoding="utf-8")
    windows = generator.split('if operating_system == "Windows":', 1)[1]
    windows = windows.split("raise RuntimeError", 1)[0]
    assert "except FileExistsError as exc:" in windows
    assert '"generation target already exists"' in windows


def test_release_template_lowercases_ghcr_identity_and_attestation_subject() -> None:
    template = (ROOT / "skills/ci-cd-architect/templates/publish.yml.template").read_text(encoding="utf-8")
    assert 'repository="ghcr.io/${GITHUB_REPOSITORY,,}"' in template
    assert "subject_name=$repository" in template
    assert "subject-name: ${{ steps.promote.outputs.subject_name }}" in template
    assert "docker push --all-tags" not in template

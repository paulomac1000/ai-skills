"""Additional fail-closed regressions for untrusted MCP response and helper shapes."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_engine():
    path = ROOT / "skills/mcp-server-consumer/tools/decision_engine.py"
    spec = importlib.util.spec_from_file_location("mcp_decision_engine_payload_regression", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_malformed_success_payloads_fail_closed() -> None:
    engine = load_engine()
    for response in (
        {"content": None},
        {"content": 7},
        {"content": [{}]},
        {"content": [{"type": "unknown"}]},
        {"content": [{"type": "text"}]},
        {"content": [{"type": "text", "text": 7}]},
        {"content": [{"type": "text", "text": "ok", "annotations": []}]},
        {"content": [{"type": "image", "data": "Zm9v"}]},
        {"content": [{"type": "audio", "data": "", "mimeType": "audio/wav"}]},
        {"content": [{"type": "resource_link", "uri": "https://example.invalid"}]},
        {"content": [{"type": "resource_link", "uri": "u", "name": "n", "size": True}]},
        {"content": [{"type": "resource", "resource": {"text": "missing uri"}}]},
        {"content": [{"type": "resource", "resource": {"uri": "u"}}]},
        {"content": [{"type": "resource", "resource": {"uri": "u", "text": "x", "blob": "eA=="}}]},
        {"content": [{"type": "text", "text": "ok"}, 7]},
        {"structuredContent": None},
        {"structuredContent": []},
        {"isError": False, "content": None},
    ):
        result = engine.handle_response(response)
        assert result.success is False, response
        assert result.error_code == "MALFORMED_RESPONSE", response


def test_valid_mcp_content_blocks_and_legacy_success_shapes_remain_supported() -> None:
    engine = load_engine()
    for response in (
        {"content": []},
        {"content": "legacy text"},
        {"content": [{"type": "text", "text": "ok"}]},
        {"content": [{"type": "image", "data": "Zm9v", "mimeType": "image/png"}]},
        {"content": [{"type": "audio", "data": "Zm9v", "mimeType": "audio/wav"}]},
        {
            "content": [
                {
                    "type": "resource_link",
                    "uri": "https://example.invalid/resource",
                    "name": "resource",
                    "description": "bounded resource",
                    "mimeType": "text/plain",
                    "size": 0,
                }
            ]
        },
        {"content": [{"type": "resource", "resource": {"uri": "file:///text", "text": ""}}]},
        {
            "content": [
                {
                    "type": "resource",
                    "resource": {"uri": "file:///blob", "blob": "", "mimeType": "application/octet-stream"},
                }
            ]
        },
        {"structuredContent": {}},
        {"data": None},
        {"success": True},
    ):
        assert engine.handle_response(response).success is True, response


def test_retry_rejects_malformed_boolean_claims() -> None:
    engine = load_engine()
    assert not engine.should_retry(
        error_code="TIMEOUT",
        attempt=0,
        operation_idempotent=True,
        manifest={"retryable": "yes"},
        response_retryable=True,
    )
    assert not engine.should_retry(
        error_code="TIMEOUT",
        attempt=0,
        operation_idempotent=True,
        manifest={"retryable": True},
        response_retryable="yes",
    )


def test_untrusted_helper_shapes_do_not_raise_or_select() -> None:
    engine = load_engine()
    assert (
        engine.select_efficient_tool(
            [{"name": "bad", "capabilities": True}],
            required_capabilities=["read"],
        )
        is None
    )
    decision = engine.get_pagination_decision(
        None,
        outcome_satisfied=False,
        pages_seen=0,
        max_pages=2,
    )
    assert not decision.continue_paging
    assert decision.reason == "invalid pagination metadata"


def test_dotnet_manifest_canonical_fields_escalate_monotonically() -> None:
    engine = load_engine()
    identity = engine.CapabilityIdentity(
        server_identity="server:inventory",
        tool_name="list_items",
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
    profile = engine.infer_capability_profile(
        "list_items",
        {"risk": "READ", "sideEffects": "write", "requiresConfirmation": True},
        identity=identity,
        trusted_policy=policy,
    )
    assert profile.risk is engine.Risk.WRITE
    assert profile.requires_confirmation is True
    assert "side-effect-escalation" in profile.source

    destructive = engine.infer_capability_profile(
        "tool",
        {"side_effects": "destructive"},
    )
    assert destructive.risk is engine.Risk.DESTRUCTIVE


def test_malformed_top_level_meta_and_retry_markers_fail_closed() -> None:
    engine = load_engine()
    malformed = (
        {"content": [], "_meta": []},
        {"content": [], "retryable": "yes"},
        {"isError": True, "content": [], "retryable": 1},
        {"error": {"code": "TIMEOUT", "message": "failed", "retryable": "yes"}},
    )
    for response in malformed:
        result = engine.handle_response(response)
        assert result.success is False, response
        assert result.error_code == "MALFORMED_RESPONSE", response

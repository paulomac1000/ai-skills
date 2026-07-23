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
        {"content": [{"type": "text", "text": "ok"}, 7]},
        {"structuredContent": None},
        {"structuredContent": []},
        {"isError": False, "content": None},
    ):
        result = engine.handle_response(response)
        assert result.success is False, response
        assert result.error_code == "MALFORMED_RESPONSE", response


def test_valid_empty_and_legacy_success_shapes_remain_supported() -> None:
    engine = load_engine()
    for response in (
        {"content": []},
        {"content": "legacy text"},
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
    assert engine.select_efficient_tool(
        [{"name": "bad", "capabilities": True}],
        required_capabilities=["read"],
    ) is None
    decision = engine.get_pagination_decision(
        None,
        outcome_satisfied=False,
        pages_seen=0,
        max_pages=2,
    )
    assert not decision.continue_paging
    assert decision.reason == "invalid pagination metadata"

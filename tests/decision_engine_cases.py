"""Behavior tests for the MCP consumer decision engine."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_engine():
    path = ROOT / "skills/mcp-server-consumer/tools/decision_engine.py"
    spec = importlib.util.spec_from_file_location("mcp_decision_engine", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_tools_package():
    directory = ROOT / "skills/mcp-server-consumer/tools"
    spec = importlib.util.spec_from_file_location(
        "mcp_consumer_tools",
        directory / "__init__.py",
        submodule_search_locations=[str(directory)],
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_unknown_risk_defers_instead_of_defaulting_to_read() -> None:
    engine = load_engine()
    assert engine.evaluate_decision("unclassified", False, "general") is engine.Decision.DEFER
    assert engine.infer_capability_profile("run").risk is engine.Risk.UNKNOWN
    assert engine.infer_capability_profile("[READ] list-items").risk is engine.Risk.UNKNOWN
    assert engine.infer_capability_profile("list", {"risk": "READ"}).risk is engine.Risk.UNKNOWN


def test_side_effect_policy() -> None:
    engine = load_engine()
    assert engine.evaluate_decision("READ", False, "general") is engine.Decision.INVOKE
    assert engine.evaluate_decision("WRITE", False, "confirmed_workflow") is engine.Decision.INVOKE
    assert engine.evaluate_decision("WRITE", False, "general") is engine.Decision.CONFIRM_THEN_INVOKE
    assert engine.evaluate_decision("SENSITIVE", False, "general") is engine.Decision.CONFIRM_THEN_INVOKE
    assert engine.evaluate_decision("SENSITIVE", False, "confirmed_workflow") is engine.Decision.INVOKE
    assert engine.evaluate_decision("DESTRUCTIVE", False, "general") is engine.Decision.CONFIRM_THEN_INVOKE
    assert engine.evaluate_decision("DANGEROUS", False, "general") is engine.Decision.REJECT
    assert engine.evaluate_decision("DANGEROUS", False, "explicit_by_name") is engine.Decision.CONFIRM_THEN_INVOKE


def test_retry_requires_valid_attempt_and_positive_non_conflicting_signals() -> None:
    engine = load_engine()
    governed = {
        "retryable": True,
        "retryConditions": {
            "retryable": True,
            "eligibleErrors": ["TIMEOUT"],
            "maxAttempts": 2,
            "backoffMilliseconds": 100,
            "requiresReconciliation": True,
        },
    }
    assert engine.should_retry(
        error_code="TIMEOUT",
        attempt=0,
        operation_idempotent=True,
        manifest=governed,
        reconciliation_completed=True,
    )
    assert engine.should_retry(error_code="TIMEOUT", attempt=0, operation_idempotent=True, response_retryable=True)
    for attempt in (-1, True, 2):
        assert not engine.should_retry(
            error_code="TIMEOUT",
            attempt=attempt,
            operation_idempotent=True,
            manifest=governed,
            reconciliation_completed=True,
        )
    for manifest in (None, {}, {"retryable": False}, {"retryable": True}):
        assert not engine.should_retry(error_code="TIMEOUT", attempt=0, operation_idempotent=True, manifest=manifest)
    assert not engine.should_retry(
        error_code="TIMEOUT",
        attempt=0,
        operation_idempotent=True,
        manifest=governed,
        response_retryable=False,
        reconciliation_completed=True,
    )
    assert not engine.should_retry(
        error_code="TIMEOUT",
        attempt=0,
        operation_idempotent=True,
        manifest={"retryable": False},
        response_retryable=True,
    )


def test_conflict_retry_requires_refreshed_precondition() -> None:
    engine = load_engine()
    kwargs = {
        "error_code": "CONFLICT",
        "attempt": 0,
        "operation_idempotent": True,
        "manifest": {
            "retryable": True,
            "retryConditions": {
                "retryable": True,
                "eligibleErrors": ["CONFLICT"],
                "maxAttempts": 2,
                "backoffMilliseconds": 100,
                "requiresReconciliation": False,
            },
        },
    }
    assert not engine.should_retry(**kwargs)
    assert engine.should_retry(**kwargs, precondition_refreshed=True)


def test_response_normalization_preserves_protocol_native_errors() -> None:
    engine = load_engine()
    success = engine.handle_response({"structuredContent": {"items": []}, "_meta": {"correlation_id": "abc"}})
    assert success.success and success.correlation_id == "abc"
    native = engine.handle_response({"isError": True, "content": [{"type": "text", "text": "device unavailable"}]})
    assert native.error_code == "MCP_TOOL_ERROR"
    assert native.error_message == "device unavailable"
    structured = engine.handle_response(
        {"isError": True, "structuredContent": {"code": "CONFLICT", "message": "stale"}}
    )
    assert structured.error_code == "CONFLICT"
    assert structured.error_message == "stale"


def test_every_explicit_legacy_error_shape_fails_closed() -> None:
    engine = load_engine()
    without_details = engine.handle_response({"success": False})
    assert without_details.success is False
    assert without_details.error_code == "LEGACY_ERROR"
    assert "without structured error" in without_details.error_message

    string_error = engine.handle_response({"error": "upstream rejected mutation"})
    assert string_error.success is False
    assert string_error.error_message == "upstream rejected mutation"

    for malformed_error in (None, [], 7, False):
        malformed = engine.handle_response({"error": malformed_error})
        assert malformed.success is False
        assert malformed.error_code == "LEGACY_ERROR"

    conflicting = engine.handle_response({"success": True, "error": "still failed"})
    assert conflicting.success is False
    assert conflicting.error_message == "still failed"

    malformed_success = engine.handle_response({"success": "yes"})
    assert malformed_success.success is False
    assert malformed_success.error_code == "MALFORMED_RESPONSE"


def test_efficiency_helpers_fail_closed() -> None:
    engine = load_engine()
    tools = [
        {"name": "wide", "capabilities": ["search", "read", "write"]},
        {"name": "read", "capabilities": ["search", "read"]},
        {"name": "batch-read", "capabilities": ["search", "read"], "batch": True},
    ]
    assert (
        engine.select_efficient_tool(tools, required_capabilities=["search", "read"], prefer_batch=True)["name"]
        == "batch-read"
    )
    assert engine.select_efficient_tool(tools, required_capabilities=[]) is None
    assert engine.choose_initial_detail_params({"properties": {"compact": {"type": "boolean"}}}) == {"compact": True}
    assert engine.choose_initial_detail_params({"properties": {"compact": {"type": "string", "enum": ["short"]}}}) == {}


def test_pagination_accepts_only_contract_valid_tokens_and_respects_final_marker() -> None:
    engine = load_engine()
    valid = engine.get_pagination_decision(
        {"next_cursor": "opaque"}, outcome_satisfied=False, pages_seen=1, max_pages=5
    )
    assert valid.continue_paging and valid.cursor == "opaque"
    for cursor in (True, 3, [], {}, ""):
        assert not engine.get_pagination_decision(
            {"next_cursor": cursor}, outcome_satisfied=False, pages_seen=1, max_pages=5
        ).continue_paging
    for offset in (True, -1, "0"):
        assert not engine.get_pagination_decision(
            {"next_offset": offset}, outcome_satisfied=False, pages_seen=1, max_pages=5
        ).continue_paging
    valid_offset = engine.get_pagination_decision(
        {"next_offset": 0}, outcome_satisfied=False, pages_seen=1, max_pages=5
    )
    assert valid_offset.continue_paging and valid_offset.offset == 0

    for final_meta in (
        {"has_more": False, "next_cursor": "stale"},
        {"has_more": False, "next_offset": 10},
    ):
        decision = engine.get_pagination_decision(final_meta, outcome_satisfied=False, pages_seen=1, max_pages=5)
        assert not decision.continue_paging
        assert decision.reason == "server marked final page"

    for malformed in (None, 0, "false", []):
        decision = engine.get_pagination_decision(
            {"has_more": malformed, "next_cursor": "stale"},
            outcome_satisfied=False,
            pages_seen=1,
            max_pages=5,
        )
        assert not decision.continue_paging
        assert decision.reason == "invalid has_more marker"

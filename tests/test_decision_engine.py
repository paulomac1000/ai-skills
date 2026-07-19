"""Behavior tests for the MCP consumer decision engine."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_engine():
    """Load the pure decision engine from the hyphenated skill directory."""
    path = ROOT / "skills/mcp-server-consumer/tools/decision_engine.py"
    spec = importlib.util.spec_from_file_location("mcp_decision_engine", path)
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


def test_untrusted_signals_can_only_increase_risk() -> None:
    engine = load_engine()
    assert engine.infer_capability_profile("[WRITE] update").risk is engine.Risk.WRITE
    assert engine.infer_capability_profile("run", {"risk": "DESTRUCTIVE"}).risk is engine.Risk.DESTRUCTIVE
    combined = engine.infer_capability_profile(
        "[DANGEROUS] execute", {"risk": "WRITE"}
    )
    assert combined.risk is engine.Risk.DANGEROUS
    assert engine.evaluate_decision(
        combined.risk, combined.requires_confirmation, "general"
    ) is engine.Decision.REJECT
    trusted = engine.infer_capability_profile(
        "[READ] misleading-name",
        {"risk": "WRITE", "trusted_policy": True, "requires_confirmation": True},
    )
    assert trusted.risk is engine.Risk.WRITE
    assert trusted.source == "local-policy"
    assert trusted.requires_confirmation is True


def test_annotations_require_an_explicit_server_trust_boundary() -> None:
    engine = load_engine()
    untrusted_destructive = engine.infer_capability_profile(
        "remove", {"annotations": {"destructiveHint": True}}
    )
    assert untrusted_destructive.risk is engine.Risk.DESTRUCTIVE
    assert untrusted_destructive.source == "untrusted-annotation-escalation"
    assert engine.infer_capability_profile(
        "list", {"annotations": {"readOnlyHint": True}}
    ).risk is engine.Risk.UNKNOWN
    assert engine.infer_capability_profile(
        "remove", {"trusted_server": True, "annotations": {"destructiveHint": True}}
    ).risk is engine.Risk.DESTRUCTIVE
    assert engine.infer_capability_profile(
        "list", {"trusted_server": True, "annotations": {"readOnlyHint": True}}
    ).risk is engine.Risk.READ
    conflicting = engine.infer_capability_profile(
        "[DANGEROUS] execute",
        {"annotations": {"destructiveHint": True}},
    )
    assert conflicting.risk is engine.Risk.DANGEROUS
    assert engine.evaluate_decision(
        conflicting.risk, conflicting.requires_confirmation, "general"
    ) is engine.Decision.REJECT


def test_positive_idempotency_requires_trusted_policy_or_contract() -> None:
    engine = load_engine()
    assert engine.infer_capability_profile(
        "update", {"idempotent": True}
    ).idempotent is None
    assert engine.infer_capability_profile(
        "update", {"idempotent": True, "trusted_server": True}
    ).idempotent is None
    assert engine.infer_capability_profile(
        "update", {"idempotent": True, "trusted_contract": True}
    ).idempotent is True
    assert engine.infer_capability_profile(
        "update", {"idempotent": True, "trusted_policy": True}
    ).idempotent is True
    assert engine.infer_capability_profile(
        "update", {"idempotent": False}
    ).idempotent is False


def test_side_effect_policy() -> None:
    engine = load_engine()
    assert engine.evaluate_decision("READ", False, "general") is engine.Decision.INVOKE
    assert engine.evaluate_decision("WRITE", False, "confirmed_workflow") is engine.Decision.INVOKE
    assert engine.evaluate_decision("WRITE", False, "general") is engine.Decision.CONFIRM_THEN_INVOKE
    assert engine.evaluate_decision("SENSITIVE", False, "general") is engine.Decision.CONFIRM_THEN_INVOKE
    assert engine.evaluate_decision("SENSITIVE", False, "explicit_by_name") is engine.Decision.CONFIRM_THEN_INVOKE
    assert engine.evaluate_decision("SENSITIVE", False, "confirmed_workflow") is engine.Decision.INVOKE
    assert engine.evaluate_decision("DESTRUCTIVE", False, "general") is engine.Decision.CONFIRM_THEN_INVOKE
    assert engine.evaluate_decision("DANGEROUS", False, "general") is engine.Decision.REJECT
    assert engine.evaluate_decision("DANGEROUS", False, "explicit_by_name") is engine.Decision.CONFIRM_THEN_INVOKE


def test_retry_requires_valid_attempt_and_positive_non_conflicting_signals() -> None:
    engine = load_engine()
    assert engine.should_retry(
        error_code="TIMEOUT", attempt=0, operation_idempotent=True, manifest={"retryable": True}
    )
    assert engine.should_retry(
        error_code="TIMEOUT", attempt=0, operation_idempotent=True, response_retryable=True
    )
    for attempt in (-1, True, 2):
        assert not engine.should_retry(
            error_code="TIMEOUT",
            attempt=attempt,
            operation_idempotent=True,
            manifest={"retryable": True},
        )
    for manifest in (None, {}, {"retryable": False}):
        assert not engine.should_retry(
            error_code="TIMEOUT", attempt=0, operation_idempotent=True, manifest=manifest
        )
    assert not engine.should_retry(
        error_code="TIMEOUT",
        attempt=0,
        operation_idempotent=True,
        manifest={"retryable": True},
        response_retryable=False,
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
        "manifest": {"retryable": True},
    }
    assert not engine.should_retry(**kwargs)
    assert engine.should_retry(**kwargs, precondition_refreshed=True)


def test_response_normalization_preserves_protocol_native_errors() -> None:
    engine = load_engine()
    success = engine.handle_response(
        {"structuredContent": {"items": []}, "_meta": {"correlation_id": "abc"}}
    )
    assert success.success and success.correlation_id == "abc"
    native = engine.handle_response(
        {"isError": True, "content": [{"type": "text", "text": "device unavailable"}]}
    )
    assert native.error_code == "MCP_TOOL_ERROR"
    assert native.error_message == "device unavailable"
    structured = engine.handle_response(
        {"isError": True, "structuredContent": {"code": "CONFLICT", "message": "stale"}}
    )
    assert structured.error_code == "CONFLICT"
    assert structured.error_message == "stale"


def test_legacy_failure_shapes_fail_closed() -> None:
    engine = load_engine()
    without_details = engine.handle_response({"success": False})
    assert without_details.success is False
    assert without_details.error_code == "LEGACY_ERROR"
    assert "without structured error" in without_details.error_message

    string_error = engine.handle_response({"error": "upstream rejected mutation"})
    assert string_error.success is False
    assert string_error.error_code == "LEGACY_ERROR"
    assert string_error.error_message == "upstream rejected mutation"

    conflicting = engine.handle_response({"success": True, "error": "still failed"})
    assert conflicting.success is False
    assert conflicting.error_message == "still failed"

    malformed = engine.handle_response({"success": "yes"})
    assert malformed.success is False
    assert malformed.error_code == "MALFORMED_RESPONSE"


def test_efficiency_helpers_fail_closed() -> None:
    engine = load_engine()
    tools = [
        {"name": "wide", "capabilities": ["search", "read", "write"]},
        {"name": "read", "capabilities": ["search", "read"]},
        {"name": "batch-read", "capabilities": ["search", "read"], "batch": True},
    ]
    assert engine.select_efficient_tool(
        tools, required_capabilities=["search", "read"], prefer_batch=True
    )["name"] == "batch-read"
    assert engine.select_efficient_tool(tools, required_capabilities=[]) is None
    assert engine.choose_initial_detail_params(
        {"properties": {"compact": {"type": "boolean"}}}
    ) == {"compact": True}
    assert engine.choose_initial_detail_params(
        {"properties": {"compact": {"type": "string", "enum": ["short"]}}}
    ) == {}


def test_pagination_accepts_only_contract_valid_tokens() -> None:
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

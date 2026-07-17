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


def test_read_write_destructive_and_dangerous_policy() -> None:
    engine = load_engine()
    assert engine.evaluate_decision("READ", False, "general") is engine.Decision.INVOKE
    assert engine.evaluate_decision("WRITE", False, "confirmed_workflow") is engine.Decision.INVOKE
    assert engine.evaluate_decision("WRITE", False, "general") is engine.Decision.CONFIRM_THEN_INVOKE
    assert engine.evaluate_decision("DESTRUCTIVE", False, "confirmed_workflow") is engine.Decision.CONFIRM_THEN_INVOKE
    assert engine.evaluate_decision("DANGEROUS", False, "general") is engine.Decision.REJECT
    assert engine.evaluate_decision("DANGEROUS", False, "explicit_by_name") is engine.Decision.CONFIRM_THEN_INVOKE


def test_sensitive_read_without_explicit_intent_requires_confirmation() -> None:
    engine = load_engine()
    assert engine.evaluate_decision("SENSITIVE", False, "not_explicit") is engine.Decision.CONFIRM_THEN_INVOKE
    assert engine.evaluate_decision("SENSITIVE", False, "confirmed_workflow") is engine.Decision.INVOKE


def test_profile_inference_prefers_explicit_metadata() -> None:
    engine = load_engine()
    profile = engine.infer_capability_profile(
        "[READ] misleading-name",
        {"risk": "WRITE", "requires_confirmation": True, "idempotent": False},
    )
    assert profile.risk is engine.Risk.WRITE
    assert profile.source == "metadata"
    assert profile.requires_confirmation is True
    assert profile.idempotent is False


def test_profile_inference_supports_prefix_and_annotations_conservatively() -> None:
    engine = load_engine()
    assert engine.infer_capability_profile("[READ] list-items").risk is engine.Risk.READ
    assert engine.infer_capability_profile("remove", {"annotations": {"destructiveHint": True}}).risk is engine.Risk.DESTRUCTIVE
    sensitive = engine.infer_capability_profile("[READ] get-secret", {"sensitive": True})
    assert sensitive.risk is engine.Risk.SENSITIVE


def test_retry_requires_safe_operation_and_positive_retry_signal() -> None:
    engine = load_engine()
    assert engine.should_retry(
        error_code="TIMEOUT",
        attempt=0,
        operation_idempotent=True,
        manifest={"retryable": True},
    )
    assert not engine.should_retry(
        error_code="TIMEOUT",
        attempt=0,
        operation_idempotent=False,
        manifest={"retryable": True},
    )
    assert not engine.should_retry(
        error_code="TIMEOUT",
        attempt=0,
        operation_idempotent=True,
        manifest={"retryable": False},
    )
    assert not engine.should_retry(
        error_code="TIMEOUT",
        attempt=2,
        operation_idempotent=True,
        manifest={"retryable": True},
    )


def test_response_normalization_handles_success_and_protocol_error() -> None:
    engine = load_engine()
    success = engine.handle_response(
        {"structuredContent": {"items": []}, "_meta": {"correlation_id": "abc"}}
    )
    assert success.success is True
    assert success.data == {"items": []}
    assert success.correlation_id == "abc"

    failure = engine.handle_response(
        {
            "isError": True,
            "error": {"code": "TIMEOUT", "message": "slow", "retryable": True},
        }
    )
    assert failure.success is False
    assert failure.error_code == "TIMEOUT"
    assert failure.retryable is True


def test_empty_success_is_not_reinterpreted_as_failure() -> None:
    engine = load_engine()
    result = engine.handle_response({"success": True, "data": []})
    assert engine.is_meaningful_empty_success(result)


def test_batch_preference_preserves_policy_and_verification() -> None:
    engine = load_engine()
    assert engine.prefer_batch_tool(
        3,
        batch_available=True,
        preserves_policy_boundaries=True,
        preserves_verification=True,
    )
    assert not engine.prefer_batch_tool(
        3,
        batch_available=True,
        preserves_policy_boundaries=False,
        preserves_verification=True,
    )


def test_tool_selection_chooses_narrowest_compatible_contract() -> None:
    engine = load_engine()
    tools = [
        {"name": "wide", "capabilities": ["search", "read", "write"]},
        {"name": "read", "capabilities": ["search", "read"]},
        {"name": "batch-read", "capabilities": ["search", "read"], "batch": True},
    ]
    assert engine.select_efficient_tool(
        tools,
        required_capabilities=["search", "read"],
        prefer_batch=True,
    )["name"] == "batch-read"


def test_initial_detail_parameters_choose_summary_mode() -> None:
    engine = load_engine()
    schema = {"properties": {"detail_level": {"enum": ["full", "summary"]}}}
    assert engine.choose_initial_detail_params(schema) == {"detail_level": "summary"}
    assert engine.choose_initial_detail_params({"properties": {"compact": {"type": "boolean"}}}) == {"compact": True}


def test_pagination_stops_on_outcome_or_limit_and_uses_tokens() -> None:
    engine = load_engine()
    assert not engine.get_pagination_decision(
        {"next_cursor": "x"}, outcome_satisfied=True, pages_seen=1, max_pages=5
    ).continue_paging
    assert not engine.get_pagination_decision(
        {"next_cursor": "x"}, outcome_satisfied=False, pages_seen=5, max_pages=5
    ).continue_paging
    decision = engine.get_pagination_decision(
        {"next_cursor": "x"}, outcome_satisfied=False, pages_seen=1, max_pages=5
    )
    assert decision.continue_paging is True
    assert decision.cursor == "x"

"""Tests for MCP consumer efficiency, fallback, pagination, and safety.

Level 4A: Token-aware invocation, progressive disclosure, batch preference.
Level 5A: L1 fallback, DANGEROUS safety, retry conflicts, negative capability.
"""

from tools.decision_engine import (
    evaluate_decision,
    should_retry,
    requires_user_confirmation,
    infer_capability_profile,
    prefer_batch_tool,
    select_efficient_tool,
    choose_initial_detail_params,
    get_pagination_decision,
    is_meaningful_empty_success,
    PaginationDecision,
    get_retry_decision,
    get_http_error_strategy,
)


# ── Section 1: Decision Safety (Critical fix verification) ────────────


class TestDangerousNeverInvoke:
    """DANGEROUS must not be invoke-able through any generic intent."""

    def test_dangerous_general_is_reject(self):
        assert evaluate_decision("DANGEROUS", False, "general") == "reject"

    def test_dangerous_any_is_reject(self):
        assert evaluate_decision("DANGEROUS", False, "any") == "reject"

    def test_dangerous_not_explicit_is_reject(self):
        assert evaluate_decision("DANGEROUS", False, "not_explicit") == "reject"

    def test_dangerous_with_confirmation_general_is_reject(self):
        assert evaluate_decision("DANGEROUS", True, "general") == "reject"

    def test_dangerous_with_confirmation_any_is_reject(self):
        assert evaluate_decision("DANGEROUS", True, "any") == "reject"

    def test_dangerous_with_confirmation_not_explicit_is_reject(self):
        assert evaluate_decision("DANGEROUS", True, "not_explicit") == "reject"

    def test_dangerous_explicit_by_name_is_confirm_then_invoke(self):
        assert (
            evaluate_decision("DANGEROUS", False, "explicit_by_name")
            == "confirm_then_invoke"
        )

    def test_dangerous_explicit_by_name_with_confirm_is_confirm_then_invoke(self):
        assert (
            evaluate_decision("DANGEROUS", True, "explicit_by_name")
            == "confirm_then_invoke"
        )


class TestUnknownRiskDefer:
    """Unknown risk values must never default to invoke."""

    def test_unknown_risk_false_confirm(self):
        assert evaluate_decision("NEW_UNKNOWN_RISK", False, "any") == "defer"

    def test_unknown_risk_true_confirm(self):
        assert evaluate_decision("NEW_UNKNOWN_RISK", True, "any") == "defer"

    def test_empty_risk_defer(self):
        assert evaluate_decision("", False, "any") == "defer"

    def test_malformed_risk_defer(self):
        assert evaluate_decision("rEaD", False, "any") == "defer"


class TestSensitivePolicy:
    """SENSITIVE requires_confirmation must match the policy table."""

    def test_sensitive_no_confirmation_is_invoke(self):
        assert evaluate_decision("SENSITIVE", False, "any") == "invoke"

    def test_sensitive_with_confirmation_is_confirm(self):
        assert evaluate_decision("SENSITIVE", True, "any") == "confirm_then_invoke"


class TestDangerousConfirmationGate:
    """requires_user_confirmation must block DANGEROUS unless explicit_by_name."""

    def test_dangerous_explicit_is_required(self):
        result = requires_user_confirmation(
            {"risk": "DANGEROUS", "name": "run_cmd"}, "explicit_by_name", False
        )
        assert result.required is True

    def test_dangerous_general_is_not_required(self):
        result = requires_user_confirmation(
            {"risk": "DANGEROUS", "name": "run_cmd"}, "general", False
        )
        assert result.required is False
        assert "rejected" in result.message.lower()

    def test_dangerous_any_is_not_required(self):
        result = requires_user_confirmation(
            {"risk": "DANGEROUS", "name": "run_cmd"}, "any", False
        )
        assert result.required is False
        assert "rejected" in result.message.lower()

    def test_dangerous_not_explicit_is_not_required(self):
        result = requires_user_confirmation(
            {"risk": "DANGEROUS", "name": "run_cmd"}, "not_explicit", False
        )
        assert result.required is False
        assert "rejected" in result.message.lower()


# ── Section 2: L1 Fallback Tests ──────────────────────────────────────


class TestCapabilityProfileFallback:
    """Capability profile inference: manifest → risk prefix → safe default."""

    def test_manifest_wins_over_docstring(self):
        profile = infer_capability_profile(
            manifest={"risk": "WRITE", "retryable": True},
            docstring="[READ] Lists entities.",
        )
        assert profile["risk"] == "WRITE"

    def test_risk_prefix_fallback(self):
        profile = infer_capability_profile(
            manifest=None,
            docstring="[READ] Lists entities.",
        )
        assert profile["risk"] == "READ"

    def test_write_prefix_fallback(self):
        profile = infer_capability_profile(
            manifest=None,
            docstring="[WRITE] Updates config.",
        )
        assert profile["risk"] == "WRITE"

    def test_destructive_prefix_fallback(self):
        profile = infer_capability_profile(
            manifest=None,
            docstring="[DESTRUCTIVE] Factory reset.",
        )
        assert profile["risk"] == "DESTRUCTIVE"

    def test_dangerous_prefix_fallback(self):
        profile = infer_capability_profile(
            manifest=None,
            docstring="[DANGEROUS] Execute command.",
        )
        assert profile["risk"] == "DANGEROUS"

    def test_sensitive_prefix_fallback(self):
        profile = infer_capability_profile(
            manifest=None,
            docstring="[SENSITIVE] Get credentials.",
        )
        assert profile["risk"] == "SENSITIVE"

    def test_empty_docstring_fallback(self):
        profile = infer_capability_profile(manifest=None, docstring=None)
        assert profile["risk"] == "READ"

    def test_no_prefix_fallback(self):
        profile = infer_capability_profile(
            manifest=None,
            docstring="Lists entities.",
        )
        assert profile["risk"] == "READ"

    def test_manifest_none_param(self):
        profile = infer_capability_profile(manifest=None)
        assert profile["risk"] == "READ"

    def test_manifest_with_missing_fields_gets_defaults(self):
        profile = infer_capability_profile(manifest={"risk": "WRITE"})
        assert profile["risk"] == "WRITE"
        assert profile["retryable"] is False
        assert profile["concurrent_safe"] is False


# ── Section 3: Retry Conflict Tests ───────────────────────────────────


class TestRetryConflicts:
    """Retry requires agreement from manifest AND error response AND matrix."""

    def test_manifest_blocks_retry(self):
        assert (
            should_retry("TIMEOUT", {"retryable": False}, error_retryable=True) is False
        )

    def test_error_blocks_retry(self):
        assert (
            should_retry("TIMEOUT", {"retryable": True}, error_retryable=False) is False
        )

    def test_both_block_retry(self):
        assert (
            should_retry("TIMEOUT", {"retryable": False}, error_retryable=False)
            is False
        )

    def test_both_allow_retry(self):
        assert (
            should_retry("TIMEOUT", {"retryable": True}, error_retryable=True) is True
        )

    def test_auth_failed_never_retries(self):
        assert (
            should_retry("AUTH_FAILED", {"retryable": True}, error_retryable=True)
            is False
        )

    def test_no_manifest_retries_timeout(self):
        assert should_retry("TIMEOUT", None, None) is True

    def test_no_error_context_retries_timeout(self):
        assert should_retry("TIMEOUT", {"retryable": True}, None) is True


# ── Section 4: Efficiency Tests ───────────────────────────────────────


class TestBatchPreference:
    """Batch/composite tools preferred over N individual calls."""

    def test_batch_preferred_over_individual(self):
        tools = [
            {"name": "get_entity", "manifest": {"risk": "READ"}},
            {"name": "get_entities_batch", "manifest": {"risk": "READ"}},
        ]
        result = prefer_batch_tool(tools, "get_entity", repeated_count=20)
        assert result is not None
        assert result["name"] == "get_entities_batch"

    def test_single_call_no_batch_needed(self):
        tools = [
            {"name": "get_entity", "manifest": {"risk": "READ"}},
            {"name": "get_entities_batch", "manifest": {"risk": "READ"}},
        ]
        result = prefer_batch_tool(tools, "get_entity", repeated_count=1)
        assert result is None

    def test_no_batch_when_individual_is_write(self):
        tools = [
            {"name": "delete_entity", "manifest": {"risk": "DESTRUCTIVE"}},
            {"name": "delete_entities_batch", "manifest": {"risk": "READ"}},
        ]
        result = prefer_batch_tool(tools, "delete_entity", repeated_count=10)
        assert result is None

    def test_batch_tool_must_be_read(self):
        tools = [
            {"name": "get_entity", "manifest": {"risk": "READ"}},
            {"name": "delete_entities_batch", "manifest": {"risk": "DESTRUCTIVE"}},
        ]
        result = prefer_batch_tool(tools, "get_entity", repeated_count=10)
        assert result is None

    def test_batch_hint_matched(self):
        tools = [
            {"name": "get_entity", "manifest": {"risk": "READ"}},
            {
                "name": "diagnose_system_health",
                "manifest": {"risk": "READ", "latency": "fast"},
            },
        ]
        result = prefer_batch_tool(tools, "get_entity", repeated_count=50)
        assert result is not None
        assert result["name"] == "diagnose_system_health"

    def test_summary_variant_preferred(self):
        tools = [
            {"name": "get_entity", "manifest": {"risk": "READ"}},
            {
                "name": "get_summary_overview",
                "manifest": {"risk": "READ", "latency": "fast"},
            },
        ]
        result = prefer_batch_tool(tools, "get_entity", repeated_count=10)
        assert result is not None
        assert result["name"] == "get_summary_overview"


class TestEfficientToolSelection:
    """select_efficient_tool chooses the most efficient tool for a task."""

    def test_discovery_phase_prefers_summary(self):
        tools = [
            {"name": "list_entities", "manifest": {"risk": "READ", "latency": "slow"}},
            {
                "name": "get_system_overview",
                "manifest": {"risk": "READ", "latency": "fast"},
            },
            {"name": "get_entity", "manifest": {"risk": "READ", "latency": "instant"}},
        ]
        result = select_efficient_tool(tools, {"phase": "discovery"})
        assert result is not None
        assert result["name"] == "get_system_overview"

    def test_discovery_skips_non_read(self):
        tools = [
            {"name": "set_config", "manifest": {"risk": "WRITE", "latency": "fast"}},
            {"name": "get_summary", "manifest": {"risk": "READ", "latency": "fast"}},
        ]
        result = select_efficient_tool(tools, {"phase": "discovery"})
        assert result is not None
        assert result["name"] == "get_summary"

    def test_repeated_read_prefers_batch(self):
        tools = [
            {"name": "get_entity", "manifest": {"risk": "READ"}},
            {"name": "get_entities_batch", "manifest": {"risk": "READ"}},
        ]
        result = select_efficient_tool(
            tools, {"repeated_count": 20, "individual_tool_name": "get_entity"}
        )
        assert result is not None
        assert result["name"] == "get_entities_batch"

    def test_no_task_returns_none(self):
        result = select_efficient_tool(
            [{"name": "tool", "manifest": {"risk": "READ"}}], None
        )
        assert result is None


class TestInitialDetailParams:
    """Initial discovery should use minimal parameters."""

    def test_detail_level_minimal(self):
        params = choose_initial_detail_params(
            {"detail_level": None, "compact": None, "limit": None}
        )
        assert params["detail_level"] == "minimal"
        assert params["compact"] is True
        assert params.get("limit") == 50

    def test_user_overrides_not_overwritten(self):
        params = choose_initial_detail_params(
            {"detail_level": None, "limit": None},
            user_overrides={"detail_level": "full", "limit": 500},
        )
        assert params["detail_level"] == "full"
        assert params.get("limit") == 500

    def test_only_known_params_defaulted(self):
        params = choose_initial_detail_params(
            {"custom_param": None, "detail_level": None}
        )
        assert params["detail_level"] == "minimal"
        assert "custom_param" not in params

    def test_empty_schema_defaults(self):
        params = choose_initial_detail_params(None)
        assert params["detail_level"] == "minimal"
        assert params["compact"] is True
        assert params["include_code"] is False


# ── Section 5: Pagination Tests ───────────────────────────────────────


class TestPaginationAwareness:
    """Pagination markers must be respected."""

    def test_has_more_true_continue(self):
        decision = get_pagination_decision(
            {"success": True, "data": [], "has_more": True}
        )
        assert decision == PaginationDecision.CONTINUE_PAGINATION

    def test_has_more_true_scope_satisfied(self):
        decision = get_pagination_decision(
            {"success": True, "data": [], "has_more": True},
            desired_scope_satisfied=True,
        )
        assert decision == PaginationDecision.PARTIAL_SCOPE_SATISFIED

    def test_has_more_false_complete(self):
        decision = get_pagination_decision(
            {"success": True, "data": [], "has_more": False}
        )
        assert decision == PaginationDecision.COMPLETE

    def test_no_markers_complete(self):
        decision = get_pagination_decision({"success": True, "data": [1, 2, 3]})
        assert decision == PaginationDecision.COMPLETE

    def test_next_offset_present_continue(self):
        decision = get_pagination_decision(
            {"success": True, "data": [], "next_offset": 200}
        )
        assert decision == PaginationDecision.CONTINUE_PAGINATION

    def test_next_cursor_present_continue(self):
        decision = get_pagination_decision(
            {"success": True, "data": [], "next_cursor": "abc"}
        )
        assert decision == PaginationDecision.CONTINUE_PAGINATION

    def test_has_more_false_with_offset_is_complete(self):
        decision = get_pagination_decision(
            {
                "success": True,
                "data": [],
                "has_more": False,
                "offset": 200,
                "limit": 100,
            }
        )
        assert decision == PaginationDecision.COMPLETE


# ── Section 6: Negative Capability Tests ──────────────────────────────


class TestNegativeCapability:
    """Empty successful results are meaningful, not errors."""

    def test_empty_list_success(self):
        assert is_meaningful_empty_success({"success": True, "data": []}) is True

    def test_empty_dict_success(self):
        assert is_meaningful_empty_success({"success": True, "data": {}}) is True

    def test_null_data_success(self):
        assert is_meaningful_empty_success({"success": True, "data": None}) is True

    def test_zero_count_success(self):
        assert is_meaningful_empty_success({"success": True, "data": 0}) is True

    def test_count_zero_object_success(self):
        assert (
            is_meaningful_empty_success({"success": True, "data": {"count": 0}}) is True
        )

    def test_non_empty_list_is_not_empty(self):
        assert (
            is_meaningful_empty_success({"success": True, "data": [1, 2, 3]}) is False
        )

    def test_non_empty_dict_is_not_empty(self):
        assert (
            is_meaningful_empty_success({"success": True, "data": {"key": "val"}})
            is False
        )

    def test_failure_is_not_meaningful_empty(self):
        assert is_meaningful_empty_success({"success": False, "data": []}) is False

    def test_missing_success_is_not_meaningful_empty(self):
        assert is_meaningful_empty_success({"data": []}) is False

    def test_success_true_with_positive_count(self):
        assert is_meaningful_empty_success({"success": True, "data": 5}) is False


# ── Section 7: Regression Tests ───────────────────────────────────────


class TestGetRetryDecisionWithErrorRetryable:
    """get_retry_decision must block retry when error.retryable is False."""

    def test_error_retryable_false_blocks_retry(self):
        decision = get_retry_decision(
            "TIMEOUT",
            {"retryable": True},
            error_retryable=False,
        )
        assert decision.should_retry is False

    def test_error_retryable_true_allows_retry(self):
        decision = get_retry_decision(
            "TIMEOUT",
            {"retryable": True},
            error_retryable=True,
        )
        assert decision.should_retry is True

    def test_error_retryable_none_falls_through(self):
        decision = get_retry_decision(
            "TIMEOUT",
            {"retryable": True},
            error_retryable=None,
        )
        assert decision.should_retry is True

    def test_manifest_false_overrides_error_true(self):
        decision = get_retry_decision(
            "TIMEOUT",
            {"retryable": False},
            error_retryable=True,
        )
        assert decision.should_retry is False

    def test_both_block(self):
        decision = get_retry_decision(
            "AUTH_FAILED",
            {"retryable": False},
            error_retryable=False,
        )
        assert decision.should_retry is False


class TestHttpErrorStrategy:
    """HTTP error strategy distinguishes 4xx from 5xx."""

    def test_5xx_retry_once(self):
        strategy = get_http_error_strategy(500)
        assert strategy.retry is True
        assert strategy.max_retries == 1

    def test_502_retry_once(self):
        strategy = get_http_error_strategy(502)
        assert strategy.retry is True

    def test_599_retry_once(self):
        strategy = get_http_error_strategy(599)
        assert strategy.retry is True

    def test_4xx_no_retry(self):
        for code in (400, 401, 403, 404, 429, 499):
            strategy = get_http_error_strategy(code)
            assert strategy.retry is False, f"{code} should not be retryable"

    def test_manifest_blocks_5xx_retry(self):
        strategy = get_http_error_strategy(500, {"retryable": False})
        assert strategy.retry is False

    def test_3xx_no_retry(self):
        strategy = get_http_error_strategy(302)
        assert strategy.retry is False


class TestPaginationMeta:
    """Pagination markers inside _meta must be detected."""

    def test_has_more_in_meta(self):
        decision = get_pagination_decision(
            {
                "success": True,
                "data": [],
                "_meta": {"has_more": True, "next_cursor": "abc"},
            }
        )
        assert decision == PaginationDecision.CONTINUE_PAGINATION

    def test_next_offset_in_meta(self):
        decision = get_pagination_decision(
            {
                "success": True,
                "data": [],
                "_meta": {"next_offset": 200},
            }
        )
        assert decision == PaginationDecision.CONTINUE_PAGINATION

    def test_meta_has_more_false_complete(self):
        decision = get_pagination_decision(
            {
                "success": True,
                "data": [1, 2, 3],
                "_meta": {"has_more": False, "total": 3},
            }
        )
        assert decision == PaginationDecision.COMPLETE

    def test_meta_overrides_nothing_when_no_markers(self):
        decision = get_pagination_decision(
            {
                "success": True,
                "data": [1],
                "_meta": {"request_id": "abc", "duration_ms": 42},
            }
        )
        assert decision == PaginationDecision.COMPLETE

    def test_has_more_in_data_envelope(self):
        decision = get_pagination_decision(
            {
                "success": True,
                "data": {"items": [], "has_more": True, "next_cursor": "abc"},
            }
        )
        assert decision == PaginationDecision.CONTINUE_PAGINATION

    def test_partial_page_does_not_imply_missing_item(self):
        decision = get_pagination_decision(
            {
                "success": True,
                "data": {"items": [{"id": "a"}], "has_more": True},
            }
        )
        assert decision == PaginationDecision.CONTINUE_PAGINATION


class TestDetailParamsNoEntityIdSuppression:
    """include_entity_id must NOT be defaulted to False."""

    def test_include_entity_id_not_in_defaults(self):
        params = choose_initial_detail_params(
            {"detail_level": None, "include_entity_id": None}
        )
        assert "include_entity_id" not in params

    def test_user_can_still_set_include_entity_id(self):
        params = choose_initial_detail_params(
            {"detail_level": None, "include_entity_id": None},
            user_overrides={"include_entity_id": True},
        )
        assert params["include_entity_id"] is True

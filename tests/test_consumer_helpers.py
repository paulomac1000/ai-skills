"""Tests for skills/mcp-server-consumer/tools/decision_engine.py.

Level 3: Helper function tests — deterministic, no I/O, no external dependencies.
"""

from tools.decision_engine import (
    ErrorAction,
    ErrorStrategy,
    handle_response,
    evaluate_decision,
    get_error_strategy,
    requires_user_confirmation,
    get_retry_decision,
    compute_backoff_delay,
    infer_manifest_safe_defaults,
    should_retry,
    is_success,
    get_error_code,
    get_request_id,
    parse_manifest,
    classify_risk,
    select_tool_for_task,
)


class TestHandleResponse:
    def test_success_response(self):
        result = handle_response({"success": True, "data": {"key": "value"}})
        assert result.success is True
        assert result.data == {"key": "value"}

    def test_success_with_meta(self):
        result = handle_response(
            {
                "success": True,
                "data": {"status": "ok"},
                "_meta": {"request_id": "abc-123", "duration_ms": 42},
            }
        )
        assert result.success is True
        assert result.meta["request_id"] == "abc-123"

    def test_failure_string_error(self):
        result = handle_response({"success": False, "error": "Something went wrong"})
        assert result.success is False
        assert result.error_code == "UNKNOWN"
        assert result.error_message == "Something went wrong"

    def test_failure_structured_error(self):
        result = handle_response(
            {
                "success": False,
                "error": {
                    "code": "TIMEOUT",
                    "message": "Operation timed out",
                    "retryable": True,
                    "suggestion": "Retry with a longer timeout",
                },
            }
        )
        assert result.success is False
        assert result.error_code == "TIMEOUT"
        assert result.error_message == "Operation timed out"
        assert result.error_retryable is True
        assert result.error_suggestion == "Retry with a longer timeout"

    def test_missing_success_field(self):
        result = handle_response({"data": "no success field"})
        assert result.success is False
        assert result.is_missing_success is True
        assert result.error_code == "MISSING_SUCCESS_FIELD"

    def test_success_false_unknown_error(self):
        result = handle_response({"success": False, "error": None})
        assert result.success is False
        assert result.error_code == "UNKNOWN"


class TestEvaluateDecision:
    def test_read_no_confirmation(self):
        assert evaluate_decision("READ", False, "any") == "invoke"

    def test_read_with_confirmation(self):
        assert evaluate_decision("READ", True, "any") == "confirm_then_invoke"

    def test_write_general_intent(self):
        assert evaluate_decision("WRITE", False, "general") == "confirm_then_invoke"

    def test_write_confirmed_workflow(self):
        assert evaluate_decision("WRITE", False, "confirmed_workflow") == "invoke"

    def test_write_with_confirmation(self):
        assert evaluate_decision("WRITE", True, "any") == "confirm_then_invoke"

    def test_destructive_always_confirm(self):
        assert evaluate_decision("DESTRUCTIVE", False, "any") == "confirm_then_invoke"
        assert evaluate_decision("DESTRUCTIVE", True, "any") == "confirm_then_invoke"

    def test_dangerous_not_explicit(self):
        assert evaluate_decision("DANGEROUS", False, "not_explicit") == "reject"
        assert evaluate_decision("DANGEROUS", True, "not_explicit") == "reject"

    def test_dangerous_explicit_by_name(self):
        assert (
            evaluate_decision("DANGEROUS", False, "explicit_by_name")
            == "confirm_then_invoke"
        )
        assert (
            evaluate_decision("DANGEROUS", True, "explicit_by_name")
            == "confirm_then_invoke"
        )

    def test_sensitive_no_confirmation(self):
        assert evaluate_decision("SENSITIVE", False, "any") == "invoke"

    def test_sensitive_with_confirmation(self):
        assert evaluate_decision("SENSITIVE", True, "any") == "confirm_then_invoke"


class TestErrorStrategy:
    def test_timeout_is_retryable(self):
        strategy = get_error_strategy("TIMEOUT")
        assert strategy.retry is True
        assert strategy.max_retries == 3

    def test_auth_failed_is_not_retryable(self):
        strategy = get_error_strategy("AUTH_FAILED")
        assert strategy.retry is False
        assert strategy.max_retries == 0

    def test_manifest_overrides_retryable(self):
        strategy = get_error_strategy("TIMEOUT", {"retryable": False})
        assert strategy.retry is False

    def test_unknown_code_defaults_to_escalate(self):
        strategy = get_error_strategy("NEW_ERROR_CODE_XYZ")
        assert strategy.retry is False
        assert strategy.action == ErrorAction.ESCALATE

    def test_all_13_error_codes_have_strategies(self):
        all_codes = [
            "TIMEOUT",
            "DEVICE_OFFLINE",
            "AUTH_FAILED",
            "INVALID_PARAM",
            "UNSUPPORTED",
            "DEPENDENCY_MISSING",
            "INTERNAL_ERROR",
            "HTTP_ERROR",
            "DEVICE_NOT_FOUND",
            "VALIDATION_FAILED",
            "RESOURCE_LOCKED",
            "RESOURCE_ALREADY_EXISTS",
            "RESOURCE_NOT_FOUND",
        ]
        for code in all_codes:
            strategy = get_error_strategy(code)
            assert isinstance(strategy, ErrorStrategy), f"No strategy for {code}"

    def test_manifest_none_does_not_crash(self):
        strategy = get_error_strategy("TIMEOUT", None)
        assert strategy.retry is True

    def test_resource_locked_is_retry_reread(self):
        strategy = get_error_strategy("RESOURCE_LOCKED")
        assert strategy.action == ErrorAction.RETRY_REREAD


class TestConfirmationGate:
    def test_read_no_confirmation(self):
        result = requires_user_confirmation(
            {"risk": "READ", "requires_confirmation": False, "name": "get_status"},
            "any",
            False,
        )
        assert result.required is False

    def test_read_with_confirmation_overrides(self):
        result = requires_user_confirmation(
            {"risk": "READ", "requires_confirmation": True, "name": "get_status"},
            "any",
            False,
        )
        assert result.required is True

    def test_write_requires_confirmation_first_time(self):
        result = requires_user_confirmation(
            {"risk": "WRITE", "requires_confirmation": False, "name": "set_config"},
            "general",
            False,
        )
        assert result.required is True

    def test_write_no_confirmation_in_confirmed_workflow(self):
        result = requires_user_confirmation(
            {"risk": "WRITE", "requires_confirmation": False, "name": "set_config"},
            "general",
            True,
        )
        assert result.required is False

    def test_destructive_always_requires_confirmation(self):
        result = requires_user_confirmation(
            {
                "risk": "DESTRUCTIVE",
                "name": "factory_reset",
                "impact": "service_outage",
            },
            "any",
            True,
        )
        assert result.required is True
        assert "DESTRUCTIVE" in result.message

    def test_dangerous_rejected_when_not_explicit(self):
        result = requires_user_confirmation(
            {"risk": "DANGEROUS", "name": "execute_command"},
            "not_explicit",
            False,
        )
        assert result.required is False
        assert "rejected" in result.message.lower()
        assert "rejected" in result.message.lower()

    def test_dangerous_confirmed_when_explicit(self):
        result = requires_user_confirmation(
            {"risk": "DANGEROUS", "name": "execute_command"},
            "explicit_by_name",
            False,
        )
        assert result.required is True
        assert "DANGEROUS" in result.message

    def test_unknown_risk_requires_safe_gate(self):
        result = requires_user_confirmation(
            {"risk": "UNKNOWN_NEW_RISK", "name": "new_tool"},
            "any",
            False,
        )
        assert result.required is True
        assert "unresolved" in result.message.lower()


class TestRetryDecision:
    def test_retry_timeout(self):
        decision = get_retry_decision("TIMEOUT", {"retryable": True}, current_attempt=0)
        assert decision.should_retry is True
        assert decision.max_retries == 3

    def test_no_retry_auth_failed(self):
        decision = get_retry_decision("AUTH_FAILED", {"retryable": True})
        assert decision.should_retry is False

    def test_manifest_blocks_retry(self):
        decision = get_retry_decision("TIMEOUT", {"retryable": False})
        assert decision.should_retry is False

    def test_max_retries_exhausted(self):
        decision = get_retry_decision("TIMEOUT", {"retryable": True}, current_attempt=3)
        assert decision.should_retry is False

    def test_internal_error_one_retry(self):
        decision = get_retry_decision(
            "INTERNAL_ERROR", {"retryable": True}, current_attempt=0
        )
        assert decision.should_retry is True
        assert decision.max_retries == 1

    def test_internal_error_exhausted(self):
        decision = get_retry_decision(
            "INTERNAL_ERROR", {"retryable": True}, current_attempt=1
        )
        assert decision.should_retry is False

    def test_unknown_code_no_retry(self):
        decision = get_retry_decision("UNKNOWN_CODE_XYZ")
        assert decision.should_retry is False


class TestBackoffDelay:
    def test_attempt_0(self):
        assert compute_backoff_delay(0) == 1.0

    def test_attempt_1(self):
        assert compute_backoff_delay(1) == 2.0

    def test_attempt_2(self):
        assert compute_backoff_delay(2) == 4.0

    def test_attempt_3_capped(self):
        assert compute_backoff_delay(3) == 8.0

    def test_attempt_10_capped(self):
        assert compute_backoff_delay(10) == 8.0


class TestSafeDefaults:
    def test_none_manifest(self):
        result = infer_manifest_safe_defaults(None)
        assert result["risk"] == "READ"
        assert result["retryable"] is False
        assert result["requires_confirmation"] is False
        assert result["concurrent_safe"] is False

    def test_partial_manifest(self):
        result = infer_manifest_safe_defaults({"risk": "WRITE"})
        assert result["risk"] == "WRITE"
        assert result["retryable"] is False
        assert result["requires_confirmation"] is False

    def test_empty_manifest(self):
        result = infer_manifest_safe_defaults({})
        assert result["risk"] == "READ"
        assert result["retryable"] is False

    def test_null_value_preserved_as_default(self):
        result = infer_manifest_safe_defaults({"risk": None})
        assert result["risk"] == "READ"


class TestCompoundErrorChecking:
    def test_both_allow_retry(self):
        assert (
            should_retry("TIMEOUT", {"retryable": True}, error_retryable=True) is True
        )

    def test_manifest_blocks(self):
        assert (
            should_retry("TIMEOUT", {"retryable": False}, error_retryable=True) is False
        )

    def test_error_blocks(self):
        assert (
            should_retry("TIMEOUT", {"retryable": True}, error_retryable=False) is False
        )

    def test_both_block(self):
        assert (
            should_retry("TIMEOUT", {"retryable": False}, error_retryable=False)
            is False
        )

    def test_auth_failed_never_retries(self):
        assert (
            should_retry("AUTH_FAILED", {"retryable": True}, error_retryable=True)
            is False
        )

    def test_manifest_none(self):
        assert should_retry("TIMEOUT", None, None) is True

    def test_error_retryable_none(self):
        assert should_retry("TIMEOUT", {"retryable": True}, None) is True


class TestConvenienceFunctions:
    def test_is_success_true(self):
        assert is_success({"success": True}) is True

    def test_is_success_false(self):
        assert is_success({"success": False}) is False

    def test_is_success_missing(self):
        assert is_success({}) is False

    def test_get_error_code_structured(self):
        assert get_error_code({"error": {"code": "TIMEOUT"}}) == "TIMEOUT"

    def test_get_error_code_string(self):
        assert get_error_code({"error": "boom"}) == "UNKNOWN"

    def test_get_error_code_none(self):
        assert get_error_code({"success": True}) is None

    def test_get_request_id(self):
        assert get_request_id({"_meta": {"request_id": "abc-123"}}) == "abc-123"

    def test_get_request_id_missing(self):
        assert get_request_id({}) is None

    def test_parse_manifest(self):
        result = parse_manifest({"manifest": {"risk": "WRITE", "retryable": True}})
        assert result["risk"] == "WRITE"
        assert result["retryable"] is True

    def test_parse_manifest_no_manifest(self):
        result = parse_manifest({})
        assert result["risk"] == "READ"

    def test_classify_risk(self):
        assert classify_risk({"risk": "DESTRUCTIVE"}) == "DESTRUCTIVE"

    def test_classify_risk_default(self):
        assert classify_risk({}) == "READ"


class TestToolSelection:
    def test_select_diagnose_tool(self):
        tools = [
            {"manifest": {"risk": "WRITE", "latency": "moderate"}},
            {"manifest": {"risk": "READ", "latency": "fast"}},
            {"manifest": {"risk": "READ", "latency": "slow"}},
        ]
        result = select_tool_for_task(tools, "diagnose")
        assert result is not None
        assert result["manifest"]["risk"] == "READ"
        assert result["manifest"]["latency"] == "fast"

    def test_select_destroy_tool(self):
        tools = [
            {"manifest": {"risk": "READ"}},
            {"manifest": {"risk": "DESTRUCTIVE"}},
        ]
        result = select_tool_for_task(tools, "destroy")
        assert result is not None
        assert result["manifest"]["risk"] == "DESTRUCTIVE"

    def test_select_unknown_task(self):
        result = select_tool_for_task([], "unknown_task")
        assert result is None

    def test_select_no_match(self):
        tools = [{"manifest": {"risk": "READ", "latency": "slow"}}]
        result = select_tool_for_task(tools, "diagnose")
        assert result is None

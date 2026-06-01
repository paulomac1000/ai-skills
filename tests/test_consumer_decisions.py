"""Tests for MCP consumer decision policy and contract obedience.

Level 4A: Decision policy — every row in the normative table is tested.
Level 5A: Contract obedience — manifest + response + context → expected decision.

These are the primary behavioral tests. They verify that the decision engine
produces the correct action for every defined combination of inputs.
"""

import pytest
from dataclasses import dataclass

from tools.decision_engine import (
    evaluate_decision,
    get_error_strategy,
    handle_response,
    requires_user_confirmation,
    should_retry,
)


# ── Level 4A: Normative Decision Policy Table ────────────────────────
#
# Every row from Canonical Template C6 must produce the expected decision.

DECISION_TABLE = [
    # (risk, requires_confirmation, user_intent, expected_decision)
    ("READ", False, "any", "invoke"),
    ("READ", True, "any", "confirm_then_invoke"),
    ("WRITE", False, "general", "confirm_then_invoke"),
    ("WRITE", False, "confirmed_workflow", "invoke"),
    ("WRITE", False, "any", "confirm_then_invoke"),
    ("WRITE", True, "confirmed_workflow", "confirm_then_invoke"),
    ("WRITE", True, "general", "confirm_then_invoke"),
    ("WRITE", True, "any", "confirm_then_invoke"),
    ("DESTRUCTIVE", False, "any", "confirm_then_invoke"),
    ("DESTRUCTIVE", True, "any", "confirm_then_invoke"),
    ("DANGEROUS", False, "explicit_by_name", "confirm_then_invoke"),
    ("DANGEROUS", True, "explicit_by_name", "confirm_then_invoke"),
    ("DANGEROUS", False, "general", "reject"),
    ("DANGEROUS", True, "general", "reject"),
    ("DANGEROUS", False, "not_explicit", "reject"),
    ("DANGEROUS", True, "not_explicit", "reject"),
    ("DANGEROUS", False, "any", "reject"),
    ("DANGEROUS", True, "any", "reject"),
    ("SENSITIVE", False, "any", "invoke"),
    ("SENSITIVE", True, "any", "confirm_then_invoke"),
    ("UNKNOWN_NEW_RISK", False, "any", "defer"),
]


@pytest.mark.parametrize(
    "risk,requires_confirmation,user_intent,expected", DECISION_TABLE
)
def test_decision_policy_row(risk, requires_confirmation, user_intent, expected):
    """Level 4A: Every row in the normative decision policy table produces
    the expected decision."""
    result = evaluate_decision(risk, requires_confirmation, user_intent)
    assert result == expected, (
        f"Decision mismatch: risk={risk}, requires_confirmation={requires_confirmation}, "
        f"user_intent={user_intent} → expected '{expected}', got '{result}'"
    )


# ── Level 4A: Error Strategy Matrix Coverage ─────────────────────────
#
# Every error code from the Error Strategy Matrix has a defined strategy.

ERROR_CODES = [
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

RETRYABLE_CODES = {"TIMEOUT", "DEVICE_OFFLINE", "RESOURCE_LOCKED"}
ONCE_CODES = {"INTERNAL_ERROR"}
# HTTP_ERROR is classified as non-retryable in the base error strategy matrix
# (all HTTP errors escalate by default). 5xx conditional retry is handled by
# the separate get_http_error_strategy() function, not by this matrix.
NON_RETRYABLE_CODES = [
    c for c in ERROR_CODES if c not in RETRYABLE_CODES and c not in ONCE_CODES
]


@pytest.mark.parametrize("error_code", ERROR_CODES)
def test_error_code_has_strategy(error_code):
    """Level 4A: Every error code has a defined strategy."""
    strategy = get_error_strategy(error_code)
    assert strategy is not None


@pytest.mark.parametrize("error_code", RETRYABLE_CODES)
def test_retryable_codes_allow_retry(error_code):
    """Level 4A: Retryable error codes permit retry (subject to manifest)."""
    strategy = get_error_strategy(error_code)
    assert strategy.retry is True, f"{error_code} should be retryable"


@pytest.mark.parametrize("error_code", NON_RETRYABLE_CODES)
def test_non_retryable_codes_disallow_retry(error_code):
    """Level 4A: Non-retryable error codes disallow retry."""
    strategy = get_error_strategy(error_code)
    assert strategy.retry is False, f"{error_code} should NOT be retryable"


@pytest.mark.parametrize("error_code", ONCE_CODES)
def test_once_codes_allow_one_retry(error_code):
    """Level 4A: Oonce-only codes allow exactly 1 retry."""
    strategy = get_error_strategy(error_code)
    assert strategy.max_retries == 1, f"{error_code} should have max_retries=1"


# ── Level 5A: Contract Obedience Test Cases ──────────────────────────
#
# Scenario-based tests: manifest + response + context → expected behavior.


@dataclass
class ContractScenario:
    """A test case for contract obedience: given these inputs, what should happen?"""

    name: str
    manifest: dict
    response: dict | None
    expected_decision: str
    expected_should_retry: bool
    expected_confirmation_required: bool
    description: str


CONTRACT_SCENARIOS = [
    ContractScenario(
        name="read_tool_success",
        manifest={"risk": "READ", "retryable": True, "name": "get_status"},
        response={"success": True, "data": {"status": "ok"}},
        expected_decision="invoke",
        expected_should_retry=False,
        expected_confirmation_required=False,
        description="READ tool with success response — invoke freely, no retry needed, no confirmation",
    ),
    ContractScenario(
        name="read_tool_timeout",
        manifest={"risk": "READ", "retryable": True, "name": "get_status"},
        response={
            "success": False,
            "error": {"code": "TIMEOUT", "message": "timeout", "retryable": True},
        },
        expected_decision="invoke",
        expected_should_retry=True,
        expected_confirmation_required=False,
        description="READ tool timeout — should retry, no confirmation needed",
    ),
    ContractScenario(
        name="write_tool_first_invocation",
        manifest={
            "risk": "WRITE",
            "retryable": True,
            "requires_confirmation": True,
            "name": "set_config",
        },
        response={"success": True, "data": {"saved": True}},
        expected_decision="confirm_then_invoke",
        expected_should_retry=False,
        expected_confirmation_required=True,
        description="First WRITE tool in workflow — requires confirmation before invoke",
    ),
    ContractScenario(
        name="destructive_tool_factory_reset",
        manifest={
            "risk": "DESTRUCTIVE",
            "retryable": False,
            "name": "factory_reset",
            "impact": "service_outage",
            "reversible": False,
        },
        response={"success": True, "data": {"status": "resetting"}},
        expected_decision="confirm_then_invoke",
        expected_should_retry=False,
        expected_confirmation_required=True,
        description="DESTRUCTIVE tool always requires confirmation, never retryable",
    ),
    ContractScenario(
        name="dangerous_tool_user_requested",
        manifest={"risk": "DANGEROUS", "name": "execute_command"},
        response={"success": True, "data": {"output": "ok"}},
        expected_decision="confirm_then_invoke",
        expected_should_retry=False,
        expected_confirmation_required=True,
        description="DANGEROUS tool explicitly requested by user — confirm, then invoke",
    ),
    ContractScenario(
        name="dangerous_tool_not_requested",
        manifest={"risk": "DANGEROUS", "name": "execute_command"},
        response=None,
        expected_decision="reject",
        expected_should_retry=False,
        expected_confirmation_required=False,
        description="DANGEROUS tool not explicitly requested — reject",
    ),
    ContractScenario(
        name="write_tool_auth_failed",
        manifest={"risk": "WRITE", "retryable": True, "name": "set_config"},
        response={
            "success": False,
            "error": {
                "code": "AUTH_FAILED",
                "message": "bad token",
                "retryable": False,
            },
        },
        expected_decision="confirm_then_invoke",
        expected_should_retry=False,
        expected_confirmation_required=True,
        description="WRITE tool with AUTH_FAILED — should NOT retry (both matrix AND error.block)",
    ),
    ContractScenario(
        name="write_tool_timeout_manifest_blocks",
        manifest={"risk": "WRITE", "retryable": False, "name": "set_config"},
        response={
            "success": False,
            "error": {"code": "TIMEOUT", "message": "timeout", "retryable": True},
        },
        expected_decision="confirm_then_invoke",
        expected_should_retry=False,
        expected_confirmation_required=True,
        description="TIMEOUT but manifest.retryable=false — retry blocked by manifest",
    ),
    ContractScenario(
        name="sensitive_tool_credentials",
        manifest={"risk": "SENSITIVE", "retryable": True, "name": "get_credentials"},
        response={"success": True, "data": {"token": "secret"}},
        expected_decision="invoke",
        expected_should_retry=False,
        expected_confirmation_required=False,
        description="SENSITIVE tool — invoke freely but data must not be logged",
    ),
    ContractScenario(
        name="resource_locked_retry_reread",
        manifest={"risk": "WRITE", "retryable": True, "name": "update_config"},
        response={
            "success": False,
            "error": {
                "code": "RESOURCE_LOCKED",
                "message": "config_hash mismatch",
                "retryable": True,
            },
        },
        expected_decision="confirm_then_invoke",
        expected_should_retry=True,
        expected_confirmation_required=True,
        description="RESOURCE_LOCKED — should retry after re-reading config",
    ),
]


@pytest.mark.parametrize("scenario", CONTRACT_SCENARIOS, ids=lambda s: s.name)
def test_contract_obedience_retry(scenario):
    """Level 5A: Contract obedience — correct retry decision for every scenario."""
    if scenario.response is not None:
        error_code = None
        error_retryable = None
        error = scenario.response.get("error")
        if isinstance(error, dict):
            error_code = error.get("code", "UNKNOWN")
            error_retryable = error.get("retryable")
        elif scenario.response.get("success") is False:
            error_code = "UNKNOWN"

        if error_code or not scenario.response.get("success", True):
            actual = should_retry(
                error_code or "UNKNOWN",
                scenario.manifest,
                error_retryable,
            )
            assert actual == scenario.expected_should_retry, (
                f"[{scenario.name}] should_retry mismatch: "
                f"expected {scenario.expected_should_retry}, got {actual}"
            )


@pytest.mark.parametrize("scenario", CONTRACT_SCENARIOS, ids=lambda s: s.name)
def test_contract_obedience_decision(scenario):
    """Level 5A: Contract obedience — correct invocation decision for every scenario."""
    manifest = scenario.manifest
    risk = manifest.get("risk", "READ")
    requires_confirm = manifest.get("requires_confirmation", False)

    if scenario.name == "dangerous_tool_user_requested":
        user_intent = "explicit_by_name"
    elif scenario.name == "dangerous_tool_not_requested":
        user_intent = "not_explicit"
    else:
        user_intent = "any"

    actual = evaluate_decision(risk, requires_confirm, user_intent)
    assert actual == scenario.expected_decision, (
        f"[{scenario.name}] decision mismatch: "
        f"expected '{scenario.expected_decision}', got '{actual}'"
    )


@pytest.mark.parametrize("scenario", CONTRACT_SCENARIOS, ids=lambda s: s.name)
def test_contract_obedience_confirmation(scenario):
    """Level 5A: Contract obedience — correct confirmation requirement for every scenario."""
    manifest = scenario.manifest

    if scenario.name == "dangerous_tool_user_requested":
        user_intent = "explicit_by_name"
    elif scenario.name == "dangerous_tool_not_requested":
        user_intent = "not_explicit"
    else:
        user_intent = "any"

    result = requires_user_confirmation(manifest, user_intent, workflow_confirmed=False)
    assert result.required == scenario.expected_confirmation_required, (
        f"[{scenario.name}] confirmation mismatch: "
        f"expected {scenario.expected_confirmation_required}, got {result.required}"
    )


# ── Level 5A: End-to-end scenario chains ─────────────────────────────


def test_workflow_write_then_destructive():
    """A realistic multi-step workflow: scan -> configure -> reboot."""
    configure_manifest = {
        "risk": "WRITE",
        "name": "update_config",
        "requires_confirmation": True,
        "retryable": True,
    }
    reboot_manifest = {
        "risk": "DESTRUCTIVE",
        "name": "reboot_device",
        "reversible": False,
        "retryable": False,
    }

    # Step 1: scan — no confirmation
    assert evaluate_decision("READ", False, "any") == "invoke"

    # Step 2: configure — confirmation required (first WRITE)
    assert evaluate_decision("WRITE", True, "general") == "confirm_then_invoke"
    # After confirmation, within same workflow
    assert (
        evaluate_decision("WRITE", True, "confirmed_workflow") == "confirm_then_invoke"
    )

    # Step 3: reboot — always confirmation required
    assert evaluate_decision("DESTRUCTIVE", False, "any") == "confirm_then_invoke"

    # If configure times out:
    config_error = should_retry("TIMEOUT", configure_manifest, error_retryable=True)
    assert config_error is True

    # If reboot errors — never retry
    reboot_error = should_retry("TIMEOUT", reboot_manifest, error_retryable=True)
    assert reboot_error is False


def test_diagnostic_workflow():
    """A diagnostic workflow: check health → get version → current state."""
    health_manifest = {"risk": "READ", "retryable": True, "latency": "instant"}
    version_manifest = {"risk": "READ", "retryable": True, "latency": "fast"}
    state_manifest = {"risk": "READ", "retryable": True, "latency": "moderate"}

    # All READ tools — invoke freely
    assert evaluate_decision("READ", False, "any") == "invoke"

    # All retryable on timeout
    for m in [health_manifest, version_manifest, state_manifest]:
        assert should_retry("TIMEOUT", m, error_retryable=True) is True


def test_config_workflow_with_rollback():
    """A config workflow: read config -> update -> verify -> (rollback if fail)."""
    update_manifest = {
        "risk": "WRITE",
        "retryable": True,
        "reversible": True,
        "requires_confirmation": True,
    }
    verify_manifest = {"risk": "READ", "retryable": True}

    # read — no confirmation
    assert evaluate_decision("READ", False, "any") == "invoke"

    # update — confirmation required, retryable
    assert evaluate_decision("WRITE", True, "general") == "confirm_then_invoke"
    assert should_retry("TIMEOUT", update_manifest, error_retryable=True) is True

    # update AUTH_FAILED — never retry
    assert should_retry("AUTH_FAILED", update_manifest, error_retryable=True) is False

    # verify — can retry on DEVICE_OFFLINE
    assert should_retry("DEVICE_OFFLINE", verify_manifest, error_retryable=True) is True


# ── Level 5A: Edge Case Tests ─────────────────────────────────────────


def test_success_response_with_error_prose():
    """EDGE_CASE: success: true with error text in data is still a success."""
    from tools.decision_engine import is_success

    response = {"success": True, "data": "Error: something failed"}
    assert is_success(response) is True
    result = handle_response(response)
    assert result.success is True
    assert result.data == "Error: something failed"


def test_mid_workflow_destructive_reclassification():
    """EDGE_CASE: WRITE-confirmed workflow must re-confirm when tool is DESTRUCTIVE.

    A tool reclassified mid-workflow to DESTRUCTIVE must trigger a fresh
    confirmation gate, regardless of prior WRITE scope confirmation.
    """
    assert evaluate_decision("DESTRUCTIVE", False, "any") == "confirm_then_invoke"
    assert evaluate_decision("DESTRUCTIVE", True, "any") == "confirm_then_invoke"
    assert (
        evaluate_decision("DESTRUCTIVE", False, "confirmed_workflow")
        == "confirm_then_invoke"
    )

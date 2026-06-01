"""Canonical decision engine for MCP consumer — reference implementation.

This module implements the decision logic described in
ref.mcp-consumer-standards.md. It is the normative implementation
against which tests measure compliance.

Every function here corresponds to a Canonical Template in the standard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Decision(str, Enum):
    INVOKE = "invoke"
    CONFIRM_THEN_INVOKE = "confirm_then_invoke"
    REJECT = "reject"
    DEFER = "defer"


class ErrorAction(str, Enum):
    RETRY = "retry"
    RETRY_ONCE = "retry_once"
    RETRY_REREAD = "retry_reread"
    ESCALATE = "escalate"


class Risk(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    DESTRUCTIVE = "DESTRUCTIVE"
    DANGEROUS = "DANGEROUS"
    SENSITIVE = "SENSITIVE"


class UserIntent(str, Enum):
    ANY = "any"
    GENERAL = "general"
    CONFIRMED_WORKFLOW = "confirmed_workflow"
    EXPLICIT_BY_NAME = "explicit_by_name"
    NOT_EXPLICIT = "not_explicit"


@dataclass
class ErrorStrategy:
    retry: bool
    max_retries: int
    action: ErrorAction


# ── Canonical Template C6: Decision Policy Table (Complete) ──────────

KNOWN_RISK_VALUES: frozenset[str] = frozenset(
    {"READ", "WRITE", "DESTRUCTIVE", "DANGEROUS", "SENSITIVE"}
)

DECISION_POLICY: list[tuple[str, bool, str, str]] = [
    ("READ", False, "any", "invoke"),
    ("READ", True, "any", "confirm_then_invoke"),
    ("WRITE", False, "confirmed_workflow", "invoke"),
    ("WRITE", False, "general", "confirm_then_invoke"),
    ("WRITE", False, "any", "confirm_then_invoke"),
    ("WRITE", True, "confirmed_workflow", "confirm_then_invoke"),
    ("WRITE", True, "general", "confirm_then_invoke"),
    ("WRITE", True, "any", "confirm_then_invoke"),
    ("DESTRUCTIVE", False, "any", "confirm_then_invoke"),
    ("DESTRUCTIVE", True, "any", "confirm_then_invoke"),
    ("DANGEROUS", False, "explicit_by_name", "confirm_then_invoke"),
    ("DANGEROUS", True, "explicit_by_name", "confirm_then_invoke"),
    ("DANGEROUS", False, "not_explicit", "reject"),
    ("DANGEROUS", True, "not_explicit", "reject"),
    ("DANGEROUS", False, "general", "reject"),
    ("DANGEROUS", True, "general", "reject"),
    ("DANGEROUS", False, "any", "reject"),
    ("DANGEROUS", True, "any", "reject"),
    ("SENSITIVE", False, "any", "invoke"),
    ("SENSITIVE", True, "any", "confirm_then_invoke"),
]


def evaluate_decision(
    risk: str,
    requires_confirmation: bool,
    user_intent: str,
) -> str:
    """Canonical Template C1 / C6: Decision Policy evaluator.

    Returns one of: 'invoke', 'confirm_then_invoke', 'reject', 'defer'.

    Unknown risk values or unmatched combinations fall back to 'defer' —
    the consumer MUST NOT invoke a tool whose capability profile is unresolved.
    """
    for r, rc, ui, decision in DECISION_POLICY:
        if r == risk and rc == requires_confirmation:
            if ui == "any" or ui == user_intent:
                return decision
    return "defer"


# ── Canonical Template C3: Error Strategy Matrix ─────────────────────

ERROR_STRATEGY_MATRIX: dict[str, ErrorStrategy] = {
    "TIMEOUT": ErrorStrategy(retry=True, max_retries=3, action=ErrorAction.RETRY),
    "DEVICE_OFFLINE": ErrorStrategy(
        retry=True, max_retries=3, action=ErrorAction.RETRY
    ),
    "RESOURCE_LOCKED": ErrorStrategy(
        retry=True, max_retries=3, action=ErrorAction.RETRY_REREAD
    ),
    "INTERNAL_ERROR": ErrorStrategy(
        retry=True, max_retries=1, action=ErrorAction.RETRY_ONCE
    ),
    "HTTP_ERROR": ErrorStrategy(
        retry=False, max_retries=0, action=ErrorAction.ESCALATE
    ),
    "AUTH_FAILED": ErrorStrategy(
        retry=False, max_retries=0, action=ErrorAction.ESCALATE
    ),
    "INVALID_PARAM": ErrorStrategy(
        retry=False, max_retries=0, action=ErrorAction.ESCALATE
    ),
    "UNSUPPORTED": ErrorStrategy(
        retry=False, max_retries=0, action=ErrorAction.ESCALATE
    ),
    "DEPENDENCY_MISSING": ErrorStrategy(
        retry=False, max_retries=0, action=ErrorAction.ESCALATE
    ),
    "DEVICE_NOT_FOUND": ErrorStrategy(
        retry=False, max_retries=0, action=ErrorAction.ESCALATE
    ),
    "VALIDATION_FAILED": ErrorStrategy(
        retry=False, max_retries=0, action=ErrorAction.ESCALATE
    ),
    "RESOURCE_ALREADY_EXISTS": ErrorStrategy(
        retry=False, max_retries=0, action=ErrorAction.ESCALATE
    ),
    "RESOURCE_NOT_FOUND": ErrorStrategy(
        retry=False, max_retries=0, action=ErrorAction.ESCALATE
    ),
}

DEFAULT_ERROR_STRATEGY = ErrorStrategy(
    retry=False, max_retries=0, action=ErrorAction.ESCALATE
)


def get_error_strategy(error_code: str, manifest: dict | None = None) -> ErrorStrategy:
    """Canonical Template C3: Error Strategy Matrix lookup.

    Returns the recovery strategy for an error code, overridden by
    manifest.retryable when present.
    """
    base = ERROR_STRATEGY_MATRIX.get(error_code, DEFAULT_ERROR_STRATEGY)

    if manifest is not None and manifest.get("retryable") is False:
        return ErrorStrategy(retry=False, max_retries=0, action=ErrorAction.ESCALATE)

    return base


# ── Canonical Template C2: Response Parsing ──────────────────────────


@dataclass
class ResponseResult:
    success: bool
    data: Any = None
    meta: dict = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    error_retryable: bool | None = None
    error_suggestion: str | None = None
    is_missing_success: bool = False


def handle_response(response: dict) -> ResponseResult:
    """Canonical Template C2: Parse and branch on a tool response."""
    success_value = response.get("success")

    if success_value is None:
        return ResponseResult(
            success=False,
            error_code="MISSING_SUCCESS_FIELD",
            error_message="Response is missing the 'success' field",
            is_missing_success=True,
        )

    if success_value is True:
        return ResponseResult(
            success=True,
            data=response.get("data"),
            meta=response.get("_meta", {}),
        )

    error = response.get("error")
    if isinstance(error, dict):
        return ResponseResult(
            success=False,
            error_code=error.get("code", "UNKNOWN"),
            error_message=error.get("message", str(error)),
            error_retryable=error.get("retryable"),
            error_suggestion=error.get("suggestion"),
        )
    elif isinstance(error, str):
        return ResponseResult(
            success=False,
            error_code="UNKNOWN",
            error_message=error,
        )

    return ResponseResult(
        success=False,
        error_code="UNKNOWN",
        error_message="Unknown error format",
    )


# ── Canonical Template C4: Confirmation Gate ─────────────────────────


@dataclass
class ConfirmationResult:
    required: bool
    message: str = ""


def requires_user_confirmation(
    manifest: dict,
    user_intent: str,
    workflow_confirmed: bool,
) -> ConfirmationResult:
    """Canonical Template C4: Determine if user confirmation is required."""
    risk = manifest.get("risk", "READ")
    requires_confirm = manifest.get("requires_confirmation", False)
    tool_name = manifest.get("name", "unknown")

    if risk == "DANGEROUS":
        if user_intent != "explicit_by_name":
            return ConfirmationResult(
                required=False,
                message=f"DANGEROUS tool rejected: user must explicitly request {tool_name} by name",
            )
        return ConfirmationResult(
            required=True,
            message=f"Confirm execution of DANGEROUS tool: {tool_name}",
        )

    if risk == "DESTRUCTIVE":
        impact = manifest.get("impact", "unknown")
        reversible = manifest.get("reversible", False)
        return ConfirmationResult(
            required=True,
            message=(
                f"Confirm DESTRUCTIVE operation: {tool_name} "
                f"(impact: {impact}, reversible: {reversible})"
            ),
        )

    if risk not in KNOWN_RISK_VALUES:
        return ConfirmationResult(
            required=True,
            message=f"Capability profile unresolved for tool: {tool_name}",
        )

    if risk == "WRITE" and not workflow_confirmed:
        return ConfirmationResult(
            required=True,
            message=f"Confirm WRITE operation: {tool_name}",
        )

    if requires_confirm:
        return ConfirmationResult(
            required=True,
            message=f"Tool requires confirmation: {tool_name}",
        )

    return ConfirmationResult(required=False)


# ── Canonical Template C5: Retry Decision ────────────────────────────


@dataclass
class RetryDecision:
    should_retry: bool
    max_retries: int
    backoff_base_s: float = 1.0
    backoff_cap_s: float = 8.0


def get_retry_decision(
    error_code: str,
    manifest: dict | None = None,
    error_retryable: bool | None = None,
    current_attempt: int = 0,
) -> RetryDecision:
    """Canonical Template C5: Determine if retry should be attempted.

    Combines the error strategy matrix with the manifest's retryable field
    AND the response's error.retryable (compound error checking per L2+ rule).
    All three must agree for retry to proceed.
    """
    if manifest is not None and manifest.get("retryable") is False:
        return RetryDecision(should_retry=False, max_retries=0)

    if error_retryable is False:
        return RetryDecision(should_retry=False, max_retries=0)

    strategy = get_error_strategy(error_code, manifest)

    if not strategy.retry:
        return RetryDecision(should_retry=False, max_retries=0)

    if current_attempt >= strategy.max_retries:
        return RetryDecision(should_retry=False, max_retries=strategy.max_retries)

    return RetryDecision(
        should_retry=True,
        max_retries=strategy.max_retries,
    )


def compute_backoff_delay(attempt: int) -> float:
    """Exponential backoff: 1s → 2s → 4s, capped at 8s.

    attempt=0 → 1s, attempt=1 → 2s, attempt=2 → 4s.
    """
    return min(2**attempt, 8.0)


# ── HTTP Error Status Code Handling ────────────────────────────────────


def get_http_error_strategy(
    status_code: int,
    manifest: dict | None = None,
) -> ErrorStrategy:
    """Determine retry strategy based on HTTP status code.

    5xx (server error) → retry once.
    4xx (client error) → no retry, escalate.
    Other → escalate.
    Respects manifest.retryable as the final gate.
    """
    if manifest is not None and manifest.get("retryable") is False:
        return ErrorStrategy(retry=False, max_retries=0, action=ErrorAction.ESCALATE)

    if 500 <= status_code <= 599:
        return ErrorStrategy(retry=True, max_retries=1, action=ErrorAction.RETRY_ONCE)

    return ErrorStrategy(retry=False, max_retries=0, action=ErrorAction.ESCALATE)


# ── Canonical Template C7: Capability-Based Tool Selection ────────────

TASK_MATCHERS: dict[str, Any] = {}


def _register_task_matchers():
    global TASK_MATCHERS
    TASK_MATCHERS = {
        "diagnose": lambda m: (
            m.get("risk") == "READ" and m.get("latency") in ("instant", "fast")
        ),
        "configure": lambda m: m.get("risk") == "WRITE" and m.get("reversible", False),
        "destroy": lambda m: m.get("risk") == "DESTRUCTIVE",
        "scan": lambda m: m.get("determinism") == "eventually-consistent",
        "read_sensitive": lambda m: m.get("risk") == "SENSITIVE",
    }


_register_task_matchers()


def select_tool_for_task(tools: list[dict], task_type: str) -> dict | None:
    """Canonical Template C7: Select the best tool for a task type."""
    matcher = TASK_MATCHERS.get(task_type)
    if matcher is None:
        return None
    for tool in tools:
        manifest = tool.get("manifest", {})
        if matcher(manifest):
            return tool
    return None


# ── Safe Default Inference ────────────────────────────────────────────


def infer_manifest_safe_defaults(raw_manifest: dict | None) -> dict:
    """Apply L2+ Backward Compatibility Rule 3: safest defaults for
    missing manifest fields."""
    if raw_manifest is None:
        raw_manifest = {}
    defaults = {
        "risk": "READ",
        "retryable": False,
        "requires_confirmation": False,
        "concurrent_safe": False,
        "reversible": True,
        "idempotent": False,
        "side_effects": "read",
        "determinism": "env-dependent",
        "latency": "moderate",
        "cost": "cheap",
        "impact": "none",
        "privacy": "none",
        "timeout_ms": 30000,
    }
    return {**defaults, **{k: v for k, v in raw_manifest.items() if v is not None}}


# ── Compound Error Checking ──────────────────────────────────────────


def should_retry(
    error_code: str,
    manifest: dict | None = None,
    error_retryable: bool | None = None,
) -> bool:
    """L2+ Compound Error Checking: both manifest AND error must agree.

    If manifest.retryable == False → NEVER retry.
    If error.retryable == False → NEVER retry.
    Only if BOTH permit → consult the error strategy matrix.
    """
    if manifest is not None and manifest.get("retryable") is False:
        return False

    if error_retryable is False:
        return False

    strategy = get_error_strategy(error_code, manifest)
    return strategy.retry


# ── Convenience functions ─────────────────────────────────────────────


def is_success(response: dict) -> bool:
    return response.get("success") is True


def get_error_code(response: dict) -> str | None:
    error = response.get("error")
    if isinstance(error, dict):
        return error.get("code")
    if isinstance(error, str):
        return "UNKNOWN"
    return None


def get_request_id(response: dict) -> str | None:
    meta = response.get("_meta", {})
    return meta.get("request_id")


def parse_manifest(tool_info: dict) -> dict:
    """Extract and normalize a manifest from a tool info dict."""
    manifest = tool_info.get("manifest", {})
    return infer_manifest_safe_defaults(manifest if manifest else None)


def classify_risk(manifest: dict) -> str:
    return manifest.get("risk", "READ")


# ── Capability Profile Inference (L1 Fallback) ─────────────────────────

RISK_PREFIX_PATTERN = {
    "[READ]",
    "[WRITE]",
    "[DESTRUCTIVE]",
    "[DANGEROUS]",
    "[SENSITIVE]",
}


def infer_capability_profile(
    manifest: dict | None = None,
    docstring: str | None = None,
) -> dict:
    """Build a capability profile from manifest, risk prefix, or safe default.

    Priority:
    1. manifest (with safe defaults for missing fields)
    2. risk prefix annotation in docstring (L1 servers without manifests)
    3. documented fallback (treat as READ with all-safe defaults)
    """
    if manifest is not None:
        return infer_manifest_safe_defaults(manifest)

    if docstring is not None:
        doc = docstring.strip()
        for prefix in RISK_PREFIX_PATTERN:
            if doc.startswith(prefix):
                risk_value = prefix[1:-1]
                return infer_manifest_safe_defaults({"risk": risk_value})

    return infer_manifest_safe_defaults(None)


# ── Efficiency Selection ───────────────────────────────────────────────

BATCH_HINT_TOKENS = frozenset(
    {
        "_batch",
        "bulk_",
        "bulk-",
        "batch_",
        "batch-",
        "diagnose_",
        "diagnose-",
        "composite_",
        "composite-",
        "overview_",
        "overview-",
        "summary_",
        "summary-",
        "investigate_",
        "investigate-",
    }
)
BATCH_HINT_STEMS = frozenset(
    {
        "batch",
        "bulk",
        "diagnose",
        "composite",
        "overview",
        "summary",
        "investigate",
    }
)


def _tool_name_matches_batch_hint(name: str) -> bool:
    """Check if a tool name suggests batch/composite efficiency."""
    name_lower = name.lower()
    for hint in BATCH_HINT_TOKENS:
        if hint in name_lower:
            return True
    for stem in BATCH_HINT_STEMS:
        if ("_" + stem) in name_lower or (stem + "_") in name_lower:
            return True
        if name_lower.endswith(stem):
            return True
    return False


def prefer_batch_tool(
    tools: list[dict],
    individual_tool_name: str,
    repeated_count: int = 1,
) -> dict | None:
    """Find a batch/composite alternative to repeated individual calls.

    Returns None when no viable alternative exists or when repeated_count <= 1.
    Never selects a non-READ tool as efficiency optimization for a READ task.
    """
    if repeated_count <= 1:
        return None

    if individual_tool_name:
        individual_manifest = None
        for t in tools:
            if t.get("name") == individual_tool_name:
                individual_manifest = t.get("manifest", {})
                break
        if individual_manifest and individual_manifest.get("risk") != "READ":
            return None

    for tool in tools:
        name = tool.get("name", "")
        manifest = tool.get("manifest", {})
        if manifest.get("risk", "READ") != "READ":
            continue
        if _tool_name_matches_batch_hint(name):
            return tool

    return None


def select_efficient_tool(
    tools: list[dict],
    task: dict | None = None,
) -> dict | None:
    """Select the most efficient tool for a task from a catalog.

    Preference order:
    1. Batch/composite READ tool if task involves repeated reads
    2. Minimal-detail summary/diagnostic tool for initial discovery
    3. Fastest available READ tool by latency
    4. Fallback to None (caller uses standard selection)
    """
    if task is None:
        return None

    repeat_count = task.get("repeated_count", 1)
    individual_name = task.get("individual_tool_name", "")
    if repeat_count > 1 and individual_name:
        batch = prefer_batch_tool(tools, individual_name, repeat_count)
        if batch is not None:
            return batch

    if task.get("phase") == "discovery":
        for tool in tools:
            manifest = tool.get("manifest", {})
            if manifest.get("risk", "READ") != "READ":
                continue
            latency = manifest.get("latency", "moderate")
            if _tool_name_matches_batch_hint(tool.get("name", "")) and latency in (
                "instant",
                "fast",
            ):
                return tool

    return None


# ── Minimal Detail Params ─────────────────────────────────────────────

DETAIL_PARAM_DEFAULTS: dict[str, object] = {
    "detail_level": "minimal",
    "compact": True,
    "summary": True,
    "limit": 50,
    "include_state": False,
    "include_attributes": False,
    "include_code": False,
    "max_results": 50,
}


def choose_initial_detail_params(
    param_schema: dict | None = None,
    user_overrides: dict | None = None,
) -> dict:
    """Choose minimal detail parameters for initial discovery calls.

    Does NOT override explicitly user-provided parameter values.
    Only applies defaults for parameters the user left unset.
    """
    result: dict = {}
    overrides = user_overrides or {}
    keys = list(DETAIL_PARAM_DEFAULTS) if param_schema is None else list(param_schema)

    for key in keys:
        if key in overrides:
            result[key] = overrides[key]
        elif key in DETAIL_PARAM_DEFAULTS:
            result[key] = DETAIL_PARAM_DEFAULTS[key]

    return result


# ── Pagination Helper ──────────────────────────────────────────────────


class PaginationDecision(str, Enum):
    COMPLETE = "complete"
    CONTINUE_PAGINATION = "continue_pagination"
    PARTIAL_SCOPE_SATISFIED = "partial_scope_satisfied"


PAGINATION_MARKERS = frozenset(
    {
        "has_more",
        "next_offset",
        "next_cursor",
        "offset",
        "limit",
        "total",
        "page",
        "cursor",
    }
)


def get_pagination_decision(
    response: dict,
    desired_scope_satisfied: bool = False,
) -> str:
    """Determine pagination state from a response.

    Checks top-level fields and _meta envelope for pagination markers.
    Returns:
    - 'complete' — no pagination markers or has_more=false
    - 'continue_pagination' — has_more=true or next_offset/next_cursor present
    - 'partial_scope_satisfied' — pagination not exhausted but desired scope met
    """
    # Merge known pagination markers into a single lookup dict.
    effective: dict = dict(response)
    data = response.get("data")
    if isinstance(data, dict):
        for k, v in data.items():
            if k not in effective and k in PAGINATION_MARKERS:
                effective[k] = v

    meta = response.get("_meta")
    if isinstance(meta, dict):
        for k, v in meta.items():
            if k not in effective and k in PAGINATION_MARKERS:
                effective[k] = v

    if effective.get("has_more") is True:
        return (
            PaginationDecision.PARTIAL_SCOPE_SATISFIED
            if desired_scope_satisfied
            else PaginationDecision.CONTINUE_PAGINATION
        )

    if (
        effective.get("next_offset") is not None
        or effective.get("next_cursor") is not None
    ):
        return (
            PaginationDecision.PARTIAL_SCOPE_SATISFIED
            if desired_scope_satisfied
            else PaginationDecision.CONTINUE_PAGINATION
        )

    return PaginationDecision.COMPLETE


# ── Negative Capability Helper ─────────────────────────────────────────


def is_meaningful_empty_success(response: dict) -> bool:
    """Check if a successful response carries meaningful emptiness.

    Returns True when success=true and data is an empty structure
    (list, dict, None, or zero count). This is a valid result,
    not an error.
    """
    if response.get("success") is not True:
        return False

    data = response.get("data")
    if data is None:
        return True
    if isinstance(data, list) and len(data) == 0:
        return True
    if isinstance(data, dict) and len(data) == 0:
        return True
    if isinstance(data, dict) and data.get("count") == 0:
        return True
    if isinstance(data, (int, float)) and data == 0:
        return True

    return False

"""Pure decision helpers for safe and efficient MCP capability consumption.

The module performs no network or protocol I/O. It exposes deterministic policy
functions that can be tested independently from an MCP runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence


class Decision(str, Enum):
    """Allowed outcomes of the side-effect policy."""

    INVOKE = "invoke"
    CONFIRM_THEN_INVOKE = "confirm_then_invoke"
    REJECT = "reject"
    DEFER = "defer"


class ErrorAction(str, Enum):
    """Recovery behavior associated with an error category."""

    RETRY = "retry"
    RETRY_AFTER_READ = "retry_after_read"
    ESCALATE = "escalate"


class Risk(str, Enum):
    """Normalized capability effect classes."""

    READ = "READ"
    WRITE = "WRITE"
    DESTRUCTIVE = "DESTRUCTIVE"
    DANGEROUS = "DANGEROUS"
    SENSITIVE = "SENSITIVE"
    UNKNOWN = "UNKNOWN"


class UserIntent(str, Enum):
    """How specifically the user authorized the operation."""

    GENERAL = "general"
    CONFIRMED_WORKFLOW = "confirmed_workflow"
    EXPLICIT_BY_NAME = "explicit_by_name"
    NOT_EXPLICIT = "not_explicit"


@dataclass(frozen=True)
class CapabilityProfile:
    """Policy-relevant facts discovered for one capability."""

    risk: Risk
    requires_confirmation: bool = False
    sensitive: bool = False
    idempotent: bool | None = None
    source: str = "unknown"


@dataclass(frozen=True)
class ErrorStrategy:
    """Bounded recovery policy for one failure category."""

    retryable: bool
    max_retries: int
    action: ErrorAction


@dataclass(frozen=True)
class ResponseResult:
    """Normalized representation of a tool response."""

    success: bool
    data: Any = None
    meta: Mapping[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool | None = None
    correlation_id: str | None = None


@dataclass(frozen=True)
class PaginationDecision:
    """Whether and how a consumer should request another page."""

    continue_paging: bool
    cursor: str | None = None
    offset: int | None = None
    reason: str = ""


ERROR_STRATEGIES: dict[str, ErrorStrategy] = {
    "TIMEOUT": ErrorStrategy(True, 2, ErrorAction.RETRY),
    "RATE_LIMITED": ErrorStrategy(True, 2, ErrorAction.RETRY),
    "UNAVAILABLE": ErrorStrategy(True, 2, ErrorAction.RETRY),
    "UPSTREAM_ERROR": ErrorStrategy(True, 1, ErrorAction.RETRY),
    "CONFLICT": ErrorStrategy(True, 1, ErrorAction.RETRY_AFTER_READ),
    "VALIDATION_FAILED": ErrorStrategy(False, 0, ErrorAction.ESCALATE),
    "AUTHENTICATION_FAILED": ErrorStrategy(False, 0, ErrorAction.ESCALATE),
    "AUTHORIZATION_FAILED": ErrorStrategy(False, 0, ErrorAction.ESCALATE),
    "NOT_FOUND": ErrorStrategy(False, 0, ErrorAction.ESCALATE),
    "UNSUPPORTED": ErrorStrategy(False, 0, ErrorAction.ESCALATE),
    "CANCELLED": ErrorStrategy(False, 0, ErrorAction.ESCALATE),
    "INTERNAL_ERROR": ErrorStrategy(False, 0, ErrorAction.ESCALATE),
}
DEFAULT_ERROR_STRATEGY = ErrorStrategy(False, 0, ErrorAction.ESCALATE)


def _risk(value: str | Risk | None) -> Risk:
    """Normalize a risk value without silently treating unknown input as safe."""
    if isinstance(value, Risk):
        return value
    if not isinstance(value, str):
        return Risk.UNKNOWN
    try:
        return Risk(value.upper())
    except ValueError:
        return Risk.UNKNOWN


def _intent(value: str | UserIntent) -> UserIntent:
    """Normalize user intent, defaulting to the least specific form."""
    if isinstance(value, UserIntent):
        return value
    try:
        return UserIntent(value)
    except (TypeError, ValueError):
        return UserIntent.NOT_EXPLICIT


def evaluate_decision(
    risk: str | Risk,
    requires_confirmation: bool,
    user_intent: str | UserIntent,
) -> Decision:
    """Evaluate whether a capability may be invoked, confirmed, or rejected."""
    normalized_risk = _risk(risk)
    intent = _intent(user_intent)
    if normalized_risk is Risk.UNKNOWN:
        return Decision.DEFER
    if normalized_risk is Risk.READ:
        return Decision.CONFIRM_THEN_INVOKE if requires_confirmation else Decision.INVOKE
    if normalized_risk is Risk.SENSITIVE:
        if requires_confirmation:
            return Decision.CONFIRM_THEN_INVOKE
        return (
            Decision.INVOKE
            if intent is UserIntent.CONFIRMED_WORKFLOW
            else Decision.CONFIRM_THEN_INVOKE
        )
    if normalized_risk is Risk.WRITE:
        if requires_confirmation:
            return Decision.CONFIRM_THEN_INVOKE
        return Decision.INVOKE if intent is UserIntent.CONFIRMED_WORKFLOW else Decision.CONFIRM_THEN_INVOKE
    if normalized_risk is Risk.DESTRUCTIVE:
        return Decision.CONFIRM_THEN_INVOKE
    if normalized_risk is Risk.DANGEROUS:
        return Decision.CONFIRM_THEN_INVOKE if intent is UserIntent.EXPLICIT_BY_NAME else Decision.REJECT
    return Decision.DEFER


def _untrusted_risk_signal(value: Any) -> Risk:
    """Accept untrusted signals only when they increase, never reduce, risk."""
    risk = _risk(value)
    if risk in {Risk.WRITE, Risk.DESTRUCTIVE, Risk.DANGEROUS, Risk.SENSITIVE}:
        return risk
    return Risk.UNKNOWN


def infer_capability_profile(
    name: str,
    metadata: Mapping[str, Any] | None = None,
) -> CapabilityProfile:
    """Infer a conservative profile with explicit provenance and trust boundaries.

    ``trusted_policy`` marks metadata supplied by the local client policy. Server
    names, descriptions, prefixes, and untrusted metadata may increase risk but
    cannot downgrade an unknown capability to READ. MCP annotations are honored
    only when ``trusted_server`` is explicitly true.
    """
    metadata = metadata or {}
    trusted_policy = metadata.get("trusted_policy") is True
    explicit = _risk(metadata.get("risk")) if trusted_policy else _untrusted_risk_signal(metadata.get("risk"))
    inferred = explicit
    source = "local-policy" if trusted_policy and explicit is not Risk.UNKNOWN else (
        "untrusted-risk-escalation" if explicit is not Risk.UNKNOWN else "unknown"
    )

    if inferred is Risk.UNKNOWN:
        upper_name = name.strip().upper()
        for candidate in (Risk.DANGEROUS, Risk.DESTRUCTIVE, Risk.SENSITIVE, Risk.WRITE):
            if upper_name.startswith(f"[{candidate.value}]"):
                inferred = candidate
                source = "name-prefix-escalation"
                break

    annotations = metadata.get("annotations")
    trusted_server = metadata.get("trusted_server") is True
    if isinstance(annotations, Mapping):
        if annotations.get("destructiveHint") is True:
            inferred = Risk.DESTRUCTIVE
            source = (
                "trusted-annotation"
                if trusted_server
                else "untrusted-annotation-escalation"
            )
        elif (
            trusted_server
            and inferred is Risk.UNKNOWN
            and annotations.get("readOnlyHint") is True
        ):
            inferred = Risk.READ
            source = "trusted-annotation"

    sensitive = metadata.get("sensitive") is True
    if sensitive and inferred in {Risk.READ, Risk.UNKNOWN}:
        inferred = Risk.SENSITIVE
        source = f"{source}+sensitive"

    idempotent_value = metadata.get("idempotent")
    idempotent = idempotent_value if isinstance(idempotent_value, bool) else None
    return CapabilityProfile(
        risk=inferred,
        requires_confirmation=metadata.get("requires_confirmation") is True,
        sensitive=sensitive,
        idempotent=idempotent,
        source=source,
    )


def get_error_strategy(error_code: str | None, manifest: Mapping[str, Any] | None = None) -> ErrorStrategy:
    """Return a bounded strategy, respecting an explicit non-retryable contract."""
    strategy = ERROR_STRATEGIES.get((error_code or "").upper(), DEFAULT_ERROR_STRATEGY)
    if manifest and manifest.get("retryable") is False:
        return DEFAULT_ERROR_STRATEGY
    return strategy


def should_retry(
    *,
    error_code: str | None,
    attempt: int,
    operation_idempotent: bool,
    manifest: Mapping[str, Any] | None = None,
    response_retryable: bool | None = None,
    precondition_refreshed: bool = False,
) -> bool:
    """Return whether another attempt is safe and explicitly permitted."""
    if type(attempt) is not int or attempt < 0:
        return False
    strategy = get_error_strategy(error_code, manifest)
    if not strategy.retryable or attempt >= strategy.max_retries:
        return False
    if strategy.action is ErrorAction.RETRY_AFTER_READ and not precondition_refreshed:
        return False
    if response_retryable is False:
        return False
    manifest_retryable = manifest.get("retryable") if manifest is not None else None
    if manifest_retryable is False:
        return False
    if manifest_retryable is not True and response_retryable is not True:
        return False
    return operation_idempotent is True


def _native_error_details(response: Mapping[str, Any]) -> tuple[str, str, bool | None]:
    """Extract a stable error tuple from protocol-native MCP result fields."""
    structured = response.get("structuredContent")
    if isinstance(structured, Mapping):
        nested = structured.get("error")
        payload = nested if isinstance(nested, Mapping) else structured
        code = payload.get("code") or payload.get("error_code") or "MCP_TOOL_ERROR"
        message = payload.get("message") or payload.get("error")
        retryable = payload.get("retryable")
        if message is not None:
            return str(code), str(message), retryable if isinstance(retryable, bool) else None
    content = response.get("content")
    texts: list[str] = []
    if isinstance(content, str):
        texts.append(content)
    elif isinstance(content, Sequence) and not isinstance(content, (str, bytes, bytearray)):
        for item in content:
            if isinstance(item, Mapping) and item.get("text") is not None:
                texts.append(str(item["text"]))
            elif isinstance(item, str):
                texts.append(item)
    message = "\n".join(text for text in texts if text.strip()).strip()
    return "MCP_TOOL_ERROR", message or "Tool invocation failed", None


def _structured_error(
    error: Mapping[str, Any], *, meta: Mapping[str, Any], correlation_id: str | None
) -> ResponseResult:
    """Normalize one explicit structured error mapping."""
    retryable = error.get("retryable")
    return ResponseResult(
        success=False,
        meta=meta,
        error_code=str(error.get("code") or "UNKNOWN"),
        error_message=str(error.get("message") or "Tool invocation failed"),
        retryable=retryable if isinstance(retryable, bool) else None,
        correlation_id=correlation_id,
    )


def handle_response(response: Mapping[str, Any]) -> ResponseResult:
    """Normalize common structured and protocol-native error response shapes."""
    meta = response.get("_meta")
    if not isinstance(meta, Mapping):
        meta = {}
    correlation = meta.get("correlation_id") or response.get("correlation_id")
    correlation_id = str(correlation) if correlation is not None else None
    if response.get("isError") is True:
        error = response.get("error")
        if isinstance(error, Mapping):
            return _structured_error(error, meta=meta, correlation_id=correlation_id)
        code, message, retryable = _native_error_details(response)
        return ResponseResult(False, meta=meta, error_code=code, error_message=message, retryable=retryable, correlation_id=correlation_id)
    success = response.get("success")
    if success is False:
        error = response.get("error")
        if isinstance(error, Mapping):
            return _structured_error(error, meta=meta, correlation_id=correlation_id)
        return ResponseResult(False, meta=meta, error_code="UNKNOWN", error_message=str(error or "Tool invocation failed"), correlation_id=correlation_id)
    if success is True:
        data = response.get("data")
    elif "content" in response or "structuredContent" in response:
        data = response.get("structuredContent", response.get("content"))
    else:
        return ResponseResult(False, meta=meta, error_code="UNRECOGNIZED_RESPONSE", error_message="Response does not contain a recognized success or error shape", correlation_id=correlation_id)
    return ResponseResult(True, data=data, meta=meta, correlation_id=correlation_id)


def is_meaningful_empty_success(result: ResponseResult) -> bool:
    """Return whether an empty value is still a successful contract result."""
    return result.success and result.data in (None, [], {}, "")


def prefer_batch_tool(
    item_count: int,
    *,
    batch_available: bool,
    preserves_policy_boundaries: bool,
    preserves_verification: bool,
) -> bool:
    """Prefer a batch capability only when it retains control and evidence."""
    return item_count > 1 and batch_available and preserves_policy_boundaries and preserves_verification


def select_efficient_tool(
    tools: Sequence[Mapping[str, Any]],
    *,
    required_capabilities: Iterable[str],
    prefer_batch: bool = False,
) -> Mapping[str, Any] | None:
    """Select the narrowest compatible tool using declared capability tags."""
    required = set(required_capabilities)
    if not required:
        return None
    candidates: list[tuple[int, int, str, Mapping[str, Any]]] = []
    for tool in tools:
        declared_value = tool.get("capabilities") or []
        if not isinstance(declared_value, Sequence) or isinstance(declared_value, (str, bytes)):
            continue
        declared = {str(item) for item in declared_value}
        if not required.issubset(declared):
            continue
        extra = len(declared - required)
        batch_penalty = 0 if bool(tool.get("batch")) == prefer_batch else 1
        candidates.append((extra, batch_penalty, str(tool.get("name") or ""), tool))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    return candidates[0][3]


def _schema_accepts_true(schema: Any) -> bool:
    """Return whether a JSON-Schema-like property explicitly accepts true."""
    if not isinstance(schema, Mapping):
        return False
    if "const" in schema:
        return schema.get("const") is True
    enum = schema.get("enum")
    if isinstance(enum, Sequence) and not isinstance(enum, (str, bytes, bytearray)):
        return any(value is True for value in enum)
    schema_type = schema.get("type")
    if schema_type == "boolean":
        return True
    if isinstance(schema_type, Sequence) and not isinstance(schema_type, (str, bytes, bytearray)) and "boolean" in schema_type:
        return True
    for keyword in ("anyOf", "oneOf"):
        alternatives = schema.get(keyword)
        if isinstance(alternatives, Sequence) and not isinstance(alternatives, (str, bytes, bytearray)):
            return any(_schema_accepts_true(alternative) for alternative in alternatives)
    return False


def choose_initial_detail_params(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Choose conservative summary parameters when a schema exposes them."""
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        return {}
    detail = properties.get("detail_level")
    choices = detail.get("enum", []) if isinstance(detail, Mapping) else []
    for candidate in ("summary", "minimal", "compact"):
        if candidate in choices:
            return {"detail_level": candidate}
    for flag in ("compact", "summary"):
        if _schema_accepts_true(properties.get(flag)):
            return {flag: True}
    return {}


def get_pagination_decision(
    meta: Mapping[str, Any],
    *,
    outcome_satisfied: bool,
    pages_seen: int,
    max_pages: int,
) -> PaginationDecision:
    """Decide whether another bounded page should be requested."""
    if outcome_satisfied:
        return PaginationDecision(False, reason="requested outcome is already satisfied")
    if type(pages_seen) is not int or type(max_pages) is not int or pages_seen < 0 or max_pages <= 0:
        return PaginationDecision(False, reason="invalid pagination budget")
    if pages_seen >= max_pages:
        return PaginationDecision(False, reason="pagination limit reached")
    if meta.get("has_more") is False:
        return PaginationDecision(False, reason="server reports no more results")
    cursor = meta.get("next_cursor")
    if isinstance(cursor, str) and cursor.strip():
        return PaginationDecision(True, cursor=cursor, reason="next cursor available")
    offset = meta.get("next_offset")
    if type(offset) is int and offset >= 0:
        return PaginationDecision(True, offset=offset, reason="next offset available")
    return PaginationDecision(False, reason="no continuation token available")

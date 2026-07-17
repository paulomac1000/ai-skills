"""Pure decision helpers for safe and efficient MCP capability consumption.

The module intentionally performs no network or protocol I/O. It gives agents and
applications deterministic policy decisions that can be tested independently from
an MCP runtime.
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
    except ValueError:
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
        return (
            Decision.CONFIRM_THEN_INVOKE
            if requires_confirmation
            else Decision.INVOKE
        )
    if normalized_risk is Risk.SENSITIVE:
        return (
            Decision.CONFIRM_THEN_INVOKE
            if requires_confirmation or intent is UserIntent.NOT_EXPLICIT
            else Decision.INVOKE
        )
    if normalized_risk is Risk.WRITE:
        if requires_confirmation:
            return Decision.CONFIRM_THEN_INVOKE
        return (
            Decision.INVOKE
            if intent is UserIntent.CONFIRMED_WORKFLOW
            else Decision.CONFIRM_THEN_INVOKE
        )
    if normalized_risk is Risk.DESTRUCTIVE:
        return Decision.CONFIRM_THEN_INVOKE
    if normalized_risk is Risk.DANGEROUS:
        return (
            Decision.CONFIRM_THEN_INVOKE
            if intent is UserIntent.EXPLICIT_BY_NAME
            else Decision.REJECT
        )
    return Decision.DEFER


def infer_capability_profile(
    name: str,
    metadata: Mapping[str, Any] | None = None,
) -> CapabilityProfile:
    """Infer a conservative capability profile from explicit metadata or a prefix.

    An explicit ``risk`` field has priority. Prefixes such as ``[READ]`` are a
    compatibility fallback. MCP annotations are treated as descriptive hints and
    never as authorization.
    """
    metadata = metadata or {}
    explicit = _risk(metadata.get("risk"))
    source = "metadata" if explicit is not Risk.UNKNOWN else "unknown"
    inferred = explicit

    if inferred is Risk.UNKNOWN:
        upper_name = name.strip().upper()
        for candidate in Risk:
            if candidate is not Risk.UNKNOWN and upper_name.startswith(f"[{candidate.value}]"):
                inferred = candidate
                source = "name-prefix"
                break

    annotations = metadata.get("annotations")
    if inferred is Risk.UNKNOWN and isinstance(annotations, Mapping):
        if annotations.get("destructiveHint") is True:
            inferred = Risk.DESTRUCTIVE
            source = "annotation"
        elif annotations.get("readOnlyHint") is True:
            inferred = Risk.READ
            source = "annotation"

    sensitive = bool(metadata.get("sensitive"))
    if sensitive and inferred is Risk.READ:
        inferred = Risk.SENSITIVE
        source = f"{source}+sensitive"

    idempotent_value = metadata.get("idempotent")
    idempotent = idempotent_value if isinstance(idempotent_value, bool) else None
    return CapabilityProfile(
        risk=inferred,
        requires_confirmation=bool(metadata.get("requires_confirmation")),
        sensitive=sensitive,
        idempotent=idempotent,
        source=source,
    )


def get_error_strategy(
    error_code: str | None,
    manifest: Mapping[str, Any] | None = None,
) -> ErrorStrategy:
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
) -> bool:
    """Return whether another attempt is safe and permitted by every signal."""
    strategy = get_error_strategy(error_code, manifest)
    if not strategy.retryable or attempt >= strategy.max_retries:
        return False
    if response_retryable is False:
        return False
    if manifest and manifest.get("retryable") is not True and response_retryable is not True:
        return False
    return operation_idempotent


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
            return ResponseResult(
                success=False,
                meta=meta,
                error_code=str(error.get("code") or "UNKNOWN"),
                error_message=str(error.get("message") or "Tool invocation failed"),
                retryable=error.get("retryable") if isinstance(error.get("retryable"), bool) else None,
                correlation_id=correlation_id,
            )
        return ResponseResult(
            success=False,
            meta=meta,
            error_code="UNKNOWN",
            error_message=str(error or "Tool invocation failed"),
            correlation_id=correlation_id,
        )

    success = response.get("success")
    if success is False:
        error = response.get("error")
        if isinstance(error, Mapping):
            return ResponseResult(
                success=False,
                meta=meta,
                error_code=str(error.get("code") or "UNKNOWN"),
                error_message=str(error.get("message") or "Tool invocation failed"),
                retryable=error.get("retryable") if isinstance(error.get("retryable"), bool) else None,
                correlation_id=correlation_id,
            )
        return ResponseResult(
            success=False,
            meta=meta,
            error_code="UNKNOWN",
            error_message=str(error or "Tool invocation failed"),
            correlation_id=correlation_id,
        )

    if success is True:
        data = response.get("data")
    elif "content" in response or "structuredContent" in response:
        data = response.get("structuredContent", response.get("content"))
    else:
        return ResponseResult(
            success=False,
            meta=meta,
            error_code="UNRECOGNIZED_RESPONSE",
            error_message="Response does not contain a recognized success or error shape",
            correlation_id=correlation_id,
        )

    return ResponseResult(
        success=True,
        data=data,
        meta=meta,
        correlation_id=correlation_id,
    )


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
    return (
        item_count > 1
        and batch_available
        and preserves_policy_boundaries
        and preserves_verification
    )


def select_efficient_tool(
    tools: Sequence[Mapping[str, Any]],
    *,
    required_capabilities: Iterable[str],
    prefer_batch: bool = False,
) -> Mapping[str, Any] | None:
    """Select the narrowest compatible tool using declared capability tags."""
    required = set(required_capabilities)
    candidates: list[tuple[int, int, str, Mapping[str, Any]]] = []
    for tool in tools:
        declared = set(tool.get("capabilities") or [])
        if not required.issubset(declared):
            continue
        extra = len(declared - required)
        batch_penalty = 0 if bool(tool.get("batch")) == prefer_batch else 1
        candidates.append((extra, batch_penalty, str(tool.get("name") or ""), tool))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    return candidates[0][3]


def choose_initial_detail_params(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Choose conservative summary parameters when a schema exposes them."""
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        return {}
    if "detail_level" in properties:
        choices = properties["detail_level"].get("enum", []) if isinstance(properties["detail_level"], Mapping) else []
        for candidate in ("summary", "minimal", "compact"):
            if candidate in choices:
                return {"detail_level": candidate}
    if "compact" in properties:
        return {"compact": True}
    if "summary" in properties:
        return {"summary": True}
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
    if pages_seen >= max_pages:
        return PaginationDecision(False, reason="pagination limit reached")
    if meta.get("has_more") is False:
        return PaginationDecision(False, reason="server reports no more results")

    cursor = meta.get("next_cursor")
    if cursor not in (None, ""):
        return PaginationDecision(True, cursor=str(cursor), reason="next cursor available")
    offset = meta.get("next_offset")
    if isinstance(offset, int):
        return PaginationDecision(True, offset=offset, reason="next offset available")
    return PaginationDecision(False, reason="no continuation token available")

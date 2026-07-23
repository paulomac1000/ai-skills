"""Pure decision helpers for safe and efficient MCP capability consumption.

The module performs no network or protocol I/O. Discovered server metadata is
always untrusted; safety-reducing policy values use typed consumer-owned inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence


class Decision(str, Enum):
    INVOKE = "invoke"
    CONFIRM_THEN_INVOKE = "confirm_then_invoke"
    REJECT = "reject"
    DEFER = "defer"


class ErrorAction(str, Enum):
    RETRY = "retry"
    RETRY_AFTER_READ = "retry_after_read"
    ESCALATE = "escalate"


class Risk(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    DESTRUCTIVE = "DESTRUCTIVE"
    DANGEROUS = "DANGEROUS"
    SENSITIVE = "SENSITIVE"
    UNKNOWN = "UNKNOWN"


class UserIntent(str, Enum):
    GENERAL = "general"
    CONFIRMED_WORKFLOW = "confirmed_workflow"
    EXPLICIT_BY_NAME = "explicit_by_name"
    NOT_EXPLICIT = "not_explicit"


@dataclass(frozen=True)
class TrustedCapabilityPolicy:
    """Consumer-owned policy values, never populated from discovered metadata."""

    risk: str | Risk | None = None
    requires_confirmation: bool | None = None
    sensitive: bool | None = None
    idempotent: bool | None = None


@dataclass(frozen=True)
class TrustedCapabilityContract:
    """Reviewed capability-contract facts kept outside server metadata."""

    risk: str | Risk | None = None
    idempotent: bool | None = None


@dataclass(frozen=True)
class CapabilityProfile:
    risk: Risk
    requires_confirmation: bool = False
    sensitive: bool = False
    idempotent: bool | None = None
    source: str = "unknown"


@dataclass(frozen=True)
class ErrorStrategy:
    retryable: bool
    max_retries: int
    action: ErrorAction


@dataclass(frozen=True)
class ResponseResult:
    success: bool
    data: Any = None
    meta: Mapping[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool | None = None
    correlation_id: str | None = None


@dataclass(frozen=True)
class PaginationDecision:
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

_RISK_SEVERITY = {
    Risk.UNKNOWN: 0,
    Risk.READ: 1,
    Risk.WRITE: 2,
    Risk.SENSITIVE: 3,
    Risk.DESTRUCTIVE: 4,
    Risk.DANGEROUS: 5,
}


def _risk(value: str | Risk | None) -> Risk:
    if isinstance(value, Risk):
        return value
    if not isinstance(value, str):
        return Risk.UNKNOWN
    try:
        return Risk(value.upper())
    except ValueError:
        return Risk.UNKNOWN


def _higher_risk(current: Risk, candidate: Risk) -> Risk:
    return candidate if _RISK_SEVERITY[candidate] > _RISK_SEVERITY[current] else current


def _intent(value: str | UserIntent) -> UserIntent:
    if isinstance(value, UserIntent):
        return value
    try:
        return UserIntent(value)
    except (TypeError, ValueError):
        return UserIntent.NOT_EXPLICIT


def evaluate_decision(risk: str | Risk, requires_confirmation: bool, user_intent: str | UserIntent) -> Decision:
    normalized = _risk(risk)
    intent = _intent(user_intent)
    if normalized is Risk.UNKNOWN:
        return Decision.DEFER
    if normalized is Risk.READ:
        return Decision.CONFIRM_THEN_INVOKE if requires_confirmation else Decision.INVOKE
    if normalized in {Risk.WRITE, Risk.SENSITIVE}:
        if requires_confirmation:
            return Decision.CONFIRM_THEN_INVOKE
        return Decision.INVOKE if intent is UserIntent.CONFIRMED_WORKFLOW else Decision.CONFIRM_THEN_INVOKE
    if normalized is Risk.DESTRUCTIVE:
        return Decision.CONFIRM_THEN_INVOKE
    if normalized is Risk.DANGEROUS:
        return Decision.CONFIRM_THEN_INVOKE if intent is UserIntent.EXPLICIT_BY_NAME else Decision.REJECT
    return Decision.DEFER


def _untrusted_risk_signal(value: Any) -> Risk:
    normalized = _risk(value)
    return normalized if normalized in {Risk.WRITE, Risk.SENSITIVE, Risk.DESTRUCTIVE, Risk.DANGEROUS} else Risk.UNKNOWN


def _prefixed_risk(name: str) -> Risk:
    upper_name = name.strip().upper()
    for candidate in (Risk.DANGEROUS, Risk.DESTRUCTIVE, Risk.SENSITIVE, Risk.WRITE):
        if upper_name.startswith(f"[{candidate.value}]"):
            return candidate
    return Risk.UNKNOWN


def _append_source(source: str, addition: str) -> str:
    if source == "unknown":
        return addition
    parts = source.split("+")
    return source if addition in parts else f"{source}+{addition}"


def infer_capability_profile(
    name: str,
    metadata: Mapping[str, Any] | None = None,
    *,
    trusted_policy: TrustedCapabilityPolicy | None = None,
    trusted_contract: TrustedCapabilityContract | None = None,
    trusted_server: bool = False,
) -> CapabilityProfile:
    """Infer a fail-closed profile without upgrading untrusted metadata to policy.

    Sensitivity is an orthogonal confidentiality fact. It remains true even when
    another signal raises the compatibility risk projection to DESTRUCTIVE or
    DANGEROUS.
    """
    if trusted_policy is not None and not isinstance(trusted_policy, TrustedCapabilityPolicy):
        raise TypeError("trusted_policy must be TrustedCapabilityPolicy or None")
    if trusted_contract is not None and not isinstance(trusted_contract, TrustedCapabilityContract):
        raise TypeError("trusted_contract must be TrustedCapabilityContract or None")

    metadata = metadata or {}
    policy_risk = _risk(trusted_policy.risk) if trusted_policy is not None else Risk.UNKNOWN
    contract_risk = _risk(trusted_contract.risk) if trusted_contract is not None else Risk.UNKNOWN
    untrusted_risk = _untrusted_risk_signal(metadata.get("risk"))
    prefix = _prefixed_risk(name)

    inferred = _higher_risk(policy_risk, contract_risk)
    source = "consumer-policy" if policy_risk is not Risk.UNKNOWN else "unknown"
    if contract_risk is not Risk.UNKNOWN:
        source = _append_source(source, "consumer-contract")

    previous = inferred
    inferred = _higher_risk(inferred, untrusted_risk)
    if inferred is not previous:
        source = _append_source(source, "untrusted-risk-escalation")

    previous = inferred
    inferred = _higher_risk(inferred, prefix)
    if inferred is not previous:
        source = _append_source(source, "name-prefix-escalation")

    annotations = metadata.get("annotations")
    if isinstance(annotations, Mapping):
        if annotations.get("destructiveHint") is True:
            previous = inferred
            inferred = _higher_risk(inferred, Risk.DESTRUCTIVE)
            if inferred is not previous:
                source = _append_source(
                    source,
                    "trusted-annotation" if trusted_server is True else "untrusted-annotation-escalation",
                )
        if trusted_server is True and inferred is Risk.UNKNOWN and annotations.get("readOnlyHint") is True:
            inferred = Risk.READ
            source = _append_source(source, "trusted-annotation")

    risk_signals = (policy_risk, contract_risk, untrusted_risk, prefix)
    explicit_sensitive = metadata.get("sensitive") is True or (
        trusted_policy is not None and trusted_policy.sensitive is True
    )
    sensitive = explicit_sensitive or Risk.SENSITIVE in risk_signals
    if explicit_sensitive:
        previous = inferred
        inferred = _higher_risk(inferred, Risk.SENSITIVE)
        if inferred is not previous:
            source = _append_source(source, "sensitive")

    requires_confirmation = metadata.get("requires_confirmation") is True or (
        trusted_policy is not None and trusted_policy.requires_confirmation is True
    )

    if metadata.get("idempotent") is False:
        idempotent: bool | None = False
    elif trusted_policy is not None and trusted_policy.idempotent is False:
        idempotent = False
    elif trusted_contract is not None and trusted_contract.idempotent is False:
        idempotent = False
    elif (
        trusted_policy is not None and trusted_policy.idempotent is True
    ) or (
        trusted_contract is not None and trusted_contract.idempotent is True
    ):
        idempotent = True
    else:
        idempotent = None

    return CapabilityProfile(
        risk=inferred,
        requires_confirmation=requires_confirmation,
        sensitive=sensitive,
        idempotent=idempotent,
        source=source,
    )


def get_error_strategy(error_code: str | None, manifest: Mapping[str, Any] | None = None) -> ErrorStrategy:
    strategy = ERROR_STRATEGIES.get((error_code or "").upper(), DEFAULT_ERROR_STRATEGY)
    if manifest is not None and manifest.get("retryable") is False:
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


def _extract_protocol_error(response: Mapping[str, Any]) -> tuple[str, str]:
    structured = response.get("structuredContent")
    if isinstance(structured, Mapping):
        code = structured.get("code")
        message = structured.get("message") or structured.get("error")
        if isinstance(code, str) or isinstance(message, str):
            return str(code or "MCP_TOOL_ERROR"), str(message or code or "MCP tool failed")
    content = response.get("content")
    if isinstance(content, Sequence) and not isinstance(content, (str, bytes, bytearray)):
        messages = [
            item.get("text")
            for item in content
            if isinstance(item, Mapping) and isinstance(item.get("text"), str)
        ]
        if messages:
            return "MCP_TOOL_ERROR", "\n".join(messages)
    if isinstance(content, str) and content:
        return "MCP_TOOL_ERROR", content
    return "MCP_TOOL_ERROR", "MCP tool failed"


def _legacy_failure(*, error: Any, meta: Mapping[str, Any], correlation_id: str | None) -> ResponseResult:
    if isinstance(error, str) and error.strip():
        message = error.strip()
    elif error is None:
        message = "Tool reported failure without structured error details"
    else:
        message = "Tool reported a malformed legacy error payload"
    return ResponseResult(
        success=False,
        meta=meta,
        error_code="LEGACY_ERROR",
        error_message=message,
        correlation_id=correlation_id,
    )


def handle_response(response: Mapping[str, Any]) -> ResponseResult:
    meta = response.get("_meta")
    if not isinstance(meta, Mapping):
        meta = {}
    correlation_id = meta.get("correlation_id") or meta.get("request_id")
    correlation = str(correlation_id) if correlation_id is not None else None
    error = response.get("error")
    if isinstance(error, Mapping):
        return ResponseResult(
            success=False,
            meta=meta,
            error_code=str(error.get("code") or "UNKNOWN"),
            error_message=str(error.get("message") or "Tool failed"),
            retryable=error.get("retryable") if isinstance(error.get("retryable"), bool) else None,
            correlation_id=correlation,
        )
    if response.get("isError") is True:
        code, message = _extract_protocol_error(response)
        return ResponseResult(
            success=False,
            meta=meta,
            error_code=code,
            error_message=message,
            retryable=response.get("retryable") if isinstance(response.get("retryable"), bool) else None,
            correlation_id=correlation,
        )
    if "error" in response:
        return _legacy_failure(error=error, meta=meta, correlation_id=correlation)

    success_marker = response.get("success")
    if success_marker is False:
        return _legacy_failure(error=None, meta=meta, correlation_id=correlation)
    if "success" in response and success_marker is not True:
        return ResponseResult(
            success=False,
            meta=meta,
            error_code="MALFORMED_RESPONSE",
            error_message="Legacy success marker must be a boolean",
            correlation_id=correlation,
        )
    data = response.get("structuredContent", response.get("data", response.get("content")))
    return ResponseResult(success=True, data=data, meta=meta, correlation_id=correlation)


def select_efficient_tool(
    tools: Iterable[Mapping[str, Any]],
    *,
    required_capabilities: Iterable[str],
    prefer_batch: bool = False,
) -> Mapping[str, Any] | None:
    required = set(required_capabilities)
    if not required:
        return None
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


def _schema_accepts_true(schema: Any) -> bool:
    if not isinstance(schema, Mapping):
        return False
    if "const" in schema:
        return schema.get("const") is True
    enum = schema.get("enum")
    if isinstance(enum, Sequence) and not isinstance(enum, (str, bytes, bytearray)):
        return any(type(value) is bool and value is True for value in enum)
    schema_type = schema.get("type")
    if schema_type == "boolean":
        return True
    if isinstance(schema_type, Sequence) and not isinstance(schema_type, (str, bytes, bytearray)):
        return "boolean" in schema_type
    return False


def choose_initial_detail_params(input_schema: Mapping[str, Any]) -> dict[str, Any]:
    properties = input_schema.get("properties")
    if not isinstance(properties, Mapping):
        return {}
    detail = properties.get("detail_level")
    if isinstance(detail, Mapping):
        enum = detail.get("enum")
        if isinstance(enum, Sequence) and not isinstance(enum, (str, bytes, bytearray)) and "summary" in enum:
            return {"detail_level": "summary"}
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
    if type(pages_seen) is not int or type(max_pages) is not int or pages_seen < 0 or max_pages <= 0:
        return PaginationDecision(False, reason="invalid pagination bounds")
    if outcome_satisfied:
        return PaginationDecision(False, reason="outcome already satisfied")
    if pages_seen >= max_pages:
        return PaginationDecision(False, reason="page limit reached")

    if "has_more" in meta:
        has_more = meta.get("has_more")
        if type(has_more) is not bool:
            return PaginationDecision(False, reason="invalid has_more marker")
        if has_more is False:
            return PaginationDecision(False, reason="server marked final page")

    cursor = meta.get("next_cursor")
    if isinstance(cursor, str) and cursor:
        return PaginationDecision(True, cursor=cursor, reason="next cursor available")
    offset = meta.get("next_offset")
    if type(offset) is int and offset >= 0:
        return PaginationDecision(True, offset=offset, reason="next offset available")
    return PaginationDecision(False, reason="no contract-valid continuation token")

"""Pure decision helpers for safe and efficient MCP capability consumption.

The module performs no network or protocol I/O. Discovered server metadata is
always untrusted; safety-reducing policy values use typed consumer-owned inputs.
"""

from __future__ import annotations

import math
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


ERROR_STRATEGIES = {
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
_MISSING = object()
_INVALID = object()
_ANNOTATION_ROLES = frozenset({"user", "assistant"})


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


def evaluate_decision(
    risk: str | Risk,
    requires_confirmation: bool,
    user_intent: str | UserIntent,
) -> Decision:
    normalized, intent = _risk(risk), _intent(user_intent)
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


def _untrusted_side_effect_signal(metadata: Mapping[str, Any]) -> Risk:
    """Project canonical and compatibility side-effect fields monotonically into risk."""

    inferred = Risk.UNKNOWN
    for key in ("sideEffects", "side_effects"):
        value = metadata.get(key, _MISSING)
        if not isinstance(value, str):
            continue
        candidate = {
            "write": Risk.WRITE,
            "destructive": Risk.DESTRUCTIVE,
        }.get(value.strip().lower(), Risk.UNKNOWN)
        inferred = _higher_risk(inferred, candidate)
    return inferred


def _prefixed_risk(name: Any) -> Risk:
    if not isinstance(name, str):
        return Risk.UNKNOWN
    upper_name = name.strip().upper()
    for candidate in (Risk.DANGEROUS, Risk.DESTRUCTIVE, Risk.SENSITIVE, Risk.WRITE):
        if upper_name.startswith(f"[{candidate.value}]"):
            return candidate
    return Risk.UNKNOWN


def _append_source(source: str, addition: str) -> str:
    if source == "unknown":
        return addition
    return source if addition in source.split("+") else f"{source}+{addition}"


def infer_capability_profile(
    name: str,
    metadata: Mapping[str, Any] | None = None,
    *,
    trusted_policy: TrustedCapabilityPolicy | None = None,
    trusted_contract: TrustedCapabilityContract | None = None,
    trusted_server: bool = False,
) -> CapabilityProfile:
    """Infer a fail-closed profile without upgrading untrusted metadata to policy."""

    if trusted_policy is not None and not isinstance(trusted_policy, TrustedCapabilityPolicy):
        raise TypeError("trusted_policy must be TrustedCapabilityPolicy or None")
    if trusted_contract is not None and not isinstance(trusted_contract, TrustedCapabilityContract):
        raise TypeError("trusted_contract must be TrustedCapabilityContract or None")
    if metadata is None:
        metadata = {}
    elif not isinstance(metadata, Mapping):
        raise TypeError("metadata must be a mapping or None")

    policy_risk = _risk(trusted_policy.risk) if trusted_policy else Risk.UNKNOWN
    contract_risk = _risk(trusted_contract.risk) if trusted_contract else Risk.UNKNOWN
    untrusted_risk = _untrusted_risk_signal(metadata.get("risk"))
    side_effect_risk = _untrusted_side_effect_signal(metadata)
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
    inferred = _higher_risk(inferred, side_effect_risk)
    if inferred is not previous:
        source = _append_source(source, "side-effect-escalation")
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

    risk_signals = (policy_risk, contract_risk, untrusted_risk, side_effect_risk, prefix)
    explicit_sensitive = metadata.get("sensitive") is True or (
        trusted_policy is not None and trusted_policy.sensitive is True
    )
    sensitive = explicit_sensitive or Risk.SENSITIVE in risk_signals
    if explicit_sensitive:
        previous = inferred
        inferred = _higher_risk(inferred, Risk.SENSITIVE)
        if inferred is not previous:
            source = _append_source(source, "sensitive")

    requires_confirmation = (
        metadata.get("requiresConfirmation") is True
        or metadata.get("requires_confirmation") is True
        or (trusted_policy is not None and trusted_policy.requires_confirmation is True)
    )
    if (
        metadata.get("idempotent") is False
        or (trusted_policy and trusted_policy.idempotent is False)
        or (trusted_contract and trusted_contract.idempotent is False)
    ):
        idempotent: bool | None = False
    elif (
        (trusted_policy and trusted_policy.idempotent is True)
        or (trusted_contract and trusted_contract.idempotent is True)
    ):
        idempotent = True
    else:
        idempotent = None
    return CapabilityProfile(inferred, requires_confirmation, sensitive, idempotent, source)


def _alias_value(mapping: Mapping[str, Any], camel: str, snake: str) -> Any:
    """Read one canonical/legacy alias and reject contradictory duplicates."""

    camel_value = mapping.get(camel, _MISSING)
    snake_value = mapping.get(snake, _MISSING)
    if camel_value is not _MISSING and snake_value is not _MISSING and camel_value != snake_value:
        return _INVALID
    return camel_value if camel_value is not _MISSING else snake_value


def _retry_conditions(manifest: Mapping[str, Any] | None) -> Mapping[str, Any] | object | None:
    if manifest is None:
        return None
    value = _alias_value(manifest, "retryConditions", "retry_conditions")
    if value is _MISSING:
        return None
    return value if isinstance(value, Mapping) else _INVALID


def _explicit_retry_veto(manifest: Mapping[str, Any] | None) -> bool:
    if manifest is None:
        return False
    top = manifest.get("retryable", _MISSING)
    if top is not _MISSING and type(top) is not bool:
        return True
    conditions = _retry_conditions(manifest)
    if conditions is _INVALID:
        return True
    if top is True and conditions is None:
        return True
    if isinstance(conditions, Mapping):
        nested = conditions.get("retryable", _MISSING)
        if type(nested) is not bool:
            return True
        if top is _MISSING or top is not nested:
            return True
        if nested is False:
            return True
    return top is False


def get_error_strategy(
    error_code: str | None,
    manifest: Mapping[str, Any] | None = None,
) -> ErrorStrategy:
    strategy = ERROR_STRATEGIES.get((error_code or "").upper(), DEFAULT_ERROR_STRATEGY)
    if manifest is not None and not isinstance(manifest, Mapping):
        return DEFAULT_ERROR_STRATEGY
    return DEFAULT_ERROR_STRATEGY if _explicit_retry_veto(manifest) else strategy


def _nested_retry_permits(
    conditions: Mapping[str, Any],
    *,
    error_code: str | None,
    attempt: int,
    reconciliation_completed: bool,
) -> bool:
    eligible = _alias_value(conditions, "eligibleErrors", "eligible_errors")
    if (
        not isinstance(eligible, Sequence)
        or isinstance(eligible, (str, bytes, bytearray))
        or not eligible
        or any(not isinstance(value, str) or not value for value in eligible)
    ):
        return False
    normalized_error = (error_code or "").upper()
    if normalized_error not in {value.upper() for value in eligible}:
        return False

    max_attempts = _alias_value(conditions, "maxAttempts", "max_attempts")
    if type(max_attempts) is not int or max_attempts < 1:
        return False
    if attempt + 1 >= max_attempts:
        return False

    backoff = _alias_value(conditions, "backoffMilliseconds", "backoff_milliseconds")
    if type(backoff) is not int or backoff <= 0:
        return False

    reconciliation = _alias_value(conditions, "requiresReconciliation", "requires_reconciliation")
    if type(reconciliation) is not bool:
        return False
    if reconciliation and not reconciliation_completed:
        return False
    return True


def should_retry(
    *,
    error_code: str | None,
    attempt: int,
    operation_idempotent: bool,
    manifest: Mapping[str, Any] | None = None,
    response_retryable: bool | None = None,
    precondition_refreshed: bool = False,
    reconciliation_completed: bool = False,
) -> bool:
    if (
        type(attempt) is not int
        or attempt < 0
        or type(operation_idempotent) is not bool
        or type(precondition_refreshed) is not bool
        or type(reconciliation_completed) is not bool
    ):
        return False
    if manifest is not None and not isinstance(manifest, Mapping):
        return False
    if response_retryable is not None and type(response_retryable) is not bool:
        return False

    strategy = get_error_strategy(error_code, manifest)
    if not strategy.retryable or attempt >= strategy.max_retries:
        return False
    if strategy.action is ErrorAction.RETRY_AFTER_READ and not precondition_refreshed:
        return False
    if response_retryable is False:
        return False

    manifest_retryable = manifest.get("retryable") if manifest is not None else None
    if manifest_retryable is not None and type(manifest_retryable) is not bool:
        return False
    if manifest_retryable is False:
        return False

    conditions = _retry_conditions(manifest)
    if conditions is _INVALID:
        return False
    if manifest_retryable is True and conditions is None:
        return False
    if isinstance(conditions, Mapping):
        nested_retryable = conditions.get("retryable", _MISSING)
        if type(nested_retryable) is not bool:
            return False
        if manifest_retryable is None or nested_retryable is not manifest_retryable:
            return False
        if not nested_retryable or not _nested_retry_permits(
            conditions,
            error_code=error_code,
            attempt=attempt,
            reconciliation_completed=reconciliation_completed,
        ):
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


def _failure(
    code: str,
    message: str,
    meta: Mapping[str, Any],
    correlation: str | None,
    retryable: bool | None = None,
) -> ResponseResult:
    return ResponseResult(
        False,
        meta=meta,
        error_code=code,
        error_message=message,
        retryable=retryable,
        correlation_id=correlation,
    )


def _legacy_failure(
    *,
    error: Any,
    meta: Mapping[str, Any],
    correlation_id: str | None,
) -> ResponseResult:
    if isinstance(error, str) and error.strip():
        message = error.strip()
    elif error is None:
        message = "Tool reported failure without structured error details"
    else:
        message = "Tool reported a malformed legacy error payload"
    return _failure("LEGACY_ERROR", message, meta, correlation_id)


def _optional_mapping(value: Mapping[str, Any], key: str) -> bool:
    candidate = value.get(key)
    return key not in value or candidate is None or isinstance(candidate, Mapping)


def _optional_string(value: Mapping[str, Any], key: str) -> bool:
    candidate = value.get(key)
    return key not in value or candidate is None or isinstance(candidate, str)


def _valid_annotations(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    if "audience" in value and value.get("audience") is not None:
        audience = value.get("audience")
        if (
            not isinstance(audience, Sequence)
            or isinstance(audience, (str, bytes, bytearray))
            or any(type(role) is not str or role not in _ANNOTATION_ROLES for role in audience)
        ):
            return False
    if "priority" in value and value.get("priority") is not None:
        priority = value.get("priority")
        if isinstance(priority, bool) or not isinstance(priority, (int, float)):
            return False
        if isinstance(priority, float) and not math.isfinite(priority):
            return False
        if not 0 <= priority <= 1:
            return False
    if "lastModified" in value and value.get("lastModified") is not None:
        last_modified = value.get("lastModified")
        if not isinstance(last_modified, str) or not last_modified.strip():
            return False
    return True


def _optional_annotations(value: Mapping[str, Any]) -> bool:
    annotations = value.get("annotations")
    return "annotations" not in value or annotations is None or _valid_annotations(annotations)


def _valid_resource_contents(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    uri = value.get("uri")
    if not isinstance(uri, str) or not uri:
        return False
    if not _optional_string(value, "mimeType") or not _optional_mapping(value, "_meta"):
        return False
    has_text = "text" in value
    has_blob = "blob" in value
    if has_text == has_blob:
        return False
    return isinstance(value.get("text" if has_text else "blob"), str)


def _valid_content_block(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    if not _optional_annotations(value) or not _optional_mapping(value, "_meta"):
        return False
    block_type = value.get("type")
    if block_type == "text":
        return isinstance(value.get("text"), str)
    if block_type in {"image", "audio"}:
        return (
            isinstance(value.get("data"), str)
            and bool(value.get("data"))
            and isinstance(value.get("mimeType"), str)
            and bool(value.get("mimeType"))
        )
    if block_type == "resource_link":
        if not isinstance(value.get("uri"), str) or not value.get("uri"):
            return False
        if not isinstance(value.get("name"), str) or not value.get("name"):
            return False
        if any(not _optional_string(value, key) for key in ("title", "description", "mimeType")):
            return False
        size = value.get("size")
        return "size" not in value or size is None or (type(size) is int and size >= 0)
    if block_type == "resource":
        return _valid_resource_contents(value.get("resource"))
    return False


def _valid_content_payload(value: Any) -> bool:
    if isinstance(value, str):
        return True
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        return False
    return all(_valid_content_block(item) for item in value)


def handle_response(response: Mapping[str, Any]) -> ResponseResult:
    """Normalize explicit protocol/legacy shapes and reject malformed success payloads."""

    if not isinstance(response, Mapping):
        return _failure("MALFORMED_RESPONSE", "Tool response must be an object", {}, None)
    meta_value = response.get("_meta")
    if "_meta" in response and meta_value is not None and not isinstance(meta_value, Mapping):
        return _failure("MALFORMED_RESPONSE", "MCP _meta must be an object or null", {}, None)
    meta = meta_value if isinstance(meta_value, Mapping) else {}
    response_retryable = response.get("retryable", _MISSING)
    if response_retryable is not _MISSING and response_retryable is not None and type(response_retryable) is not bool:
        return _failure("MALFORMED_RESPONSE", "MCP retryable marker must be a boolean or null", meta, None)
    correlation_id = meta.get("correlation_id") or meta.get("request_id")
    correlation = str(correlation_id) if correlation_id is not None else None

    error = response.get("error")
    if isinstance(error, Mapping):
        nested_retryable = error.get("retryable", _MISSING)
        if nested_retryable is not _MISSING and nested_retryable is not None and type(nested_retryable) is not bool:
            return _failure(
                "MALFORMED_RESPONSE",
                "Structured error retryable marker must be a boolean or null",
                meta,
                correlation,
            )
        return _failure(
            str(error.get("code") or "UNKNOWN"),
            str(error.get("message") or "Tool failed"),
            meta,
            correlation,
            nested_retryable if type(nested_retryable) is bool else None,
        )
    if response.get("isError") is True:
        structured = response.get("structuredContent")
        if "structuredContent" in response and structured is not None and not isinstance(structured, Mapping):
            return _failure(
                "MALFORMED_RESPONSE",
                "MCP structuredContent must be an object or null",
                meta,
                correlation,
            )
        if "content" in response and not _valid_content_payload(response.get("content")):
            return _failure(
                "MALFORMED_RESPONSE",
                "MCP content must be text or a sequence of valid MCP content blocks",
                meta,
                correlation,
            )
        code, message = _extract_protocol_error(response)
        return _failure(
            code,
            message,
            meta,
            correlation,
            response_retryable if type(response_retryable) is bool else None,
        )
    if "error" in response:
        return _legacy_failure(error=error, meta=meta, correlation_id=correlation)
    if "isError" in response and type(response.get("isError")) is not bool:
        return _failure("MALFORMED_RESPONSE", "MCP isError marker must be a boolean", meta, correlation)

    success_marker = response.get("success")
    if success_marker is False:
        return _legacy_failure(error=None, meta=meta, correlation_id=correlation)
    if "success" in response and type(success_marker) is not bool:
        return _failure("MALFORMED_RESPONSE", "Legacy success marker must be a boolean", meta, correlation)

    structured = response.get("structuredContent")
    structured_present = "structuredContent" in response and structured is not None
    content_present = "content" in response
    if structured_present and not isinstance(structured, Mapping):
        return _failure(
            "MALFORMED_RESPONSE",
            "MCP structuredContent must be an object or null",
            meta,
            correlation,
        )
    if content_present and not _valid_content_payload(response.get("content")):
        return _failure(
            "MALFORMED_RESPONSE",
            "MCP content must be text or a sequence of valid MCP content blocks",
            meta,
            correlation,
        )

    payload_keys = [
        key
        for key, present in (
            ("structuredContent", structured_present),
            ("data", "data" in response),
            ("content", content_present),
        )
        if present
    ]
    explicit_legacy_success = success_marker is True
    explicit_protocol_success = response.get("isError") is False and (structured_present or content_present)
    recognized_payload_success = bool(payload_keys)
    if not (explicit_legacy_success or explicit_protocol_success or recognized_payload_success):
        return _failure(
            "MALFORMED_RESPONSE",
            "Tool response has no recognized success or error shape",
            meta,
            correlation,
        )
    data = structured if structured_present else response.get("data", response.get("content"))
    return ResponseResult(True, data=data, meta=meta, correlation_id=correlation)


def select_efficient_tool(
    tools: Iterable[Mapping[str, Any]],
    *,
    required_capabilities: Iterable[str],
    prefer_batch: bool = False,
) -> Mapping[str, Any] | None:
    try:
        required_values = tuple(required_capabilities)
    except TypeError:
        return None
    if not required_values or any(not isinstance(value, str) or not value for value in required_values):
        return None
    required = set(required_values)
    candidates = []
    for tool in tools:
        if not isinstance(tool, Mapping):
            continue
        raw_declared = tool.get("capabilities")
        if not isinstance(raw_declared, Sequence) or isinstance(raw_declared, (str, bytes, bytearray)):
            continue
        if any(not isinstance(value, str) or not value for value in raw_declared):
            continue
        declared = set(raw_declared)
        if required.issubset(declared):
            candidates.append(
                (
                    len(declared - required),
                    0 if bool(tool.get("batch")) == prefer_batch else 1,
                    str(tool.get("name") or ""),
                    tool,
                )
            )
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[:3])
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
    return schema_type == "boolean" or (
        isinstance(schema_type, Sequence)
        and not isinstance(schema_type, (str, bytes, bytearray))
        and "boolean" in schema_type
    )


def choose_initial_detail_params(input_schema: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(input_schema, Mapping):
        return {}
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
    if not isinstance(meta, Mapping):
        return PaginationDecision(False, reason="invalid pagination metadata")
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

"""Deterministic MCP consumer policy decisions with identity-bound trust.

This module is intentionally self-contained. Discovered server metadata can only
increase risk or veto positive claims. Any safety-reducing policy value must be
bound to the exact reviewed capability identity. Legacy constructor/keyword
call shapes remain accepted conservatively at the public boundary, but there is
only one current decision-engine implementation.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class Risk(str, Enum):
    UNKNOWN = "UNKNOWN"
    READ = "READ"
    WRITE = "WRITE"
    SENSITIVE = "SENSITIVE"
    DESTRUCTIVE = "DESTRUCTIVE"
    DANGEROUS = "DANGEROUS"


class Decision(str, Enum):
    INVOKE = "invoke"
    CONFIRM_THEN_INVOKE = "confirm_then_invoke"
    REJECT = "reject"
    DEFER = "defer"


class UserIntent(str, Enum):
    NORMAL = "normal"
    CONFIRMED_WORKFLOW = "confirmed_workflow"
    EXPLICIT_BY_NAME = "explicit_by_name"


class ErrorAction(str, Enum):
    RETRY = "retry"
    SURFACE = "surface"
    REAUTHENTICATE = "reauthenticate"
    DEFER = "defer"


@dataclass(frozen=True)
class CapabilityProfile:
    risk: Risk
    requires_confirmation: bool
    sensitive: bool
    idempotent: bool | None
    source: str


@dataclass(frozen=True)
class ResponseResult:
    ok: bool
    data: Any = None
    error: str | None = None
    retryable: bool = False
    error_code: str | None = None
    next_token: str | None = None
    total_count: int | None = None


@dataclass(frozen=True)
class ErrorStrategy:
    action: ErrorAction
    max_retries: int
    backoff_seconds: tuple[int, ...]


@dataclass(frozen=True)
class PaginationDecision:
    continue_fetching: bool
    next_token: str | None
    reason: str


ERROR_STRATEGIES: dict[str, ErrorStrategy] = {
    "AUTH_FAILED": ErrorStrategy(ErrorAction.REAUTHENTICATE, 0, ()),
    "AUTH_EXPIRED": ErrorStrategy(ErrorAction.REAUTHENTICATE, 0, ()),
    "UNAUTHORIZED": ErrorStrategy(ErrorAction.REAUTHENTICATE, 0, ()),
    "RATE_LIMITED": ErrorStrategy(ErrorAction.RETRY, 3, (2, 5, 10)),
    "TIMEOUT": ErrorStrategy(ErrorAction.RETRY, 2, (1, 3)),
    "NETWORK_ERROR": ErrorStrategy(ErrorAction.RETRY, 2, (1, 3)),
    "BACKEND_UNAVAILABLE": ErrorStrategy(ErrorAction.RETRY, 2, (2, 5)),
    "VALIDATION_ERROR": ErrorStrategy(ErrorAction.SURFACE, 0, ()),
    "NOT_FOUND": ErrorStrategy(ErrorAction.SURFACE, 0, ()),
    "CONFLICT": ErrorStrategy(ErrorAction.SURFACE, 0, ()),
    "PERMISSION_DENIED": ErrorStrategy(ErrorAction.SURFACE, 0, ()),
    "UNKNOWN": ErrorStrategy(ErrorAction.DEFER, 0, ()),
}
DEFAULT_ERROR_STRATEGY = ErrorStrategy(ErrorAction.DEFER, 0, ())

_RISK_RANK = {
    Risk.UNKNOWN: 0,
    Risk.READ: 1,
    Risk.WRITE: 2,
    Risk.SENSITIVE: 3,
    Risk.DESTRUCTIVE: 4,
    Risk.DANGEROUS: 5,
}
_MISSING = object()
_INVALID = object()
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_POLICY_SOURCE = re.compile(r"^[a-z][a-z0-9-]*:sha256:[0-9a-f]{64}$")


class _CapabilityProfileResult(Protocol):
    risk: object
    requires_confirmation: bool
    sensitive: bool
    idempotent: bool | None
    source: str


def _risk(value: Any) -> Risk:
    if isinstance(value, Risk):
        return value
    if not isinstance(value, str):
        return Risk.UNKNOWN
    try:
        return Risk(value.strip().upper())
    except ValueError:
        return Risk.UNKNOWN


def _intent(value: Any) -> UserIntent:
    if isinstance(value, UserIntent):
        return value
    if not isinstance(value, str):
        return UserIntent.NORMAL
    try:
        return UserIntent(value.strip().lower())
    except ValueError:
        return UserIntent.NORMAL


def _higher_risk(left: Risk, right: Risk) -> Risk:
    return right if _RISK_RANK[right] > _RISK_RANK[left] else left


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
    inferred = Risk.UNKNOWN
    for key in ("sideEffects", "side_effects"):
        value = metadata.get(key, _MISSING)
        if not isinstance(value, str):
            continue
        candidate = {"write": Risk.WRITE, "destructive": Risk.DESTRUCTIVE}.get(
            value.strip().lower(), Risk.UNKNOWN
        )
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


def _alias_value(mapping: Mapping[str, Any], camel: str, snake: str) -> Any:
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


def get_error_strategy(error_code: str) -> ErrorStrategy:
    if not isinstance(error_code, str):
        return DEFAULT_ERROR_STRATEGY
    return ERROR_STRATEGIES.get(error_code.strip().upper(), DEFAULT_ERROR_STRATEGY)


def _manifest_retryable(error_code: str, manifest: Mapping[str, Any] | None) -> bool:
    if manifest is None:
        return False
    conditions = _retry_conditions(manifest)
    if not isinstance(conditions, Mapping) or conditions is _INVALID:
        return False
    if conditions.get("retryable") is not True:
        return False
    raw_codes = _alias_value(conditions, "errorCodes", "error_codes")
    if not isinstance(raw_codes, Sequence) or isinstance(raw_codes, str):
        return False
    normalized_codes: set[str] = set()
    for value in raw_codes:
        if not isinstance(value, str) or not value.strip():
            return False
        normalized_codes.add(value.strip().upper())
    return error_code in normalized_codes


def _declared_idempotent(idempotent: bool | None, manifest: Mapping[str, Any] | None) -> bool:
    if manifest is None:
        return False
    manifest_idempotent = manifest.get("idempotent", _MISSING)
    if type(manifest_idempotent) is not bool or manifest_idempotent is not True:
        return False
    return idempotent is True


def should_retry(
    error_code: str,
    attempt: int,
    idempotent: bool | None = None,
    manifest: Mapping[str, Any] | None = None,
) -> bool:
    if not isinstance(error_code, str) or not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 0:
        return False
    if idempotent is not None and type(idempotent) is not bool:
        return False
    if manifest is not None and not isinstance(manifest, Mapping):
        return False
    if _explicit_retry_veto(manifest):
        return False
    normalized = error_code.strip().upper()
    if not normalized:
        return False
    strategy = get_error_strategy(normalized)
    if strategy.action is not ErrorAction.RETRY or attempt >= strategy.max_retries:
        return False
    return _declared_idempotent(idempotent, manifest) and _manifest_retryable(normalized, manifest)


def _is_invalid_mapping(value: Any) -> bool:
    return not isinstance(value, Mapping)


def _contract_violation(message: str, error_code: str = "CONTRACT_VIOLATION") -> ResponseResult:
    return ResponseResult(ok=False, error=message, retryable=False, error_code=error_code)


def _parse_nonnegative_int(value: Any) -> int | None | object:
    if value is _MISSING:
        return None
    if type(value) is int and value >= 0:
        return value
    return _INVALID


def _normalize_next_token(value: Any) -> str | None | object:
    if value is _MISSING or value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return _INVALID


def _extract_structured_response(response: Mapping[str, Any]) -> tuple[Any, str | None, int | None] | ResponseResult:
    structured = response.get("structuredContent", _MISSING)
    if structured is _MISSING:
        return response.get("content"), None, None
    if not isinstance(structured, Mapping):
        return _contract_violation("structuredContent must be an object")
    data = structured.get("data", structured)
    next_token_value = _alias_value(structured, "nextPageToken", "next_page_token")
    next_token = _normalize_next_token(next_token_value)
    if next_token is _INVALID:
        return _contract_violation("nextPageToken must be a non-empty string or null")
    total_value = _alias_value(structured, "totalCount", "total_count")
    total_count = _parse_nonnegative_int(total_value)
    if total_count is _INVALID:
        return _contract_violation("totalCount must be a non-negative integer")
    return data, next_token, total_count


def handle_response(response: Mapping[str, Any] | Any) -> ResponseResult:
    if _is_invalid_mapping(response):
        return _contract_violation("response must be an object")
    assert isinstance(response, Mapping)
    if type(response.get("isError", False)) is not bool:
        return _contract_violation("isError must be boolean when present")
    if response.get("isError") is True:
        structured = response.get("structuredContent")
        if structured is None:
            return _contract_violation("error response is missing structuredContent")
        if not isinstance(structured, Mapping):
            return _contract_violation("error structuredContent must be an object")
        error = structured.get("error")
        if not isinstance(error, Mapping):
            return _contract_violation("error response is missing structuredContent.error")
        code = error.get("code")
        message = error.get("message")
        retryable = error.get("retryable")
        if not isinstance(code, str) or not code.strip():
            return _contract_violation("error.code must be a non-empty string")
        if not isinstance(message, str) or not message.strip():
            return _contract_violation("error.message must be a non-empty string")
        if type(retryable) is not bool:
            return _contract_violation("error.retryable must be boolean")
        normalized = code.strip().upper()
        return ResponseResult(
            ok=False,
            error=message,
            retryable=retryable,
            error_code=normalized,
        )
    extracted = _extract_structured_response(response)
    if isinstance(extracted, ResponseResult):
        return extracted
    data, next_token, total_count = extracted
    return ResponseResult(ok=True, data=data, next_token=next_token, total_count=total_count)


def select_efficient_tool(
    tools: Sequence[Mapping[str, Any]],
    required_fields: Sequence[str],
) -> Mapping[str, Any] | None:
    if isinstance(tools, (str, bytes)) or isinstance(required_fields, (str, bytes)):
        return None
    required: set[str] = set()
    for field in required_fields:
        if not isinstance(field, str) or not field:
            return None
        required.add(field)
    candidates: list[tuple[int, int, Mapping[str, Any]]] = []
    for tool in tools:
        if not isinstance(tool, Mapping):
            continue
        name = tool.get("name")
        if not isinstance(name, str) or not name:
            continue
        output_schema = tool.get("outputSchema", {})
        if not isinstance(output_schema, Mapping):
            continue
        properties = output_schema.get("properties", {})
        if not isinstance(properties, Mapping):
            continue
        available = {key for key in properties if isinstance(key, str)}
        if required <= available:
            candidates.append((len(available), len(name), tool))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1], str(item[2].get("name", ""))))
    return candidates[0][2]


def choose_initial_detail_params(tool_schema: Mapping[str, Any] | None) -> dict[str, Any]:
    if tool_schema is None:
        return {}
    if not isinstance(tool_schema, Mapping):
        return {}
    input_schema = tool_schema.get("inputSchema", {})
    if not isinstance(input_schema, Mapping):
        return {}
    properties = input_schema.get("properties", {})
    if not isinstance(properties, Mapping):
        return {}
    result: dict[str, Any] = {}
    if "summary" in properties:
        result["summary"] = True
    if "detail" in properties:
        detail = properties["detail"]
        if isinstance(detail, Mapping):
            enum = detail.get("enum")
            if isinstance(enum, Sequence) and not isinstance(enum, str) and "summary" in enum:
                result["detail"] = "summary"
    if "fields" in properties:
        field_schema = properties["fields"]
        if isinstance(field_schema, Mapping):
            default = field_schema.get("default")
            if isinstance(default, Sequence) and not isinstance(default, str):
                result["fields"] = list(default)
    return result


def get_pagination_decision(
    response: ResponseResult,
    pages_fetched: int,
    items_fetched: int,
    *,
    max_pages: int = 10,
    max_items: int = 1000,
) -> PaginationDecision:
    if not isinstance(response, ResponseResult):
        return PaginationDecision(False, None, "invalid-response")
    values = (pages_fetched, items_fetched, max_pages, max_items)
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in values):
        return PaginationDecision(False, None, "invalid-bounds")
    if max_pages == 0 or max_items == 0:
        return PaginationDecision(False, None, "limit-reached")
    if not response.ok:
        return PaginationDecision(False, None, "response-error")
    if response.next_token is None:
        return PaginationDecision(False, None, "no-next-token")
    if pages_fetched >= max_pages or items_fetched >= max_items:
        return PaginationDecision(False, None, "limit-reached")
    if response.total_count is not None and items_fetched >= response.total_count:
        return PaginationDecision(False, None, "total-count-reached")
    return PaginationDecision(True, response.next_token, "next-page")


def _nonempty(value: str, field_name: str, maximum: int = 512) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{field_name} must be a non-empty string of at most {maximum} characters")


@dataclass(frozen=True, slots=True)
class CapabilityIdentity:
    """Exact capability identity observed from the selected server contract."""

    server_identity: str
    tool_name: str
    tool_schema_hash: str
    manifest_version: str
    target_scope: str | None = None

    def __post_init__(self) -> None:
        _nonempty(self.server_identity, "server_identity")
        _nonempty(self.tool_name, "tool_name", 255)
        if not _DIGEST.fullmatch(self.tool_schema_hash):
            raise ValueError("tool_schema_hash must be a lowercase sha256 digest")
        _nonempty(self.manifest_version, "manifest_version", 128)
        if self.target_scope is not None:
            _nonempty(self.target_scope, "target_scope", 255)


@dataclass(frozen=True, slots=True)
class TrustedPolicyBinding:
    """Consumer-owned provenance for values reviewed against one exact identity."""

    identity: CapabilityIdentity
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.identity, CapabilityIdentity):
            raise TypeError("identity must be CapabilityIdentity")
        if not _POLICY_SOURCE.fullmatch(self.source):
            raise ValueError("source must be an immutable '<kind>:sha256:<64 lowercase hex>' identity")


@dataclass(frozen=True, slots=True)
class TrustedCapabilityPolicy:
    """Consumer policy values; positive trust requires ``binding``."""

    risk: object = None
    requires_confirmation: bool | None = None
    sensitive: bool | None = None
    idempotent: bool | None = None
    binding: TrustedPolicyBinding | None = None

    def __post_init__(self) -> None:
        if self.binding is not None and not isinstance(self.binding, TrustedPolicyBinding):
            raise TypeError("binding must be TrustedPolicyBinding or None")
        for field_name in ("requires_confirmation", "sensitive", "idempotent"):
            value = getattr(self, field_name)
            if value is not None and type(value) is not bool:
                raise TypeError(f"{field_name} must be boolean or None")


@dataclass(frozen=True, slots=True)
class TrustedCapabilityContract:
    """Reviewed capability facts; positive trust requires ``binding``."""

    risk: object = None
    idempotent: bool | None = None
    binding: TrustedPolicyBinding | None = None

    def __post_init__(self) -> None:
        if self.binding is not None and not isinstance(self.binding, TrustedPolicyBinding):
            raise TypeError("binding must be TrustedPolicyBinding or None")
        if self.idempotent is not None and type(self.idempotent) is not bool:
            raise TypeError("idempotent must be boolean or None")


def _validate_binding(
    value: TrustedCapabilityPolicy | TrustedCapabilityContract | None,
    identity: CapabilityIdentity | None,
    invoked_name: str,
    field_name: str,
) -> None:
    if value is None or value.binding is None:
        return
    if identity is None:
        raise ValueError(f"identity is required when bound {field_name} is supplied")
    if identity.tool_name != invoked_name:
        raise ValueError(f"{field_name} tool identity does not match invoked capability name")
    if value.binding.identity != identity:
        raise ValueError(f"{field_name} does not match the observed capability identity")


def infer_capability_profile(
    name: str,
    metadata: Mapping[str, Any] | None = None,
    *,
    identity: CapabilityIdentity | None = None,
    trusted_policy: TrustedCapabilityPolicy | None = None,
    trusted_contract: TrustedCapabilityContract | None = None,
    **legacy_options: Any,
) -> _CapabilityProfileResult:
    """Infer a fail-closed profile using exact, identity-bound trusted values.

    The removed 1.2 ``trusted_server=`` keyword remains accepted through the
    compatibility keyword boundary, but it never turns remote metadata into
    trusted input.
    """

    trusted_server = legacy_options.pop("trusted_server", False)
    if legacy_options:
        unexpected = ", ".join(sorted(str(option) for option in legacy_options))
        raise TypeError(f"unexpected keyword argument(s): {unexpected}")
    if not isinstance(name, str):
        raise TypeError("name must be a string")
    if identity is not None and not isinstance(identity, CapabilityIdentity):
        raise TypeError("identity must be CapabilityIdentity or None")
    if trusted_policy is not None and not isinstance(trusted_policy, TrustedCapabilityPolicy):
        raise TypeError("trusted_policy must be TrustedCapabilityPolicy or None")
    if trusted_contract is not None and not isinstance(trusted_contract, TrustedCapabilityContract):
        raise TypeError("trusted_contract must be TrustedCapabilityContract or None")
    if type(trusted_server) is not bool:
        raise TypeError("trusted_server must be boolean")
    if metadata is None:
        metadata = {}
    elif not isinstance(metadata, Mapping):
        raise TypeError("metadata must be a mapping or None")

    _validate_binding(trusted_policy, identity, name, "trusted_policy")
    _validate_binding(trusted_contract, identity, name, "trusted_contract")

    policy_binding = trusted_policy.binding if trusted_policy is not None else None
    contract_binding = trusted_contract.binding if trusted_contract is not None else None
    if trusted_policy is None:
        policy_risk = Risk.UNKNOWN
    elif policy_binding is not None:
        policy_risk = _risk(trusted_policy.risk)
    else:
        policy_risk = _untrusted_risk_signal(trusted_policy.risk)
    if trusted_contract is None:
        contract_risk = Risk.UNKNOWN
    elif contract_binding is not None:
        contract_risk = _risk(trusted_contract.risk)
    else:
        contract_risk = _untrusted_risk_signal(trusted_contract.risk)

    inferred = _higher_risk(policy_risk, contract_risk)
    source = "unknown"
    if policy_risk is not Risk.UNKNOWN:
        if policy_binding is not None:
            source = _append_source(source, f"consumer-policy:{policy_binding.source}")
        else:
            source = _append_source(source, "legacy-unbound-policy-escalation")
    if contract_risk is not Risk.UNKNOWN:
        if contract_binding is not None:
            source = _append_source(source, f"consumer-contract:{contract_binding.source}")
        else:
            source = _append_source(source, "legacy-unbound-contract-escalation")

    signals = (
        (_untrusted_risk_signal(metadata.get("risk")), "untrusted-risk-escalation"),
        (_untrusted_side_effect_signal(metadata), "side-effect-escalation"),
        (_prefixed_risk(name), "name-prefix-escalation"),
    )
    for candidate, label in signals:
        previous = inferred
        inferred = _higher_risk(inferred, candidate)
        if inferred is not previous:
            source = _append_source(source, label)

    annotations = metadata.get("annotations")
    if isinstance(annotations, Mapping) and annotations.get("destructiveHint") is True:
        previous = inferred
        inferred = _higher_risk(inferred, Risk.DESTRUCTIVE)
        if inferred is not previous:
            source = _append_source(source, "untrusted-annotation-escalation")

    explicit_sensitive = metadata.get("sensitive") is True or (
        trusted_policy is not None and trusted_policy.sensitive is True
    )
    sensitive_signal = (
        policy_risk is Risk.SENSITIVE
        or contract_risk is Risk.SENSITIVE
        or any(candidate is Risk.SENSITIVE for candidate, _label in signals)
    )
    sensitive = explicit_sensitive or sensitive_signal or inferred is Risk.SENSITIVE
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
        or (trusted_policy is not None and trusted_policy.idempotent is False)
        or (trusted_contract is not None and trusted_contract.idempotent is False)
    ):
        idempotent: bool | None = False
    elif (trusted_policy is not None and policy_binding is not None and trusted_policy.idempotent is True) or (
        trusted_contract is not None and contract_binding is not None and trusted_contract.idempotent is True
    ):
        idempotent = True
    else:
        idempotent = None

    return CapabilityProfile(inferred, requires_confirmation, sensitive, idempotent, source)


__all__ = [
    "CapabilityIdentity",
    "CapabilityProfile",
    "Decision",
    "ErrorAction",
    "ErrorStrategy",
    "PaginationDecision",
    "ResponseResult",
    "Risk",
    "TrustedCapabilityContract",
    "TrustedCapabilityPolicy",
    "TrustedPolicyBinding",
    "UserIntent",
    "choose_initial_detail_params",
    "evaluate_decision",
    "get_error_strategy",
    "get_pagination_decision",
    "handle_response",
    "infer_capability_profile",
    "select_efficient_tool",
    "should_retry",
]

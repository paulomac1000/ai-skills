"""Public MCP consumer decisions with identity-bound trusted policy values.

The mature response, retry, pagination, and efficiency helpers remain in the
internal compatibility module. This module owns the public trust boundary:
discovered metadata can only increase risk or veto a positive claim, while any
safety-reducing value must be bound to the exact reviewed capability identity.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _load_legacy() -> Any:
    path = Path(__file__).with_name("decision_engine_legacy.py")
    module_name = f"{__name__}._legacy" if "." in __name__ else f"{__name__}_legacy"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load decision engine compatibility module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_LEGACY = _load_legacy()

Decision = _LEGACY.Decision
ErrorAction = _LEGACY.ErrorAction
ErrorStrategy = _LEGACY.ErrorStrategy
PaginationDecision = _LEGACY.PaginationDecision
ResponseResult = _LEGACY.ResponseResult
Risk = _LEGACY.Risk
UserIntent = _LEGACY.UserIntent
CapabilityProfile = _LEGACY.CapabilityProfile
ERROR_STRATEGIES = _LEGACY.ERROR_STRATEGIES
DEFAULT_ERROR_STRATEGY = _LEGACY.DEFAULT_ERROR_STRATEGY

choose_initial_detail_params = _LEGACY.choose_initial_detail_params
evaluate_decision = _LEGACY.evaluate_decision
get_error_strategy = _LEGACY.get_error_strategy
get_pagination_decision = _LEGACY.get_pagination_decision
handle_response = _LEGACY.handle_response
select_efficient_tool = _LEGACY.select_efficient_tool
should_retry = _LEGACY.should_retry

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_POLICY_SOURCE = re.compile(r"^[a-z][a-z0-9-]*:sha256:[0-9a-f]{64}$")


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
    """Consumer-owned policy values bound to one reviewed capability identity."""

    binding: TrustedPolicyBinding
    risk: object = None
    requires_confirmation: bool | None = None
    sensitive: bool | None = None
    idempotent: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.binding, TrustedPolicyBinding):
            raise TypeError("binding must be TrustedPolicyBinding")
        for field_name in (
            "requires_confirmation",
            "sensitive",
            "idempotent",
        ):
            value = getattr(self, field_name)
            if value is not None and type(value) is not bool:
                raise TypeError(f"{field_name} must be boolean or None")


@dataclass(frozen=True, slots=True)
class TrustedCapabilityContract:
    """Reviewed capability facts bound to server, schema, manifest, and target scope."""

    binding: TrustedPolicyBinding
    risk: object = None
    idempotent: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.binding, TrustedPolicyBinding):
            raise TypeError("binding must be TrustedPolicyBinding")
        if self.idempotent is not None and type(self.idempotent) is not bool:
            raise TypeError("idempotent must be boolean or None")


def _validate_binding(
    value: TrustedCapabilityPolicy | TrustedCapabilityContract | None,
    identity: CapabilityIdentity | None,
    invoked_name: str,
    field_name: str,
) -> None:
    if value is None:
        return
    if identity is None:
        raise ValueError(f"identity is required when {field_name} is supplied")
    if identity.tool_name != invoked_name:
        raise ValueError(f"{field_name} tool identity does not match invoked capability name")
    if value.binding.identity != identity:
        raise ValueError(f"{field_name} does not match the observed capability identity")


def _source(source: str, addition: str) -> str:
    return _LEGACY._append_source(source, addition)


def infer_capability_profile(
    name: str,
    metadata: Mapping[str, Any] | None = None,
    *,
    identity: CapabilityIdentity | None = None,
    trusted_policy: TrustedCapabilityPolicy | None = None,
    trusted_contract: TrustedCapabilityContract | None = None,
) -> Any:
    """Infer a fail-closed profile using exact, identity-bound trusted values.

    Server-discovered values and annotations never reduce risk, confer
    idempotency, or create trust. They may only escalate risk, require
    confirmation, mark confidentiality, or veto an idempotency claim.
    """

    if not isinstance(name, str):
        raise TypeError("name must be a string")
    if identity is not None and not isinstance(identity, CapabilityIdentity):
        raise TypeError("identity must be CapabilityIdentity or None")
    if trusted_policy is not None and not isinstance(
        trusted_policy,
        TrustedCapabilityPolicy,
    ):
        raise TypeError("trusted_policy must be TrustedCapabilityPolicy or None")
    if trusted_contract is not None and not isinstance(
        trusted_contract,
        TrustedCapabilityContract,
    ):
        raise TypeError("trusted_contract must be TrustedCapabilityContract or None")
    if metadata is None:
        metadata = {}
    elif not isinstance(metadata, Mapping):
        raise TypeError("metadata must be a mapping or None")

    _validate_binding(trusted_policy, identity, name, "trusted_policy")
    _validate_binding(trusted_contract, identity, name, "trusted_contract")

    policy_risk = _LEGACY._risk(trusted_policy.risk) if trusted_policy else Risk.UNKNOWN
    contract_risk = _LEGACY._risk(trusted_contract.risk) if trusted_contract else Risk.UNKNOWN
    inferred = _LEGACY._higher_risk(policy_risk, contract_risk)
    source = "unknown"
    if trusted_policy is not None and policy_risk is not Risk.UNKNOWN:
        source = _source(
            source,
            f"consumer-policy:{trusted_policy.binding.source}",
        )
    if trusted_contract is not None and contract_risk is not Risk.UNKNOWN:
        source = _source(
            source,
            f"consumer-contract:{trusted_contract.binding.source}",
        )

    signals = (
        (
            _LEGACY._untrusted_risk_signal(metadata.get("risk")),
            "untrusted-risk-escalation",
        ),
        (
            _LEGACY._untrusted_side_effect_signal(metadata),
            "side-effect-escalation",
        ),
        (_LEGACY._prefixed_risk(name), "name-prefix-escalation"),
    )
    for candidate, label in signals:
        previous = inferred
        inferred = _LEGACY._higher_risk(inferred, candidate)
        if inferred is not previous:
            source = _source(source, label)

    annotations = metadata.get("annotations")
    if isinstance(annotations, Mapping) and annotations.get("destructiveHint") is True:
        previous = inferred
        inferred = _LEGACY._higher_risk(inferred, Risk.DESTRUCTIVE)
        if inferred is not previous:
            source = _source(source, "untrusted-annotation-escalation")

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
        inferred = _LEGACY._higher_risk(inferred, Risk.SENSITIVE)
        if inferred is not previous:
            source = _source(source, "sensitive")

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
    elif (trusted_policy is not None and trusted_policy.idempotent is True) or (
        trusted_contract is not None and trusted_contract.idempotent is True
    ):
        idempotent = True
    else:
        idempotent = None

    return CapabilityProfile(
        inferred,
        requires_confirmation,
        sensitive,
        idempotent,
        source,
    )


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

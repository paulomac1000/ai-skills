#!/usr/bin/env python3
"""Safe construction and validation for cross-boundary diagnostics."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,255}$")
_NAME_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_REASON_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_REVISION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,127}$")
_REF_RE = re.compile(
    r"^(?:(?:[A-Za-z][A-Za-z0-9+.-]{1,31})://|urn:)"
    r"[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,479}$"
)
_PROVENANCE = frozenset({"trusted_runtime", "canonical_identifier", "provider_code"})
_SEVERITIES = frozenset({"info", "warning", "error"})
_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "construction_revision",
        "category",
        "reason_code",
        "severity",
        "safe_fields",
        "source_payload_included",
        "truncated",
        "raw_detail_ref",
    }
)
_SAFE_FIELD_FIELDS = frozenset({"name", "value", "provenance"})
_FALLBACK_CATEGORY = "external_failure"
_FALLBACK_REASON = "diagnostic.unclassified"
_FALLBACK_SEVERITY = "error"

SafeScalar = str | int | bool
Severity = Literal["info", "warning", "error"]


class DiagnosticEgressError(ValueError):
    """Raised when policy itself cannot safely construct diagnostics."""


@dataclass(frozen=True)
class DiagnosticField:
    name: str
    value: SafeScalar
    provenance: str


@dataclass(frozen=True)
class DiagnosticClassification:
    category: str
    reason_code: str
    severity: Severity
    fields: tuple[DiagnosticField, ...] = ()


@dataclass(frozen=True)
class DiagnosticFieldPolicy:
    provenances: frozenset[str]
    allowed_strings: frozenset[str] = frozenset()
    integer_range: tuple[int, int] | None = None
    allow_boolean: bool = False


@dataclass(frozen=True)
class DiagnosticReasonPolicy:
    category: str
    severity: Severity
    fields: Mapping[str, DiagnosticFieldPolicy]

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))


@dataclass(frozen=True)
class DiagnosticPolicy:
    revision: str
    reasons: Mapping[str, DiagnosticReasonPolicy]

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", MappingProxyType(dict(self.reasons)))
        if not isinstance(self.revision, str) or not _REVISION_RE.fullmatch(self.revision):
            raise DiagnosticEgressError("policy revision must be a bounded opaque token")
        if not isinstance(self.reasons, Mapping):
            raise DiagnosticEgressError("reasons must be a mapping")
        for reason_code, reason in self.reasons.items():
            if not isinstance(reason_code, str) or not _REASON_RE.fullmatch(reason_code):
                raise DiagnosticEgressError("reason codes must be bounded stable tokens")
            if not isinstance(reason, DiagnosticReasonPolicy):
                raise DiagnosticEgressError("reason policy must use DiagnosticReasonPolicy")
            if not _NAME_RE.fullmatch(reason.category):
                raise DiagnosticEgressError("reason category must be a bounded stable token")
            if reason.severity not in _SEVERITIES:
                raise DiagnosticEgressError("reason severity is not supported")
            if not isinstance(reason.fields, Mapping):
                raise DiagnosticEgressError("reason fields must be a mapping")
            for name, field_policy in reason.fields.items():
                if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
                    raise DiagnosticEgressError("safe field names must be bounded stable tokens")
                if not isinstance(field_policy, DiagnosticFieldPolicy):
                    raise DiagnosticEgressError("safe fields must use DiagnosticFieldPolicy")
                if (
                    not isinstance(field_policy.provenances, frozenset)
                    or not field_policy.provenances
                    or not field_policy.provenances <= _PROVENANCE
                ):
                    raise DiagnosticEgressError("safe field provenance allowlists must be non-empty and trusted")
                if not isinstance(field_policy.allowed_strings, frozenset) or any(
                    not isinstance(value, str) or not _TOKEN_RE.fullmatch(value)
                    for value in field_policy.allowed_strings
                ):
                    raise DiagnosticEgressError("allowed string values must be bounded policy-owned tokens")
                if not isinstance(field_policy.allow_boolean, bool):
                    raise DiagnosticEgressError("allow_boolean must be boolean")
                if field_policy.integer_range is not None:
                    integer_range = field_policy.integer_range
                    if (
                        not isinstance(integer_range, tuple)
                        or len(integer_range) != 2
                        or any(isinstance(value, bool) or not isinstance(value, int) for value in integer_range)
                        or integer_range[0] > integer_range[1]
                        or integer_range[0] < -(2**63)
                        or integer_range[1] > 2**63 - 1
                    ):
                        raise DiagnosticEgressError("integer_range must be an ordered signed-64-bit pair")
                if (
                    not field_policy.allowed_strings
                    and field_policy.integer_range is None
                    and not field_policy.allow_boolean
                ):
                    raise DiagnosticEgressError("safe field policy must allow at least one bounded value class")


def _safe_scalar(value: object) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, int):
        return -(2**63) <= value <= 2**63 - 1
    return isinstance(value, str) and bool(_TOKEN_RE.fullmatch(value))


def _safe_ref(value: object) -> bool:
    return isinstance(value, str) and bool(_REF_RE.fullmatch(value))


def _value_allowed(value: object, field_policy: DiagnosticFieldPolicy) -> bool:
    if isinstance(value, bool):
        return field_policy.allow_boolean
    if isinstance(value, int):
        if field_policy.integer_range is None:
            return False
        lower, upper = field_policy.integer_range
        return lower <= value <= upper
    return isinstance(value, str) and value in field_policy.allowed_strings


def _fallback(*, revision: str, truncated: bool, raw_detail_ref: str | None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "construction_revision": revision,
        "category": _FALLBACK_CATEGORY,
        "reason_code": _FALLBACK_REASON,
        "severity": _FALLBACK_SEVERITY,
        "safe_fields": [],
        "source_payload_included": False,
        "truncated": truncated,
        "raw_detail_ref": raw_detail_ref if _safe_ref(raw_detail_ref) else None,
    }


def build_safe_diagnostic(
    classification: object,
    *,
    policy: DiagnosticPolicy,
    truncated: bool = False,
    raw_detail_ref: str | None = None,
) -> dict[str, Any]:
    """Build a protected-sink diagnostic from trusted typed classification only.

    Free-form source/provider text has no output field. Invalid or unknown
    classifications fail closed to one bounded generic record.
    """
    if not isinstance(policy, DiagnosticPolicy):
        raise DiagnosticEgressError("policy must be a DiagnosticPolicy")
    if not isinstance(truncated, bool):
        raise DiagnosticEgressError("truncated must be boolean")

    fallback = _fallback(
        revision=policy.revision,
        truncated=truncated,
        raw_detail_ref=raw_detail_ref,
    )
    if not isinstance(classification, DiagnosticClassification):
        return fallback
    reason = policy.reasons.get(classification.reason_code)
    if reason is None:
        return fallback
    if classification.category != reason.category or classification.severity != reason.severity:
        return fallback

    output_fields: list[dict[str, SafeScalar | str]] = []
    seen: set[str] = set()
    if len(classification.fields) > 16:
        return fallback
    for field in classification.fields:
        if not isinstance(field, DiagnosticField):
            return fallback
        field_policy = reason.fields.get(field.name)
        if field.name in seen or field_policy is None:
            return fallback
        seen.add(field.name)
        if field.provenance not in field_policy.provenances or field.provenance not in _PROVENANCE:
            return fallback
        if not _safe_scalar(field.value) or not _value_allowed(field.value, field_policy):
            return fallback
        output_fields.append(
            {
                "name": field.name,
                "value": field.value,
                "provenance": field.provenance,
            }
        )

    return {
        "schema_version": 1,
        "construction_revision": policy.revision,
        "category": classification.category,
        "reason_code": classification.reason_code,
        "severity": classification.severity,
        "safe_fields": output_fields,
        "source_payload_included": False,
        "truncated": truncated,
        "raw_detail_ref": raw_detail_ref if _safe_ref(raw_detail_ref) else None,
    }


def classify_and_build(
    raw_error: object,
    *,
    classifier: Callable[[object], object],
    policy: DiagnosticPolicy,
    truncated: bool = False,
    raw_detail_ref: str | None = None,
) -> dict[str, Any]:
    """Classify untrusted input without ever copying it to the protected output."""
    if not callable(classifier):
        raise DiagnosticEgressError("classifier must be callable")
    try:
        classification = classifier(raw_error)
    except Exception:  # noqa: BLE001 - classifier failure intentionally becomes safe fallback
        classification = None
    return build_safe_diagnostic(
        classification,
        policy=policy,
        truncated=truncated,
        raw_detail_ref=raw_detail_ref,
    )


def validate_diagnostic_egress_semantics(record: object, *, policy: DiagnosticPolicy | None = None) -> tuple[str, ...]:
    """Validate semantic constraints that protect broader-trust sinks."""
    if not isinstance(record, Mapping):
        return ("diagnostic egress record must be an object",)

    findings: list[str] = []
    missing = sorted(_ROOT_FIELDS - set(record))
    if missing:
        findings.append("missing diagnostic fields: " + ", ".join(missing))
    extra = sorted(set(record) - _ROOT_FIELDS)
    if extra:
        findings.append("unknown diagnostic fields: " + ", ".join(extra))
    if record.get("schema_version") != 1:
        findings.append("schema_version must be 1")
    revision = record.get("construction_revision")
    if not isinstance(revision, str) or not _REVISION_RE.fullmatch(revision):
        findings.append("construction_revision must be a bounded opaque token")
    category = record.get("category")
    if not isinstance(category, str) or not _NAME_RE.fullmatch(category):
        findings.append("category must be a bounded stable token")
    reason_code = record.get("reason_code")
    if not isinstance(reason_code, str) or not _REASON_RE.fullmatch(reason_code):
        findings.append("reason_code must be a bounded stable token")
    if record.get("severity") not in _SEVERITIES:
        findings.append("severity is not supported")
    if record.get("source_payload_included") is not False:
        findings.append("protected diagnostics require source_payload_included=false")
    if not isinstance(record.get("truncated"), bool):
        findings.append("truncated must be boolean")
    raw_ref = record.get("raw_detail_ref")
    if raw_ref is not None and not _safe_ref(raw_ref):
        findings.append("raw_detail_ref must be null or a bounded opaque reference")

    fields = record.get("safe_fields")
    if not isinstance(fields, Sequence) or isinstance(fields, (str, bytes, bytearray)):
        findings.append("safe_fields must be an array")
        return tuple(sorted(set(findings)))
    if len(fields) > 16:
        findings.append("safe_fields exceeds the maximum of 16 entries")

    seen: set[str] = set()
    for index, field in enumerate(fields):
        if not isinstance(field, Mapping):
            findings.append(f"safe_fields[{index}] must be an object")
            continue
        unknown = sorted(set(field) - _SAFE_FIELD_FIELDS)
        if unknown:
            findings.append(f"safe_fields[{index}] has unknown fields: " + ", ".join(unknown))
        name = field.get("name")
        if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
            findings.append(f"safe_fields[{index}].name must be a bounded stable token")
        elif name in seen:
            findings.append(f"safe_fields contains duplicate name: {name}")
        else:
            seen.add(name)
        if not _safe_scalar(field.get("value")):
            findings.append(f"safe_fields[{index}].value must be a bounded safe scalar")
        if field.get("provenance") not in _PROVENANCE:
            findings.append(f"safe_fields[{index}].provenance is not trusted")

    if policy is not None:
        if not isinstance(policy, DiagnosticPolicy):
            raise DiagnosticEgressError("policy must be a DiagnosticPolicy")
        if revision != policy.revision:
            findings.append("construction_revision does not match current policy")
        reason = policy.reasons.get(reason_code) if isinstance(reason_code, str) else None
        if reason is None:
            if reason_code != _FALLBACK_REASON or fields:
                findings.append("reason_code is not allowed by policy")
            if reason_code == _FALLBACK_REASON and (
                category != _FALLBACK_CATEGORY or record.get("severity") != _FALLBACK_SEVERITY
            ):
                findings.append("generic fallback category/severity is not canonical")
        else:
            if category != reason.category or record.get("severity") != reason.severity:
                findings.append("category/severity do not match reason policy")
            for index, field in enumerate(fields):
                if not isinstance(field, Mapping):
                    continue
                name = field.get("name")
                provenance = field.get("provenance")
                field_policy = reason.fields.get(name) if isinstance(name, str) else None
                value = field.get("value")
                if (
                    field_policy is None
                    or provenance not in field_policy.provenances
                    or not _value_allowed(value, field_policy)
                ):
                    findings.append(f"safe_fields[{index}] is not allowed by current reason policy")

    return tuple(sorted(set(findings)))

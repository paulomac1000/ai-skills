#!/usr/bin/env python3
"""Runtime-neutral secret taint and egress guard primitives."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, Literal

Sensitivity = Literal["credential", "secret", "personal", "sensitive", "public", "unknown"]
ExposureState = Literal["not_model_visible", "model_visible", "externally_exposed"]
Sink = Literal[
    "delegated_prompt",
    "external_model_prompt",
    "tool_argument",
    "argv",
    "temporary_script",
    "github_output",
    "durable_evidence",
    "log",
    "memory",
    "screenshot",
    "protected_runtime_channel",
]

EXTERNAL_SINKS: frozenset[Sink] = frozenset(
    {
        "delegated_prompt",
        "external_model_prompt",
        "tool_argument",
        "argv",
        "temporary_script",
        "github_output",
        "durable_evidence",
        "log",
        "memory",
        "screenshot",
    }
)
SECRET_SENSITIVITIES = {"credential", "secret"}


class TaintViolation(ValueError):
    """Raised when tainted data would cross a prohibited boundary."""


@dataclass(frozen=True)
class TaintMetadata:
    sensitivity: Sensitivity
    source_boundary: str
    allowed_sinks: tuple[Sink, ...]
    opaque_ref: str
    exposure_state: ExposureState


@dataclass(frozen=True)
class ProtectedBinding:
    opaque_ref: str
    channel: str
    purpose: str


@dataclass(frozen=True)
class ExposureRecord:
    opaque_ref: str
    sensitivity: Sensitivity
    source_boundary: str
    affected_sinks: tuple[Sink, ...]
    exposure_state: Literal["externally_exposed"]
    remediation: tuple[str, ...]


@dataclass
class _ObservedValue:
    raw: str
    metadata: TaintMetadata


class TaintGuard:
    """Hold raw values only in runtime memory and emit safe metadata externally."""

    def __init__(self) -> None:
        self._values: dict[str, _ObservedValue] = {}

    def observe(
        self,
        raw: str,
        *,
        sensitivity: Sensitivity,
        source_boundary: str,
        opaque_ref: str,
        exposure_state: ExposureState = "model_visible",
        allowed_sinks: tuple[Sink, ...] = ("protected_runtime_channel",),
    ) -> TaintMetadata:
        if not raw:
            raise TaintViolation("refusing to register an empty sensitive value")
        if not opaque_ref:
            raise TaintViolation("opaque_ref is required")
        if sensitivity == "public":
            raise TaintViolation("public values do not belong in the secret-taint registry")
        if opaque_ref in self._values and self._values[opaque_ref].raw != raw:
            raise TaintViolation("opaque_ref already identifies a different tainted value")
        metadata = TaintMetadata(
            sensitivity=sensitivity,
            source_boundary=source_boundary,
            allowed_sinks=tuple(allowed_sinks),
            opaque_ref=opaque_ref,
            exposure_state=exposure_state,
        )
        self._values[opaque_ref] = _ObservedValue(raw=raw, metadata=metadata)
        return metadata

    def metadata(self, opaque_ref: str) -> TaintMetadata:
        try:
            return self._values[opaque_ref].metadata
        except KeyError as error:
            raise TaintViolation(f"unknown opaque secret reference: {opaque_ref}") from error

    def _replacement(self, observed: _ObservedValue) -> str:
        return f"[REDACTED:{observed.metadata.opaque_ref}]"

    def sanitize_text(self, text: str, *, sink: Sink) -> str:
        """Redact known tainted values; unknown-sensitive egress must use guard_unknown()."""
        output = text
        for observed in self._values.values():
            if observed.raw not in output:
                continue
            metadata = observed.metadata
            if sink == "protected_runtime_channel" and sink in metadata.allowed_sinks:
                raise TaintViolation("raw protected-channel transfer must use use_protected(), not model-visible text")
            output = output.replace(observed.raw, self._replacement(observed))
        return output

    def sanitize_value(self, value: Any, *, sink: Sink) -> Any:
        """Recursively redact tainted strings, including mapping keys, before external sinks."""
        if isinstance(value, str):
            return self.sanitize_text(value, sink=sink)
        if isinstance(value, list):
            return [self.sanitize_value(item, sink=sink) for item in value]
        if isinstance(value, tuple):
            return tuple(self.sanitize_value(item, sink=sink) for item in value)
        if isinstance(value, dict):
            sanitized: dict[Any, Any] = {}
            for key, item in value.items():
                safe_key = self.sanitize_text(key, sink=sink) if isinstance(key, str) else key
                if safe_key in sanitized and safe_key != key:
                    raise TaintViolation("taint redaction would collapse distinct mapping keys")
                sanitized[safe_key] = self.sanitize_value(item, sink=sink)
            return sanitized
        return value

    def guard_unknown(self, *, sensitivity: Sensitivity, sink: Sink, opaque_ref: str | None = None) -> None:
        """Fail conservatively for unknown-sensitive material at external egress."""
        if sink in EXTERNAL_SINKS and sensitivity == "unknown":
            reference = opaque_ref or "unclassified"
            raise TaintViolation(f"unknown-sensitive material {reference} cannot cross external sink {sink}")

    def protected_binding(self, opaque_ref: str, *, channel: str, purpose: str) -> ProtectedBinding:
        metadata = self.metadata(opaque_ref)
        if "protected_runtime_channel" not in metadata.allowed_sinks:
            raise TaintViolation("protected runtime use is not allowed by taint policy")
        return ProtectedBinding(opaque_ref=opaque_ref, channel=channel, purpose=purpose)

    def use_protected(
        self,
        opaque_ref: str,
        *,
        channel: str,
        purpose: str,
        operation: Callable[[str], Any],
    ) -> tuple[Any, ProtectedBinding]:
        """Resolve raw material only inside a trusted callback and return opaque evidence."""
        binding = self.protected_binding(opaque_ref, channel=channel, purpose=purpose)
        observed = self._values[opaque_ref]
        result = operation(observed.raw)
        return result, binding

    def exposure_record(self, opaque_ref: str, *, affected_sinks: tuple[Sink, ...]) -> ExposureRecord:
        metadata = self.metadata(opaque_ref)
        return ExposureRecord(
            opaque_ref=opaque_ref,
            sensitivity=metadata.sensitivity,
            source_boundary=metadata.source_boundary,
            affected_sinks=tuple(dict.fromkeys(affected_sinks)),
            exposure_state="externally_exposed",
            remediation=(
                "invoke owning rotation-or-revocation policy when applicable",
                "scan retained evidence and logs according to retention policy",
                "add a regression for the leaking mechanism",
            ),
        )


def safe_json(value: Any, guard: TaintGuard, *, sink: Sink) -> str:
    """Serialize a value only after sink-specific taint sanitization."""
    return json.dumps(guard.sanitize_value(value, sink=sink), sort_keys=True)


def exposure_json(record: ExposureRecord) -> str:
    """Serialize an exposure record containing no raw value or plain fingerprint."""
    return json.dumps(asdict(record), sort_keys=True)

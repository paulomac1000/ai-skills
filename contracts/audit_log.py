"""Semantic validation for append-only agentic audit event streams."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


def _stable_value(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _event_fingerprint(event: Mapping[str, Any]) -> str:
    return _stable_value(event)


def _idempotency_identity(event: Mapping[str, Any]) -> tuple[str, str, str, str] | None:
    key = event.get("idempotency_key")
    if not isinstance(key, str) or not key:
        return None
    actor = event.get("actor")
    actor_principal = actor.get("principal_id") if isinstance(actor, Mapping) else None
    capability = event.get("capability")
    target = event.get("target")
    target_identity = target.get("identity") if isinstance(target, Mapping) else None
    if not all(isinstance(value, str) and value for value in (actor_principal, capability, target_identity)):
        return None
    return actor_principal, capability, target_identity, key


def _operation_identity(event: Mapping[str, Any]) -> tuple[str, str, str] | None:
    operation = event.get("operation")
    target = event.get("target")
    target_identity = target.get("identity") if isinstance(target, Mapping) else None
    arguments = event.get("normalized_arguments_digest")
    if not all(isinstance(value, str) and value for value in (operation, target_identity, arguments)):
        return None
    return operation, target_identity, arguments


def _successful_terminal(event: Mapping[str, Any]) -> bool:
    outcome = event.get("outcome")
    if not isinstance(outcome, Mapping):
        return False
    return outcome.get("disposition") == "completed" and outcome.get("execution") == "succeeded"


def _side_effect(event: Mapping[str, Any]) -> str | None:
    outcome = event.get("outcome")
    if not isinstance(outcome, Mapping):
        return None
    value = outcome.get("side_effect")
    return value if isinstance(value, str) else None


def _success_effects_conflict(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    left_effect = _side_effect(left)
    right_effect = _side_effect(right)
    if left_effect == right_effect:
        return False
    positive = {"confirmed", "published"}
    negative = {"none", "disproven"}
    return (left_effect in positive and right_effect in negative) or (
        right_effect in positive and left_effect in negative
    )


def validate_audit_sequence(events: Sequence[Mapping[str, Any]]) -> list[str]:
    """Validate cross-event idempotency, identity, and terminal-success semantics.

    Args:
        events: Ordered append-only audit events that already satisfy the event schema.

    Returns:
        Semantic findings. An empty list means the sequence is internally consistent.
    """
    findings: list[str] = []
    event_fingerprints: dict[str, str] = {}
    key_bindings: dict[tuple[str, str, str, str], tuple[str, str, str]] = {}
    successful_event_by_key: dict[tuple[str, str, str, str], Mapping[str, Any]] = {}

    for index, event in enumerate(events):
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            findings.append(f"event[{index}]: event_id is required")
            continue
        fingerprint = _event_fingerprint(event)
        previous_fingerprint = event_fingerprints.get(event_id)
        if previous_fingerprint is not None:
            label = "DUPLICATE_EVENT_ID" if previous_fingerprint == fingerprint else "EVENT_ID_REBOUND"
            findings.append(f"{label}: {event_id}")
            continue
        event_fingerprints[event_id] = fingerprint

        identity = _idempotency_identity(event)
        operation = _operation_identity(event)
        if identity is not None and operation is not None:
            previous_operation = key_bindings.get(identity)
            if previous_operation is None:
                key_bindings[identity] = operation
            elif previous_operation != operation:
                findings.append(
                    "IDEMPOTENCY_KEY_REBOUND: "
                    f"{identity[3]} moved from {_stable_value(previous_operation)} to {_stable_value(operation)}"
                )

        if identity is not None and _successful_terminal(event):
            previous_success = successful_event_by_key.get(identity)
            if previous_success is not None:
                if _success_effects_conflict(previous_success, event):
                    findings.append(
                        "CONFLICTING_TERMINAL_SUCCESS: "
                        f"idempotency identity {identity[3]} has contradictory successful side effects"
                    )
                else:
                    findings.append(
                        "DUPLICATE_TERMINAL_SUCCESS: "
                        f"idempotency identity {identity[3]} already has a canonical successful result"
                    )
            else:
                successful_event_by_key[identity] = event

    return findings


def validate_append_only_audit(
    previous: Sequence[Mapping[str, Any]],
    current: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Validate that a candidate audit stream only appends to the accepted prefix.

    Args:
        previous: Previously accepted durable audit sequence.
        current: Candidate successor sequence.

    Returns:
        Findings for truncation, prefix mutation, or semantic inconsistency.
    """
    findings = validate_audit_sequence(current)
    if len(current) < len(previous):
        findings.append("AUDIT_TRUNCATED: candidate history is shorter than accepted history")
        return findings
    for index, event in enumerate(previous):
        if index >= len(current):
            break
        if _event_fingerprint(current[index]) != _event_fingerprint(event):
            findings.append(f"AUDIT_PREFIX_MUTATED: event at index {index} changed")
    return findings

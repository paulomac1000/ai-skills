"""Deterministic semantic validation for append-only agentic audit histories."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _canonical_event(event: Mapping[str, object]) -> str:
    return json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _action_binding(event: Mapping[str, object]) -> tuple[str, str, str, str, str, str]:
    actor = _mapping(event.get("actor"))
    action = _mapping(event.get("action"))
    return (
        _text(actor.get("principal")),
        _text(actor.get("session")),
        _text(action.get("capability")),
        _text(action.get("operation")),
        _text(action.get("target")),
        _text(action.get("normalized_args_digest")),
    )


def _idempotency_identity(event: Mapping[str, object]) -> tuple[str, str, str] | None:
    actor = _mapping(event.get("actor"))
    action = _mapping(event.get("action"))
    key_ref = _text(action.get("idempotency_key_ref"))
    if not key_ref:
        return None
    return (_text(actor.get("principal")), _text(actor.get("session")), key_ref)


def _successful_terminal(event: Mapping[str, object]) -> bool:
    outcome = _mapping(event.get("outcome"))
    return outcome.get("disposition") == "completed" and outcome.get("execution") == "succeeded"


def _side_effect(event: Mapping[str, object]) -> str:
    return _text(_mapping(event.get("outcome")).get("side_effect"))


def _success_effects_conflict(left: str, right: str) -> bool:
    if left == right:
        return False
    positive = {"published", "confirmed", "partial"}
    negative = {"none", "not_started", "disproven"}
    return (left in positive and right in negative) or (right in positive and left in negative)


def validate_audit_sequence(events: Sequence[Mapping[str, object]]) -> list[str]:
    """Validate cross-event identity, idempotency, and terminal-success semantics.

    Args:
        events: Audit events in append order after structural schema validation.

    Returns:
        Stable human-readable findings. An empty list means the sequence satisfies
        the reusable audit-history invariants checked by this module.
    """
    findings: list[str] = []
    event_by_id: dict[str, str] = {}
    binding_by_key: dict[tuple[str, str, str], tuple[str, str, str, str, str, str]] = {}
    successful_effect_by_key: dict[tuple[str, str, str], str] = {}

    for index, event in enumerate(events):
        event_id = _text(event.get("event_id"))
        if not event_id:
            findings.append(f"event[{index}]: event_id is required for semantic validation")
        else:
            canonical = _canonical_event(event)
            previous = event_by_id.get(event_id)
            if previous is not None:
                kind = "DUPLICATE_EVENT_ID" if previous == canonical else "EVENT_ID_CONFLICT"
                findings.append(f"event[{index}]: {kind}: {event_id}")
            else:
                event_by_id[event_id] = canonical

        key_identity = _idempotency_identity(event)
        if key_identity is None:
            continue

        binding = _action_binding(event)
        previous_binding = binding_by_key.get(key_identity)
        if previous_binding is None:
            binding_by_key[key_identity] = binding
        elif previous_binding != binding:
            findings.append(
                f"event[{index}]: IDEMPOTENCY_KEY_REBOUND: {key_identity[2]} is bound to a different action identity"
            )
            continue

        if not _successful_terminal(event):
            continue

        effect = _side_effect(event)
        previous_effect = successful_effect_by_key.get(key_identity)
        if previous_effect is not None and _success_effects_conflict(previous_effect, effect):
            findings.append(
                f"event[{index}]: CONFLICTING_TERMINAL_SUCCESS: {key_identity[2]} reports incompatible side effects"
            )
        else:
            successful_effect_by_key.setdefault(key_identity, effect)

    return findings


def validate_audit_append(
    previous_events: Sequence[Mapping[str, object]],
    candidate_events: Sequence[Mapping[str, object]],
) -> list[str]:
    """Validate that a candidate history is an append-only extension of a prior history.

    Args:
        previous_events: Previously accepted immutable audit history.
        candidate_events: Candidate history after appending zero or more events.

    Returns:
        Append-only and sequence-semantic findings. Any finding must block
        publication of the candidate history.
    """
    findings: list[str] = []
    if len(candidate_events) < len(previous_events):
        findings.append("AUDIT_HISTORY_TRUNCATED: candidate history removed accepted events")
    else:
        for index, previous in enumerate(previous_events):
            if _canonical_event(previous) != _canonical_event(candidate_events[index]):
                findings.append(f"AUDIT_HISTORY_REWRITTEN: accepted event at index {index} changed")
                break

    findings.extend(validate_audit_sequence(candidate_events))
    return findings

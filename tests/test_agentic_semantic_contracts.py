"""Acceptance tests for reusable audit-history semantics."""

from __future__ import annotations

from copy import deepcopy

from contracts.audit_log import validate_audit_append, validate_audit_sequence


def _outcome(*, disposition: str = "pending", side_effect: str = "unknown") -> dict[str, object]:
    return {
        "schema_version": 1,
        "transport": "succeeded",
        "execution": "succeeded" if disposition == "completed" else "running",
        "side_effect": side_effect,
        "artifact": "none",
        "verification": "passed" if disposition == "completed" else "not_run",
        "disposition": disposition,
        "safe_to_retry": "no" if disposition == "completed" else "unknown",
    }


def _audit_event(
    event_id: str,
    *,
    target: str = "inventory:item-1",
    key_ref: str = "opaque:key-1",
    disposition: str = "pending",
    side_effect: str = "unknown",
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "event_id": event_id,
        "correlation_id": "corr-1",
        "timestamp": "2026-09-11T00:00:00Z",
        "actor": {"principal": "operator", "session": "session-1"},
        "action": {
            "capability": "inventory.put",
            "operation": "put",
            "target": target,
            "normalized_args_digest": "hmac-sha256:" + "a" * 64,
            "idempotency_key_ref": key_ref,
        },
        "outcome": _outcome(disposition=disposition, side_effect=side_effect),
        "retention_class": "security-audit",
    }


def test_audit_sequence_allows_reconcile_then_terminal_success() -> None:
    events = [
        _audit_event("event-1"),
        _audit_event("event-2", disposition="completed", side_effect="confirmed"),
    ]
    assert validate_audit_sequence(events) == []


def test_audit_sequence_rejects_duplicate_and_conflicting_event_identity() -> None:
    first = _audit_event("event-1")
    changed = deepcopy(first)
    changed["correlation_id"] = "corr-other"

    duplicate = validate_audit_sequence([first, deepcopy(first)])
    conflict = validate_audit_sequence([first, changed])
    assert any("DUPLICATE_EVENT_ID" in finding for finding in duplicate)
    assert any("EVENT_ID_CONFLICT" in finding for finding in conflict)


def test_audit_sequence_rejects_idempotency_key_rebinding() -> None:
    findings = validate_audit_sequence(
        [
            _audit_event("event-1", target="inventory:item-1"),
            _audit_event("event-2", target="inventory:item-2"),
        ]
    )
    assert any("IDEMPOTENCY_KEY_REBOUND" in finding for finding in findings)


def test_audit_sequence_rejects_contradictory_successful_history() -> None:
    findings = validate_audit_sequence(
        [
            _audit_event("event-1", disposition="completed", side_effect="confirmed"),
            _audit_event("event-2", disposition="completed", side_effect="none"),
        ]
    )
    assert any("CONFLICTING_TERMINAL_SUCCESS" in finding for finding in findings)


def test_audit_append_rejects_rewrite_and_truncation() -> None:
    first = _audit_event("event-1")
    second = _audit_event("event-2")
    rewritten = deepcopy(first)
    rewritten["correlation_id"] = "rewritten"

    assert any("AUDIT_HISTORY_REWRITTEN" in finding for finding in validate_audit_append([first], [rewritten]))
    assert any("AUDIT_HISTORY_TRUNCATED" in finding for finding in validate_audit_append([first, second], [first]))

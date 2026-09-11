"""Regressions for application-contract findings retained after the OSG runtime split."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from contracts.audit_log import validate_audit_sequence

ROOT = Path(__file__).resolve().parents[1]


def _audit_event(event_id: str, side_effect: str = "confirmed") -> dict[str, object]:
    return {
        "event_id": event_id,
        "actor": {"principal": "operator", "session": "session-1"},
        "action": {
            "capability": "inventory.put",
            "operation": "put",
            "target": "inventory:item-1",
            "normalized_args_digest": "hmac-sha256:" + "a" * 64,
            "idempotency_key_ref": "opaque:key-1",
        },
        "outcome": {
            "execution": "succeeded",
            "disposition": "completed",
            "side_effect": side_effect,
        },
    }


def test_action_outcome_unknown_side_effect_cannot_be_terminal_failed() -> None:
    schema = json.loads((ROOT / "contracts/action-outcome.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    outcome = {
        "schema_version": 1,
        "transport": "timed_out",
        "execution": "unknown",
        "side_effect": "unknown",
        "artifact": "unknown",
        "verification": "not_run",
        "disposition": "failed",
        "safe_to_retry": "no",
    }
    assert any("failed" in error.message for error in validator.iter_errors(outcome))
    outcome["disposition"] = "reconcile_required"
    assert list(validator.iter_errors(outcome)) == []


def test_audit_rejects_equivalent_second_terminal_success() -> None:
    findings = validate_audit_sequence([_audit_event("event-1"), _audit_event("event-2")])
    assert any("DUPLICATE_TERMINAL_SUCCESS" in finding for finding in findings)


def test_audit_still_distinguishes_conflicting_terminal_success() -> None:
    findings = validate_audit_sequence([_audit_event("event-1"), _audit_event("event-2", "none")])
    assert any("CONFLICTING_TERMINAL_SUCCESS" in finding for finding in findings)

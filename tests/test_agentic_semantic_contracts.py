"""Acceptance tests for reusable audit-history and diagnostic reasoning semantics."""

from __future__ import annotations

from copy import deepcopy

import pytest

from contracts.audit_log import validate_audit_append, validate_audit_sequence
from contracts.diagnostic_reasoning import (
    DiagnosticReasoningError,
    record_probe_result,
    record_remediation_result,
    reopen_hypothesis,
    select_discriminating_probe,
    validate_diagnostic_state,
    validate_diagnostic_transition,
)


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


def _diagnostic_state() -> dict[str, object]:
    return {
        "schema_version": 1,
        "observations": [
            {
                "id": "O1",
                "claim": "Provider returned HTTP 402.",
                "evidence_ref": "ev:http-402",
                "classification": "OBSERVATION",
                "scope": "capability",
                "source_group": "provider-response",
            },
            {
                "id": "O2",
                "claim": "Authoritative account state reports available credit.",
                "evidence_ref": "ev:credit",
                "classification": "FACT",
                "scope": "external",
                "source_group": "account-state",
            },
            {
                "id": "O3",
                "claim": "Exact target route succeeds with the same account.",
                "evidence_ref": "ev:route-success",
                "classification": "OBSERVATION",
                "scope": "capability",
                "source_group": "route-probe",
            },
        ],
        "hypotheses": [
            {
                "id": "H-billing",
                "claim": "The account has insufficient balance.",
                "status": "active",
                "supporting_evidence": ["ev:http-402"],
                "contradicting_evidence": [],
                "next_discriminating_probe": "Read authoritative account credit and probe the exact route.",
                "revision": 1,
            },
            {
                "id": "H-route",
                "claim": "The specific provider route is degraded.",
                "status": "active",
                "supporting_evidence": [],
                "contradicting_evidence": [],
                "next_discriminating_probe": "Probe exact provider route.",
                "revision": 1,
            },
        ],
        "causal_assessment": {"status": "unknown", "causes": [], "unresolved_alternatives": ["H-billing", "H-route"]},
        "evidence_refs": ["ev:http-402", "ev:credit", "ev:route-success"],
    }


def _hypothesis(state: dict[str, object], hypothesis_id: str) -> dict[str, object]:
    hypotheses = state["hypotheses"]
    assert isinstance(hypotheses, list)
    for hypothesis in hypotheses:
        assert isinstance(hypothesis, dict)
        if hypothesis.get("id") == hypothesis_id:
            return hypothesis
    raise AssertionError(f"missing hypothesis {hypothesis_id}")


def test_http_402_does_not_survive_contradicting_live_evidence_as_root_cause() -> None:
    state = _diagnostic_state()
    state = record_probe_result(state, "H-billing", "ev:credit", "contradicts")
    billing = _hypothesis(state, "H-billing")
    assert billing["status"] == "disproven"

    with pytest.raises(DiagnosticReasoningError, match="explicit reopen"):
        record_probe_result(state, "H-billing", "ev:new-402", "supports")


def test_disproven_hypothesis_requires_new_evidence_and_revision_to_reopen() -> None:
    state = record_probe_result(_diagnostic_state(), "H-billing", "ev:credit", "contradicts")
    with pytest.raises(DiagnosticReasoningError, match="must be new"):
        reopen_hypothesis(
            state,
            "H-billing",
            "ev:credit",
            next_discriminating_probe="Probe exact provider route again.",
        )

    reopened = reopen_hypothesis(
        state,
        "H-billing",
        "ev:new-account-state",
        next_discriminating_probe="Probe exact provider route again.",
    )
    billing = _hypothesis(reopened, "H-billing")
    assert billing["status"] == "active"
    assert billing["revision"] == 2
    assert validate_diagnostic_transition(state, reopened) == []


def test_disproven_hypothesis_persists_across_handoff_and_compaction() -> None:
    state = record_probe_result(_diagnostic_state(), "H-billing", "ev:credit", "contradicts")
    compacted = deepcopy(state)
    hypotheses = compacted["hypotheses"]
    assert isinstance(hypotheses, list)
    compacted["hypotheses"] = [item for item in hypotheses if isinstance(item, dict) and item.get("id") != "H-billing"]
    findings = validate_diagnostic_transition(state, compacted)
    assert any("DISPROVEN_HYPOTHESIS_DROPPED" in finding for finding in findings)


def test_failed_remediation_disproves_hypothesis_and_records_postcondition() -> None:
    state = record_remediation_result(
        _diagnostic_state(),
        "H-route",
        "ev:repair-check",
        predicted_postcondition="Exact provider route succeeds.",
        observed_postcondition="Exact provider route still fails.",
        status="failed",
    )
    route = _hypothesis(state, "H-route")
    assert route["status"] == "disproven"
    attempts = state["remediation_attempts"]
    assert isinstance(attempts, list)
    assert attempts[0]["status"] == "failed"


def test_candidate_config_is_not_causal_until_effective_runtime_source_is_proven() -> None:
    state = _diagnostic_state()
    route = _hypothesis(state, "H-route")
    route["status"] = "supported"
    route["config_source_refs"] = ["config:a", "config:b", "config:c"]
    state["effective_config_provenance"] = [
        {"component": "provider", "source": "config:a", "status": "candidate"},
        {"component": "provider", "source": "config:b", "status": "candidate"},
        {"component": "provider", "source": "config:c", "status": "runtime-proven", "evidence_ref": "ev:runtime-config"},
    ]
    state["causal_assessment"] = {
        "status": "suspected",
        "causes": [{"hypothesis_id": "H-route", "role": "primary", "support": "supported", "evidence_refs": ["ev:http-402"]}],
        "unresolved_alternatives": [],
    }
    findings = validate_diagnostic_state(state)
    assert sum("CONFIG_SOURCE_NOT_RUNTIME_PROVEN" in finding for finding in findings) == 2


def test_liveness_and_capability_health_remain_distinct_observations() -> None:
    state = _diagnostic_state()
    observations = state["observations"]
    assert isinstance(observations, list)
    observations.extend(
        [
            {
                "id": "O-process",
                "claim": "Process health endpoint is healthy.",
                "evidence_ref": "ev:process-health",
                "classification": "OBSERVATION",
                "scope": "process",
                "source_group": "runtime-health",
            },
            {
                "id": "O-capability",
                "claim": "Action-specific provider probe fails.",
                "evidence_ref": "ev:provider-probe",
                "classification": "OBSERVATION",
                "scope": "capability",
                "source_group": "provider-probe",
            },
        ]
    )
    assert validate_diagnostic_state(state) == []


def test_probe_selection_ignores_disproven_hypotheses_and_is_deterministic() -> None:
    state = _diagnostic_state()
    state = record_probe_result(state, "H-billing", "ev:credit", "contradicts")
    assert select_discriminating_probe(state) == "Probe exact provider route."


def test_multi_causal_assessment_keeps_independently_evidenced_contributors() -> None:
    state = _diagnostic_state()
    billing = _hypothesis(state, "H-billing")
    route = _hypothesis(state, "H-route")
    billing["status"] = "supported"
    route["status"] = "supported"
    state["causal_assessment"] = {
        "status": "partial",
        "causes": [
            {"hypothesis_id": "H-billing", "role": "contributing", "support": "supported", "evidence_refs": ["ev:credit"]},
            {"hypothesis_id": "H-route", "role": "contributing", "support": "supported", "evidence_refs": ["ev:route-success"]},
        ],
        "unresolved_alternatives": [],
    }
    assert validate_diagnostic_state(state) == []

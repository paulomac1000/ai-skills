"""Regressions for the independent PR #87 governance-hardening audit."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from contracts.audit_log import validate_audit_sequence
from contracts.diagnostic_reasoning import (
    DiagnosticReasoningError,
    record_probe_result,
    record_remediation_result,
    reopen_hypothesis,
    select_discriminating_probe,
    validate_diagnostic_state,
    validate_diagnostic_transition,
)

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


def _diagnostic_state() -> dict[str, object]:
    return {
        "schema_version": 1,
        "observations": [
            {
                "id": "O-route",
                "claim": "Exact route fails while account state remains valid.",
                "evidence_ref": "ev:route",
                "classification": "OBSERVATION",
                "source_group": "route-runtime",
            },
            {
                "id": "O-account",
                "claim": "Authoritative account state reports available credit.",
                "evidence_ref": "ev:account",
                "classification": "FACT",
                "source_group": "account-authority",
            },
        ],
        "probes": [
            {
                "id": "P-common",
                "description": "Probe that predicts the same result for every hypothesis.",
                "source_group": "probe-common",
                "predictions": {"H-billing": "fail", "H-route": "fail"},
                "observed_outcome": None,
                "evidence_ref": None,
            },
            {
                "id": "P-route",
                "description": "Probe exact routing independently.",
                "source_group": "route-independent",
                "predictions": {"H-billing": "route-ok", "H-route": "route-fails"},
                "observed_outcome": "route-fails",
                "evidence_ref": "ev:probe-route",
            },
        ],
        "hypotheses": [
            {
                "id": "H-billing",
                "claim": "Insufficient balance causes the failure.",
                "status": "disproven",
                "supporting_evidence": [],
                "contradicting_evidence": ["ev:account"],
                "next_discriminating_probe": "Check balance.",
                "revision": 1,
            },
            {
                "id": "H-route",
                "claim": "The exact provider route is degraded.",
                "status": "supported",
                "supporting_evidence": ["ev:route", "ev:probe-route"],
                "contradicting_evidence": [],
                "next_discriminating_probe": "Probe exact route.",
                "revision": 1,
            },
        ],
        "causal_assessment": {
            "status": "proven",
            "causes": [
                {
                    "hypothesis_id": "H-route",
                    "role": "primary",
                    "support": "proven",
                    "evidence_refs": ["ev:route", "ev:probe-route"],
                }
            ],
            "unresolved_alternatives": [],
        },
        "evidence_refs": ["ev:route", "ev:account", "ev:probe-route"],
    }


def _hypothesis(state: dict[str, object], hypothesis_id: str) -> dict[str, object]:
    hypotheses = state["hypotheses"]
    assert isinstance(hypotheses, list)
    for hypothesis in hypotheses:
        assert isinstance(hypothesis, dict)
        if hypothesis.get("id") == hypothesis_id:
            return hypothesis
    raise AssertionError(hypothesis_id)


def test_action_outcome_unknown_side_effect_cannot_be_terminal_failed() -> None:
    schema = json.loads((ROOT / "contracts/action-outcome.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    outcome = {
        "schema_version": 1,
        "transport": "timed_out",
        "execution": "unknown",
        "side_effect": "unknown",
        "artifact_publication": "unknown",
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


def test_proven_root_cause_requires_real_independent_discriminating_evidence() -> None:
    assert validate_diagnostic_state(_diagnostic_state()) == []


def test_declared_proven_cannot_reference_missing_evidence() -> None:
    state = _diagnostic_state()
    causal = state["causal_assessment"]
    assert isinstance(causal, dict)
    causes = causal["causes"]
    assert isinstance(causes, list) and isinstance(causes[0], dict)
    causes[0]["evidence_refs"] = ["ev:missing", "ev:probe-route"]
    findings = validate_diagnostic_state(state)
    assert any("UNKNOWN_CAUSAL_EVIDENCE" in finding for finding in findings)
    assert any("PROVEN_EVIDENCE_NOT_BOUND_TO_HYPOTHESIS" in finding for finding in findings)


def test_correlated_evidence_is_not_independent_confirmation() -> None:
    state = _diagnostic_state()
    observations = state["observations"]
    probes = state["probes"]
    assert isinstance(observations, list) and isinstance(probes, list)
    assert isinstance(observations[0], dict) and isinstance(probes[1], dict)
    probes[1]["source_group"] = observations[0]["source_group"]
    findings = validate_diagnostic_state(state)
    assert any("PROVEN_WITHOUT_INDEPENDENT_CONFIRMATION" in finding for finding in findings)


def test_proven_requires_executed_probe_that_discriminates_winner() -> None:
    state = _diagnostic_state()
    probes = state["probes"]
    assert isinstance(probes, list) and isinstance(probes[1], dict)
    probes[1]["predictions"] = {"H-billing": "route-fails", "H-route": "route-fails"}
    findings = validate_diagnostic_state(state)
    assert any("PROVEN_WITHOUT_DISCRIMINATING_EVIDENCE" in finding for finding in findings)


def test_probe_selection_maximizes_pairwise_prediction_separation() -> None:
    state = _diagnostic_state()
    hypotheses = state["hypotheses"]
    probes = state["probes"]
    assert isinstance(hypotheses, list) and isinstance(probes, list)
    assert isinstance(hypotheses[0], dict) and isinstance(probes[1], dict)
    hypotheses[0]["status"] = "active"
    probes[1]["observed_outcome"] = None
    probes[1]["evidence_ref"] = None
    probes.append(
        {
            "id": "P-weak",
            "description": "Weak common probe.",
            "source_group": "weak",
            "predictions": {"H-billing": "same", "H-route": "same"},
            "observed_outcome": None,
            "evidence_ref": None,
        }
    )
    assert select_discriminating_probe(state) == "Probe exact routing independently."


def test_probe_selection_prefers_more_pairwise_separation_with_three_hypotheses() -> None:
    state = _diagnostic_state()
    hypotheses = state["hypotheses"]
    probes = state["probes"]
    assert isinstance(hypotheses, list) and isinstance(probes, list)
    assert isinstance(hypotheses[0], dict)
    hypotheses[0]["status"] = "active"
    hypotheses.append(
        {
            "id": "H-auth",
            "claim": "Authentication drift.",
            "status": "active",
            "supporting_evidence": [],
            "contradicting_evidence": [],
            "next_discriminating_probe": "Inspect auth.",
            "revision": 1,
        }
    )
    probes.clear()
    probes.extend(
        [
            {
                "id": "P-two",
                "description": "Separates one pair.",
                "source_group": "p2",
                "predictions": {"H-billing": "a", "H-route": "b"},
                "observed_outcome": None,
                "evidence_ref": None,
            },
            {
                "id": "P-three",
                "description": "Separates all hypotheses.",
                "source_group": "p3",
                "predictions": {"H-billing": "a", "H-route": "b", "H-auth": "c"},
                "observed_outcome": None,
                "evidence_ref": None,
            },
        ]
    )
    assert select_discriminating_probe(state) == "Separates all hypotheses."


def test_probe_selection_returns_none_without_two_unresolved_or_discriminating_candidates() -> None:
    state = _diagnostic_state()
    route = _hypothesis(state, "H-route")
    route["status"] = "disproven"
    assert select_discriminating_probe(state) is None

    state = _diagnostic_state()
    billing = _hypothesis(state, "H-billing")
    billing["status"] = "active"
    probes = state["probes"]
    assert isinstance(probes, list)
    probes[:] = [probes[0]]
    assert select_discriminating_probe(state) is None


def test_probe_result_transitions_cover_support_inconclusive_and_invalid_paths() -> None:
    state = _diagnostic_state()
    billing = _hypothesis(state, "H-billing")
    billing["status"] = "active"
    supported = record_probe_result(state, "H-billing", "ev:new", "supports")
    assert _hypothesis(supported, "H-billing")["status"] == "supported"
    inconclusive = record_probe_result(state, "H-billing", "ev:inc", "inconclusive")
    assert _hypothesis(inconclusive, "H-billing")["status"] == "unknown"
    with pytest.raises(DiagnosticReasoningError, match="unsupported probe verdict"):
        record_probe_result(state, "H-billing", "ev:x", "invalid")  # type: ignore[arg-type]
    with pytest.raises(DiagnosticReasoningError, match="non-empty"):
        record_probe_result(state, "H-billing", "", "supports")


def test_probe_evidence_cannot_support_and_contradict_same_revision() -> None:
    state = _diagnostic_state()
    billing = _hypothesis(state, "H-billing")
    billing["status"] = "active"
    billing["supporting_evidence"] = ["ev:account"]
    with pytest.raises(DiagnosticReasoningError, match="support and contradict"):
        record_probe_result(state, "H-billing", "ev:account", "contradicts")


def test_reopen_requires_disproven_hypothesis_valid_revision_and_new_evidence() -> None:
    state = _diagnostic_state()
    route = _hypothesis(state, "H-route")
    with pytest.raises(DiagnosticReasoningError, match="only a disproven"):
        reopen_hypothesis(state, "H-route", "ev:new", next_discriminating_probe="Probe.")
    with pytest.raises(DiagnosticReasoningError, match="requires evidence"):
        reopen_hypothesis(state, "H-billing", "", next_discriminating_probe="Probe.")
    billing = _hypothesis(state, "H-billing")
    billing["revision"] = 0
    with pytest.raises(DiagnosticReasoningError, match="positive integer"):
        reopen_hypothesis(state, "H-billing", "ev:new", next_discriminating_probe="Probe.")


def test_remediation_paths_require_evidence_and_do_not_resurrect_disproven() -> None:
    state = _diagnostic_state()
    with pytest.raises(DiagnosticReasoningError, match="requires evidence"):
        record_remediation_result(
            state,
            "H-route",
            "",
            predicted_postcondition="Route recovers.",
            status="verified",
        )
    verified = record_remediation_result(
        state,
        "H-route",
        "ev:repair",
        predicted_postcondition="Route recovers.",
        status="verified",
    )
    assert _hypothesis(verified, "H-route")["status"] == "supported"
    partial = record_remediation_result(
        state,
        "H-route",
        "ev:partial",
        predicted_postcondition="Route recovers.",
        status="partial",
    )
    assert _hypothesis(partial, "H-route")["status"] == "unknown"
    with pytest.raises(DiagnosticReasoningError, match="silently resurrect"):
        record_remediation_result(
            state,
            "H-billing",
            "ev:repair",
            predicted_postcondition="Billing succeeds.",
            status="verified",
        )


def test_semantic_validator_rejects_duplicate_ids_incomplete_probe_and_multiple_primary() -> None:
    state = _diagnostic_state()
    observations = state["observations"]
    hypotheses = state["hypotheses"]
    probes = state["probes"]
    causal = state["causal_assessment"]
    assert isinstance(observations, list) and isinstance(hypotheses, list)
    assert isinstance(probes, list) and isinstance(causal, dict)
    observations.append(deepcopy(observations[0]))
    hypotheses.append(deepcopy(hypotheses[1]))
    probes.append(
        {
            "id": "P-incomplete",
            "description": "Broken execution record.",
            "source_group": "broken",
            "predictions": {"H-billing": "a", "H-route": "b"},
            "observed_outcome": "a",
            "evidence_ref": None,
        }
    )
    causes = causal["causes"]
    assert isinstance(causes, list)
    causes.append(
        {
            "hypothesis_id": "H-route",
            "role": "primary",
            "support": "proven",
            "evidence_refs": ["ev:route", "ev:probe-route"],
        }
    )
    findings = validate_diagnostic_state(state)
    assert any("DUPLICATE_OBSERVATION_ID" in finding for finding in findings)
    assert any("DUPLICATE_HYPOTHESIS_ID" in finding for finding in findings)
    assert any("INCOMPLETE_PROBE_EVIDENCE" in finding for finding in findings)
    assert any("MULTIPLE_PRIMARY_CAUSES" in finding for finding in findings)


def test_transition_rejects_silent_reopen_missing_reopen_and_old_evidence() -> None:
    previous = _diagnostic_state()
    current = deepcopy(previous)
    billing = _hypothesis(current, "H-billing")
    billing["status"] = "active"
    findings = validate_diagnostic_transition(previous, current)
    assert any("SILENTLY_REOPENED" in finding for finding in findings)

    current = deepcopy(previous)
    billing = _hypothesis(current, "H-billing")
    billing["status"] = "active"
    billing["revision"] = 2
    findings = validate_diagnostic_transition(previous, current)
    assert any("MISSING_REOPEN_EVIDENCE" in finding for finding in findings)

    current = deepcopy(previous)
    billing = _hypothesis(current, "H-billing")
    billing["status"] = "active"
    billing["revision"] = 2
    billing["reopen"] = {"from_revision": 1, "evidence_ref": "ev:account"}
    findings = validate_diagnostic_transition(previous, current)
    assert any("REUSED_OLD_EVIDENCE" in finding for finding in findings)


def test_validator_handles_invalid_root_shapes_without_crashing() -> None:
    assert validate_diagnostic_state({"hypotheses": "bad"}) == ["hypotheses must be an array"]
    state = _diagnostic_state()
    state["causal_assessment"] = "bad"
    assert any("causal_assessment must be an object" in finding for finding in validate_diagnostic_state(state))

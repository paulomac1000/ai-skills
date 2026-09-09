from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "contracts" / "agentic-governance.schema.json").read_text(encoding="utf-8"))


def _validator(definition: str) -> Draft202012Validator:
    return Draft202012Validator({"$ref": f"#/$defs/{definition}", "$defs": SCHEMA["$defs"]})


def _outcome(**overrides: object) -> dict:
    value = {
        "schema_version": 1,
        "transport": "succeeded",
        "execution": "succeeded",
        "side_effect": "confirmed",
        "artifact": "none",
        "verification": "passed",
        "disposition": "completed",
        "safe_to_retry": "no",
    }
    value.update(overrides)
    return value


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"side_effect": "unknown", "disposition": "completed"}, "ambiguous side effect"),
        ({"artifact": "missing"}, "required artifact missing"),
        ({"verification": "stale"}, "stale evidence"),
    ],
)
def test_completed_outcome_rejects_unproven_completion(overrides: dict, reason: str) -> None:
    del reason
    with pytest.raises(ValidationError):
        _validator("action_outcome").validate(_outcome(**overrides))


def _receipt() -> dict:
    return {
        "schema_version": 1,
        "candidate": {"source_revision": "a" * 40},
        "bootstrap": {"policy_revision": "policy-1", "declared_dependencies_only": True},
        "test_corpus": {
            "policy_revision": "corpus-1",
            "discovered_files": 34,
            "executed_files": 34,
            "excluded_files": [],
            "discovery_drift": 0,
        },
        "execution_integrity": {
            "cancelled": 0,
            "pending": 0,
            "unhandled_exceptions": 0,
            "unraisable": 0,
            "blocking_warnings": 0,
            "leaked_async_work": 0,
        },
        "isolation": {"production_effective_state_touched": False},
        "verdict": "pass",
    }


def test_historical_34_23_test_corpus_shape_cannot_pass() -> None:
    receipt = _receipt()
    receipt["test_corpus"]["executed_files"] = 23
    receipt["test_corpus"]["discovery_drift"] = 11
    with pytest.raises(ValidationError):
        _validator("verification_receipt").validate(receipt)


@pytest.mark.parametrize(
    "field",
    ["cancelled", "pending", "unhandled_exceptions", "unraisable", "blocking_warnings"],
)
def test_pass_rejects_execution_integrity_failures(field: str) -> None:
    receipt = _receipt()
    receipt["execution_integrity"][field] = 1
    with pytest.raises(ValidationError):
        _validator("verification_receipt").validate(receipt)


def test_pass_rejects_unknown_async_leak_state() -> None:
    receipt = _receipt()
    receipt["execution_integrity"]["leaked_async_work"] = "unknown"
    with pytest.raises(ValidationError):
        _validator("verification_receipt").validate(receipt)


def test_validation_cannot_touch_production_effective_state() -> None:
    receipt = _receipt()
    receipt["isolation"]["production_effective_state_touched"] = True
    with pytest.raises(ValidationError):
        _validator("verification_receipt").validate(receipt)


def test_ephemeral_distribution_requires_cleanup() -> None:
    install = {
        "schema_version": 1,
        "skill_id": "qa-change-verifier",
        "source": "github:owner/repo",
        "source_revision": "b" * 40,
        "distribution_mode": "EPHEMERAL",
        "install_scope": ".agents/generated/qa-change-verifier",
        "managed_by": "skill-installer",
        "update_policy": "pinned",
        "cleanup_policy": "none",
    }
    with pytest.raises(ValidationError):
        _validator("skill_installation").validate(install)


def test_delegation_preserves_planning_and_execution_bases() -> None:
    contract = {
        "schema_version": 1,
        "task_id": "task-1",
        "planning_base": {"repository": "owner/repo", "ref": "main", "revision": "a" * 40},
        "execution_base": {"repository": "owner/repo", "ref": "branch", "revision": "b" * 40},
        "base_relationship": "descendant",
        "admission": "BASE_ADVANCED_COMPATIBLE",
        "plan_revision": "plan-1",
        "required_capabilities": ["repository.write"],
        "expected_outputs": ["published revision"],
        "authority": ["repository.write:owner/repo"],
    }
    _validator("delegation_contract").validate(contract)
    assert contract["planning_base"]["revision"] != contract["execution_base"]["revision"]


def test_intent_ledger_keeps_superseded_requirements_auditable() -> None:
    ledger = {
        "schema_version": 1,
        "ledger_id": "ledger-1",
        "task_id": "task-1",
        "revision": 2,
        "requirements": [
            {"id": "r1", "statement": "Do not publish", "origin": "user_explicit", "kind": "constraint", "state": "superseded", "superseded_by": "r2"},
            {"id": "r2", "statement": "Publish only to the feature branch", "origin": "clarified", "kind": "constraint", "state": "active"}
        ]
    }
    _validator("intent_ledger").validate(ledger)


def test_diagnostic_state_keeps_disproven_hypothesis_distinct_from_observation() -> None:
    state = {
        "schema_version": 1,
        "observations": [{"id": "o1", "claim": "HTTP returned 403", "evidence_ref": "probe:1", "classification": "OBSERVATION"}],
        "hypotheses": [{"id": "h1", "claim": "credential is invalid", "status": "disproven", "supporting_evidence": [], "contradicting_evidence": ["probe:2"], "next_discriminating_probe": None}],
        "root_cause": {"status": "unknown", "hypothesis_id": None}
    }
    _validator("diagnostic_state").validate(state)
    assert state["observations"][0]["claim"] == "HTTP returned 403"


def test_audit_can_record_dispatched_unknown_side_effect_without_false_success() -> None:
    event = {
        "schema_version": 1,
        "event_id": "event-1",
        "correlation_id": "correlation-1",
        "timestamp": "2026-09-10T00:00:00Z",
        "actor": {"principal": "agent"},
        "action": {"capability": "send", "operation": "create", "target": "resource:1"},
        "outcome": _outcome(transport="timed_out", execution="unknown", side_effect="unknown", verification="not_run", disposition="reconcile_required", safe_to_retry="unknown")
    }
    _validator("audit_event").validate(event)

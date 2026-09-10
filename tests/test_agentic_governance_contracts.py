from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
if str(CONTRACTS) not in sys.path:
    sys.path.insert(0, str(CONTRACTS))

from validate_verification_receipt import validate_receipt, validate_receipt_semantics  # noqa: E402


def _load(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def _validator(name: str) -> Draft202012Validator:
    schema = _load(name)
    resources = []
    for path in CONTRACTS.glob("*.schema.json"):
        candidate = _load(path.name)
        if "$id" in candidate:
            resources.append((candidate["$id"], Resource.from_contents(candidate)))
    return Draft202012Validator(schema, registry=Registry().with_resources(resources))


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
            "accounted_files": 34,
            "discovery_drift": 0,
            "execution_evidence": "observed",
            "completeness": "complete",
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
        "evidence_refs": ["evidence:repository-run"],
        "verdict": "pass",
    }


def test_valid_pass_receipt_is_schema_and_semantically_complete() -> None:
    receipt = _receipt()
    _validator("verification-receipt.schema.json").validate(receipt)
    assert validate_receipt(receipt) == []


def test_historical_34_23_test_corpus_shape_cannot_pass() -> None:
    receipt = _receipt()
    receipt["test_corpus"]["executed_files"] = 23
    receipt["test_corpus"]["accounted_files"] = 23
    receipt["test_corpus"]["discovery_drift"] = 11
    with pytest.raises(ValidationError):
        _validator("verification-receipt.schema.json").validate(receipt)


def test_zero_execution_cannot_pass_for_nonempty_discovery_even_with_zero_drift() -> None:
    receipt = _receipt()
    receipt["test_corpus"]["executed_files"] = 0
    receipt["test_corpus"]["accounted_files"] = 0
    receipt["test_corpus"]["discovery_drift"] = 0
    with pytest.raises(ValidationError):
        _validator("verification-receipt.schema.json").validate(receipt)


def test_semantic_validator_recomputes_accounted_test_files() -> None:
    receipt = _receipt()
    receipt["test_corpus"]["executed_files"] = 23
    receipt["test_corpus"]["accounted_files"] = 34
    receipt["test_corpus"]["discovery_drift"] = 0
    _validator("verification-receipt.schema.json").validate(receipt)
    findings = validate_receipt_semantics(receipt)
    assert any("accounted_files" in finding for finding in findings)


@pytest.mark.parametrize(
    "field",
    ["cancelled", "pending", "unhandled_exceptions", "unraisable", "blocking_warnings"],
)
def test_verification_pass_rejects_execution_integrity_failures(field: str) -> None:
    receipt = _receipt()
    receipt["execution_integrity"][field] = 1
    with pytest.raises(ValidationError):
        _validator("verification-receipt.schema.json").validate(receipt)


def test_verification_pass_rejects_unknown_async_leak_state() -> None:
    receipt = _receipt()
    receipt["execution_integrity"]["leaked_async_work"] = "unknown"
    with pytest.raises(ValidationError):
        _validator("verification-receipt.schema.json").validate(receipt)


def test_validation_cannot_touch_production_effective_state() -> None:
    receipt = _receipt()
    receipt["isolation"]["production_effective_state_touched"] = True
    with pytest.raises(ValidationError):
        _validator("verification-receipt.schema.json").validate(receipt)


def _ledger() -> dict:
    return {
        "schema_version": 1,
        "ledger_id": "ledger-1",
        "task_id": "task-1",
        "intent_revision": 3,
        "goal": "Implement and deploy the requested change",
        "requirements": [
            {
                "id": "R1",
                "statement": "Implement code",
                "status": "satisfied",
                "source": "user",
                "source_revision": "user-turn-1",
                "mandatory": True,
                "superseded_by": None,
                "superseded_by_authority": None,
                "evidence_refs": ["git:commit-a"],
            },
            {
                "id": "R2",
                "statement": "Deploy app A",
                "status": "pending",
                "source": "user",
                "source_revision": "user-turn-1",
                "mandatory": True,
                "superseded_by": None,
                "superseded_by_authority": None,
                "evidence_refs": [],
            },
        ],
        "required_capabilities": ["repository.write", "deployment.execute"],
        "required_execution_methods": ["protected-release"],
        "acceptance_criteria": ["code verified", "deployed runtime verified"],
        "prohibitions": ["do not mutate service B"],
        "authorized_operations": ["repository.write:app-a", "deploy:app-a"],
        "scope": {
            "in_scope_targets": ["app-a"],
            "protected_or_out_of_scope_targets": ["service-b"],
            "allowed_side_effect_classes": ["repository-write", "deploy"],
        },
        "open_questions": [],
        "unresolved_conflicts": [],
    }


def test_intent_ledger_preserves_pending_required_deployment() -> None:
    ledger = _ledger()
    _validator("intent-ledger.schema.json").validate(ledger)
    assert [item["id"] for item in ledger["requirements"] if item["status"] == "pending"] == ["R2"]


def test_satisfied_requirement_requires_evidence() -> None:
    ledger = _ledger()
    ledger["requirements"][0]["evidence_refs"] = []
    with pytest.raises(ValidationError):
        _validator("intent-ledger.schema.json").validate(ledger)


def test_superseded_requirement_requires_new_requirement_and_authority_reference() -> None:
    ledger = _ledger()
    ledger["requirements"][1].update({"status": "superseded", "superseded_by": None, "superseded_by_authority": None})
    with pytest.raises(ValidationError):
        _validator("intent-ledger.schema.json").validate(ledger)


def test_delegation_records_both_bases_and_explicit_advanced_admission() -> None:
    contract = {
        "schema_version": 1,
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "intent_revision": 3,
        "planning_base": {"repository": "owner/repo", "ref": "main", "revision": "a" * 40},
        "execution_base": {"repository": "owner/repo", "ref": "feature", "revision": "b" * 40},
        "base_relationship": "descendant",
        "admission": "BASE_ADVANCED_COMPATIBLE",
        "plan_revision": "plan-2",
        "required_capabilities": ["repository.write"],
        "expected_outputs": ["published-revision"],
        "authority": ["repository.write:owner/repo"],
        "resource_domains": ["repo:owner/repo"],
        "requires_work": True,
        "revalidated_assumptions": ["working set unchanged upstream"],
        "result": None,
    }
    _validator("delegation-contract.schema.json").validate(contract)
    assert contract["planning_base"]["revision"] != contract["execution_base"]["revision"]


def test_diagnostic_state_preserves_multiple_contributing_causes() -> None:
    state = {
        "schema_version": 1,
        "observations": [
            {
                "id": "O1",
                "claim": "action-specific probe failed",
                "evidence_ref": "probe:1",
                "classification": "OBSERVATION",
            }
        ],
        "hypotheses": [
            {
                "id": "H1",
                "claim": "runtime binding is stale",
                "status": "supported",
                "supporting_evidence": ["probe:2"],
                "contradicting_evidence": [],
                "next_discriminating_probe": None,
            },
            {
                "id": "H2",
                "claim": "provider is degraded",
                "status": "supported",
                "supporting_evidence": ["probe:3"],
                "contradicting_evidence": [],
                "next_discriminating_probe": None,
            },
        ],
        "causal_assessment": {
            "status": "partial",
            "causes": [
                {"hypothesis_id": "H1", "role": "contributing", "support": "supported", "evidence_refs": ["probe:2"]},
                {"hypothesis_id": "H2", "role": "contributing", "support": "supported", "evidence_refs": ["probe:3"]},
            ],
            "unresolved_alternatives": [],
        },
        "effective_config_provenance": [],
        "evidence_refs": ["probe:1", "probe:2", "probe:3"],
    }
    _validator("diagnostic-state.schema.json").validate(state)
    assert len(state["causal_assessment"]["causes"]) == 2

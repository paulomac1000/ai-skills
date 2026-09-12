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

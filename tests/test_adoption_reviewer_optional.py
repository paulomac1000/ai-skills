from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from contracts import validate_adoption


def test_request_changes_schema_does_not_require_fictitious_reviewer() -> None:
    schema = validate_adoption._load_json(validate_adoption.DEFAULT_SCHEMA)
    decision_schema = schema["properties"]["decision"]
    errors = list(
        Draft202012Validator(decision_schema).iter_errors(
            {"status": "request-changes", "rationale": "blocking gaps remain"}
        )
    )
    assert errors == []


def test_approve_schema_still_requires_reviewer_and_acceptance_authority() -> None:
    schema = validate_adoption._load_json(validate_adoption.DEFAULT_SCHEMA)
    conditional = {"type": "object", "allOf": schema["allOf"]}
    errors = list(
        Draft202012Validator(conditional).iter_errors(
            {"decision": {"status": "approve", "rationale": "ready"}}
        )
    )
    messages = [error.message for error in errors]
    assert any("acceptance_authority" in message for message in messages)
    assert any("reviewer" in message for message in messages)


def test_structural_request_changes_validator_accepts_missing_reviewer(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        validate_adoption,
        "_manifest",
        lambda *_args, **_kwargs: {"version": "1.2.0", "maturity": "stable"},
    )
    monkeypatch.setattr(validate_adoption, "_catalog_rules", lambda *_args, **_kwargs: set())
    for name in (
        "_validate_applicability",
        "_validate_compatibility",
        "_validate_artifacts",
        "_validate_mcp_extension",
    ):
        monkeypatch.setattr(validate_adoption, name, lambda *_args, **_kwargs: None)

    assessment = {
        "schema_version": 1,
        "verification_mode": "structural-attestation",
        "assessment_id": "assessment-1",
        "generated_at": "2026-08-19T12:00:00Z",
        "prepared_by": [{"provider": "github", "login": "author", "id": 1}],
        "repository": {
            "name": "owner/repository",
            "revision": "1" * 40,
            "source_branch": "agent/work",
        },
        "skill": {"name": "mcp-server-architect", "version": "1.2.0", "maturity": "stable"},
        "scope": {"included": ["runtime"], "excluded": [], "exclusion_rationale": []},
        "behavior": {"preserved": ["safe reads"], "intentionally_changed": [], "removed_legacy": []},
        "rollback": {
            "trigger_conditions": ["regression"],
            "procedure": ["restore previous revision"],
            "data_recovery": ["none required"],
        },
        "residual_risks": [
            {
                "risk": "provider evidence pending",
                "owner": "maintainers",
                "mitigation": "run hosted verification",
                "blocking": True,
            }
        ],
        "decision": {"status": "request-changes", "rationale": "provider evidence pending"},
    }
    findings = validate_adoption.validate_document(
        assessment,
        {},
        tmp_path,
        require_approval=False,
        as_of=date(2026, 8, 19),
        schema={"type": "object"},
        repository_root=tmp_path,
    )
    assert not any(finding.location.startswith("decision.reviewer") for finding in findings)

"""Regressions for contract hardening transferred from the provider-validation branch."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_read_capability_is_naturally_idempotent_without_retry_key() -> None:
    schema = json.loads((ROOT / "contracts/capability-manifest.schema.json").read_text(encoding="utf-8"))
    manifest = {
        "schema_version": 1,
        "id": "inventory.list",
        "name": "List inventory",
        "description": "Lists bounded inventory metadata.",
        "operation_kind": "read",
        "risk": "low",
        "determinism": "environment-dependent",
        "latency": "interactive",
        "impact": "none",
        "active_state": "active",
        "retryable": True,
        "idempotent": True,
        "reversible": False,
        "requires_confirmation": False,
        "idempotency_key_required": False,
        "authorization_scopes": [],
        "concurrency": {"scope": "principal", "limit": 4},
        "max_response_bytes": 65536,
    }
    validator = Draft202012Validator(schema)
    assert list(validator.iter_errors(manifest)) == []
    manifest["idempotent"] = False
    assert list(validator.iter_errors(manifest))


def test_local_reusable_inherits_workflow_write_permissions(tmp_path: Path) -> None:
    tools = ROOT / "skills/ci-cd-architect/tools"
    sys.path.insert(0, str(tools))
    import check_github_actions_policy as auditor

    workflow = tmp_path / ".github/workflows/caller.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        """name: caller
on: workflow_dispatch
permissions:
  packages: write
jobs:
  publish:
    uses: ./.github/workflows/reusable.yml
""",
        encoding="utf-8",
    )
    findings = auditor._privileged_local_reusable_findings(workflow, tmp_path)
    assert any("write-enabled local reusable workflow" in item.message for item in findings)


def test_python_generator_rejects_lexical_symlink_parent(tmp_path: Path) -> None:
    generator = _load(
        ROOT / "skills/mcp-server-architect/tools/generate_python_server.py",
        "transfer_followup_python_generator",
    )
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks or reparse points"):
        generator.generate_project(
            linked_parent / "generated",
            "inventory_server",
            "Inventory Server",
        )


def test_structural_request_changes_schema_does_not_require_reviewer() -> None:
    schema = json.loads((ROOT / "contracts/adoption-assessment.schema.json").read_text(encoding="utf-8"))
    decision_schema = {"$defs": schema["$defs"], **schema["properties"]["decision"]}
    errors = list(
        Draft202012Validator(decision_schema).iter_errors(
            {"status": "request-changes", "rationale": "blocking gaps remain"}
        )
    )
    assert errors == []


def test_approve_schema_still_requires_reviewer_and_acceptance_authority() -> None:
    schema = json.loads((ROOT / "contracts/adoption-assessment.schema.json").read_text(encoding="utf-8"))
    messages = [
        error.message
        for error in Draft202012Validator(schema).iter_errors(
            {"decision": {"status": "approve", "rationale": "ready"}}
        )
    ]
    assert any("reviewer" in message for message in messages)
    assert any("acceptance_authority" in message for message in messages)


def test_generic_assessment_template_has_exact_test_case_placeholder() -> None:
    template = (ROOT / "contracts/adoption-assessment.yaml.template").read_text(encoding="utf-8")
    assert "version: REPLACE_WITH_SKILL_VERSION" in template
    assert "test_case: tests/test_contract.py::test_REPLACE_WITH_EXACT_TEST" in template
    assert "reviewer:" not in template

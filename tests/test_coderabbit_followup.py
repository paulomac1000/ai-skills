"""Regression tests for executable findings from the exact-head bot review."""

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


def test_consumer_policy_identity_must_match_invoked_tool_name() -> None:
    engine = _load(
        ROOT / "skills/mcp-server-consumer/tools/decision_engine.py",
        "review_followup_decision_engine",
    )
    identity = engine.CapabilityIdentity(
        server_identity="server:inventory",
        tool_name="inventory.list",
        tool_schema_hash="sha256:" + "1" * 64,
        manifest_version="1",
    )
    policy = engine.TrustedCapabilityPolicy(
        binding=engine.TrustedPolicyBinding(
            identity=identity,
            source="reviewed-policy:sha256:" + "2" * 64,
        ),
        risk=engine.Risk.READ,
    )
    with pytest.raises(ValueError, match="invoked capability name"):
        engine.infer_capability_profile(
            "inventory.delete",
            {},
            identity=identity,
            trusted_policy=policy,
        )


def test_capability_schema_separates_lifecycle_from_operation_kind() -> None:
    schema = json.loads(
        (ROOT / "contracts/capability-manifest.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert schema["properties"]["operation_kind"]["enum"] == [
        "read",
        "write",
        "destructive",
    ]
    assert schema["properties"]["active_state"]["enum"] == [
        "active",
        "inactive",
        "deprecated",
    ]
    approval = schema["properties"]["approval"]["properties"]["binds"]
    assert "expires-at" in approval["items"]["enum"]
    assert any(
        condition.get("contains", {}).get("const") == "expires-at"
        for condition in approval["allOf"]
    )


def test_read_schema_is_naturally_idempotent_and_retry_is_opt_in() -> None:
    schema = json.loads(
        (ROOT / "contracts/capability-manifest.schema.json").read_text(
            encoding="utf-8"
        )
    )
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


def test_generated_manifests_are_active_and_read_flags_fail_closed() -> None:
    capability_dir = (
        ROOT
        / "skills/mcp-server-architect/tools/python-template/src/"
        "__PACKAGE__/capabilities"
    )
    for path in capability_dir.glob("*.json.template"):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["active_state"] == "active"
        if manifest["operation_kind"] == "read":
            assert manifest["impact"] == "none"
            assert manifest["retryable"] is False
            assert manifest["idempotent"] is True
            for field in (
                "reversible",
                "requires_confirmation",
                "idempotency_key_required",
            ):
                assert manifest[field] is False
        if manifest["requires_confirmation"]:
            assert "expires-at" in manifest["approval"]["binds"]


def test_dotnet_projection_preserves_lifecycle_and_expiry_binding() -> None:
    adapter = (
        ROOT
        / "skills/mcp-server-architect/tools/dotnet-template/src/"
        "__NAMESPACE__.Mcp.Server/CanonicalCapabilityManifest.cs.template"
    ).read_text(encoding="utf-8")
    assert "var activeState = manifest.ActiveState switch" in adapter
    assert '"inactive" => "inactive"' in adapter
    assert '"deprecated" => "deprecated"' in adapter
    assert '"expires-at"' in adapter
    assert "only active capabilities may be registered" in adapter
    assert 'operationKind == "read" ? "read" : "write"' not in adapter


def test_windows_atomic_publication_normalizes_existing_target() -> None:
    generator = (
        ROOT / "skills/mcp-server-architect/tools/generate_dotnet_server.py"
    ).read_text(encoding="utf-8")
    windows = generator.split('if operating_system == "Windows":', 1)[1]
    windows = windows.split("raise RuntimeError", 1)[0]
    assert "except FileExistsError as exc:" in windows
    assert '"generation target already exists"' in windows


def test_release_template_lowercases_ghcr_identity_and_attestation_subject() -> None:
    template = (
        ROOT / "skills/ci-cd-architect/templates/publish.yml.template"
    ).read_text(encoding="utf-8")
    assert 'repository="ghcr.io/${GITHUB_REPOSITORY,,}"' in template
    assert "subject_name=$repository" in template
    assert "subject-name: ${{ steps.push.outputs.subject_name }}" in template
    assert "docker push --all-tags" not in template


def test_privileged_local_reusable_workflow_guard_is_executable() -> None:
    auditor = (
        ROOT
        / "skills/ci-cd-architect/tools/check_github_actions_policy.py"
    ).read_text(encoding="utf-8")
    assert "_privileged_local_reusable_findings" in auditor
    assert "write-enabled local reusable workflow" in auditor
    assert "recursively audited" in auditor
    assert 'document.get("permissions")' in auditor
    assert "_impl._permission_has_write(effective_permissions)" in auditor


def test_privileged_local_reusable_inherits_workflow_write_permissions(
    tmp_path: Path,
) -> None:
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
        "review_followup_python_generator",
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


def test_manifest_validator_handles_non_string_approval_bindings(
    tmp_path: Path,
) -> None:
    validator = _load(
        ROOT / "contracts/validate_capability_manifest.py",
        "review_followup_manifest_validator",
    )
    manifest = {
        "schema_version": 1,
        "id": "inventory.put",
        "name": "Put inventory",
        "description": "Updates bounded inventory metadata.",
        "operation_kind": "write",
        "risk": "high",
        "determinism": "environment-dependent",
        "latency": "interactive",
        "impact": "external",
        "active_state": "active",
        "retryable": False,
        "idempotent": False,
        "reversible": False,
        "requires_confirmation": True,
        "idempotency_key_required": False,
        "authorization_scopes": ["inventory:write"],
        "approval": {
            "enforcement": "server-side",
            "record_required": True,
            "record_ttl_seconds": 60,
            "binds": [
                "principal",
                {"invalid": True},
                "capability",
                "target",
                "arguments-digest",
                "expires-at",
            ],
        },
        "concurrency": {"scope": "principal-target", "limit": 1},
        "max_response_bytes": 65536,
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    findings = validator.validate_manifest(path)
    assert findings


def test_lock_schema_and_validator_reject_path_and_name_ambiguity() -> None:
    schema = json.loads(
        (ROOT / "contracts/ai-skills-lock.schema.json").read_text(
            encoding="utf-8"
        )
    )
    pattern = schema["properties"]["skills"]["additionalProperties"][
        "properties"
    ]["normative_entrypoint"]["pattern"]
    assert ".." not in pattern
    validator = (
        ROOT / "contracts/validate_skills_lock.py"
    ).read_text(encoding="utf-8")
    assert "SKILL_NAME" in validator
    assert "must be a non-empty string" in validator
    assert "cannot inspect normative entrypoint" in validator


def test_ecosystem_readme_governance_is_explicit_afds_v2() -> None:
    document = (
        ROOT
        / "skills/afds-doc-writer/references/ecosystem-readme-governance.md"
    ).read_text(encoding="utf-8")
    assert document.startswith("---\nafds_schema_version: 2\n")
    assert "verification:\n  kind: command\n  value:" in document

"""Regression tests for provider-neutral adoption and MCP manifest hardening."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from contracts.validate_capability_manifest import validate_manifest
from contracts.validate_evidence_provider import validate_record
from contracts.validate_skills_lock import validate_lock

ROOT = Path(__file__).resolve().parents[1]
FULL_SHA = "1" * 40
DIGEST = "sha256:" + "2" * 64


def _write_yaml(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    return path


def _capability(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
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
        "retryable": False,
        "idempotent": True,
        "reversible": False,
        "requires_confirmation": False,
        "idempotency_key_required": False,
        "authorization_scopes": [],
        "concurrency": {"scope": "principal", "limit": 4, "queue_limit": 8},
        "max_response_bytes": 65536,
        "protocol_revisions": ["2026-07-28"],
    }
    value.update(overrides)
    return value


def test_capability_schema_accepts_explicit_read_contract(tmp_path: Path) -> None:
    manifest = _write_yaml(tmp_path / "capability.yaml", _capability())
    assert validate_manifest(manifest) == []


def test_retryable_read_does_not_require_idempotency_key(tmp_path: Path) -> None:
    manifest = _write_yaml(
        tmp_path / "read.yaml",
        _capability(retryable=True),
    )
    assert validate_manifest(manifest) == []


def test_write_retry_flags_require_explicit_rationales(tmp_path: Path) -> None:
    manifest = _write_yaml(
        tmp_path / "write.yaml",
        _capability(
            operation_kind="write",
            impact="external",
            risk="high",
            authorization_scopes=["inventory:write"],
            retryable=True,
            idempotent=True,
            idempotency_key_required=True,
        ),
    )
    findings = validate_manifest(manifest)
    assert any("retryable_rationale" in finding for finding in findings)
    assert any("idempotent_rationale" in finding for finding in findings)


def test_confirmation_metadata_requires_server_approval_record(tmp_path: Path) -> None:
    manifest = _write_yaml(
        tmp_path / "destructive.yaml",
        _capability(
            operation_kind="destructive",
            impact="external",
            risk="critical",
            authorization_scopes=["inventory:delete"],
            requires_confirmation=True,
        ),
    )
    findings = validate_manifest(manifest)
    assert any("approval" in finding for finding in findings)


def _evidence_record(profile: str, quality: str, provider_kind: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "profile": profile,
        "quality_level": quality,
        "provider": {"kind": provider_kind, "name": "test-provider"},
        "repository": "example/service",
        "revision": FULL_SHA,
        "execution": {
            "id": "run-1",
            "lane": "python-compatibility",
            "command": "python -m pytest",
            "started_at": "2026-08-06T18:00:00Z",
            "finished_at": "2026-08-06T18:01:00Z",
        },
        "result": "passed",
        "evidence": [{"kind": "report", "identity": "pytest.xml", "digest": DIGEST}],
    }


def test_local_structural_evidence_cannot_approve_l2(tmp_path: Path) -> None:
    record = _write_yaml(
        tmp_path / "evidence.yaml",
        _evidence_record("local-structural", "executed-local", "local-structural"),
    )
    findings = validate_record(record, target_level="L2")
    assert any("cannot approve L2" in finding for finding in findings)


def test_hosted_provider_can_supply_l2_exact_sha_evidence(tmp_path: Path) -> None:
    record = _write_yaml(
        tmp_path / "evidence.yaml",
        _evidence_record("hosted-provider", "provider-backed-exact-sha", "gitlab-ci"),
    )
    assert validate_record(record, target_level="L2") == []


def test_sensitive_profile_escalates_to_independent_release(tmp_path: Path) -> None:
    record = _write_yaml(
        tmp_path / "evidence.yaml",
        _evidence_record("hosted-provider", "provider-backed-exact-sha", "azure-pipelines"),
    )
    findings = validate_record(
        record,
        target_level="L2",
        deployment_profiles=frozenset({"sensitive"}),
    )
    assert any("independent-release" in finding for finding in findings)


def test_skill_lock_validates_version_entrypoint_revision_and_digest(tmp_path: Path) -> None:
    skill = tmp_path / "skills/example"
    standard = skill / "STANDARD.md"
    standard.parent.mkdir(parents=True)
    standard.write_text("# Example standard\n", encoding="utf-8")
    _write_yaml(
        skill / "manifest.yaml",
        {"version": "1.2.0", "normative_entrypoint": "STANDARD.md"},
    )
    digest = "sha256:" + hashlib.sha256(standard.read_bytes()).hexdigest()
    lock = _write_yaml(
        tmp_path / "ai-skills.lock.yaml",
        {
            "schema_version": 1,
            "repository": "paulomac1000/ai-skills",
            "revision": FULL_SHA,
            "skills": {
                "example": {
                    "version": "1.2.0",
                    "revision": FULL_SHA,
                    "normative_entrypoint": "skills/example/STANDARD.md",
                    "content_digest": digest,
                }
            },
        },
    )
    assert validate_lock(lock, skills_root=tmp_path) == []


def test_skill_lock_rejects_moving_revision_and_cross_skill_entrypoint(tmp_path: Path) -> None:
    lock = _write_yaml(
        tmp_path / "ai-skills.lock.yaml",
        {
            "schema_version": 1,
            "repository": "paulomac1000/ai-skills",
            "revision": "main",
            "skills": {
                "example": {
                    "version": "1.2.0",
                    "revision": FULL_SHA,
                    "normative_entrypoint": "skills/other/STANDARD.md",
                }
            },
        },
    )
    findings = validate_lock(lock)
    assert any("full commit SHA" in finding or "does not match" in finding for finding in findings)
    assert any("locked skill" in finding for finding in findings)


def test_mcp_runtime_scopes_are_not_conflated() -> None:
    manifest = yaml.safe_load(
        (ROOT / "skills/mcp-server-architect/manifest.yaml").read_text(encoding="utf-8")
    )
    runtime = manifest["runtime_contract"]
    assert runtime["tool_runtime"]["python"] == ">=3.12,<3.15"
    assert runtime["assessed_project_runtime"]["python"] == ">=3.10"
    assert runtime["generated_baseline_runtime"]["python"] == ">=3.12,<3.15"
    assert "implicit project minimum" in runtime["policy"]


def test_new_contract_schemas_are_valid_json_schema() -> None:
    from jsonschema import Draft202012Validator

    for name in (
        "ai-skills-lock.schema.json",
        "capability-manifest.schema.json",
        "evidence-provider.schema.json",
    ):
        schema = json.loads((ROOT / "contracts" / name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)

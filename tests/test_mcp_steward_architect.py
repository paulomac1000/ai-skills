"""Executable contracts for the MCP Steward architecture skill."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "mcp-steward-architect"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_composes_server_and_consumer_standards() -> None:
    manifest = yaml.safe_load((SKILL / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["version"] == "2.1.0"
    assert manifest["maturity"] == "stable"
    assert manifest["dependencies"]["skills"] == [
        "mcp-server-architect",
        "mcp-server-consumer",
    ]
    for required in manifest["required"]:
        assert (SKILL / required).is_file(), required

    credential_policy = yaml.safe_load(
        (SKILL / "templates" / "credential-policy.yaml.template").read_text(
            encoding="utf-8"
        )
    )
    forbidden = set(credential_policy["fallback"]["forbidden_failure_classes"])
    assert {"authorization-denied", "policy-denied", "delivery-unknown"} <= forbidden
    assert credential_policy["fallback"]["require_equivalent_principal_scope"] is True
    assert credential_policy["fallback"]["require_same_target"] is True
    assert credential_policy["fallback"]["require_replay_safe"] is True


def test_public_contract_schemas_are_draft_2020_12_and_closed() -> None:
    for name in (
        "steward-profile.schema.json",
        "steward-job.schema.json",
        "external-operation-receipt.schema.json",
        "steward-handoff.schema.json",
    ):
        schema = json.loads((ROOT / "contracts" / name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False


def test_delivery_unknown_is_reconciliation_not_retry() -> None:
    validator = _load(
        SKILL / "tools" / "validate_steward.py",
        "validate_steward",
    )
    receipt = {
        "schema_version": 1,
        "operationId": "op1",
        "jobId": "j1",
        "lineageId": "l1",
        "generation": 1,
        "attemptId": "a1",
        "capabilityIdentity": "deploy:v1",
        "targetIdentity": "prod:1",
        "requestDigest": "sha256:" + "0" * 64,
        "state": "dispatched",
        "delivery": "delivery-unknown",
        "retryDisposition": "eligible",
        "credentialSlotId": "primary",
        "createdAt": "2026-09-12T00:00:00Z",
        "observedAt": "2026-09-12T00:00:01Z",
        "retryCount": 0,
        "reconcileCount": 0,
    }
    findings = validator.validate_document("receipt", receipt)
    assert findings == [
        "receipt: delivery-unknown requires retryDisposition=reconcile-first"
    ]
    receipt["retryDisposition"] = "reconcile-first"
    assert validator.validate_document("receipt", receipt) == []


def test_stale_generation_handoff_cannot_be_actionable() -> None:
    validator = _load(
        SKILL / "tools" / "validate_steward.py",
        "validate_steward_handoff",
    )
    handoff = {
        "schema_version": 1,
        "handoffId": "h1",
        "jobId": "old",
        "lineageId": "l1",
        "generation": 1,
        "subject": {"type": "repo", "id": "r", "revision": "abc"},
        "status": "completed",
        "actionable": True,
        "outcome": "verified",
        "evidenceRefs": [],
        "artifactRefs": [],
        "externalOperationRefs": [],
        "gaps": [],
        "sealedAt": "2026-09-12T00:00:00Z",
        "digest": "sha256:" + "1" * 64,
    }
    assert validator.validate_handoff_current(
        handoff,
        current_job_id="new",
        current_generation=2,
    ) == ["handoff: stale job/generation cannot be actionable"]


def test_terminal_job_cannot_retain_lease() -> None:
    validator = _load(
        SKILL / "tools" / "validate_steward.py",
        "validate_steward_job",
    )
    job = {
        "schema_version": 1,
        "jobId": "j1",
        "lineageId": "l1",
        "generation": 1,
        "attemptId": "a1",
        "version": 2,
        "subject": {"type": "repo", "id": "r", "revision": "abc"},
        "status": "completed",
        "stage": "done",
        "createdAt": "2026-09-12T00:00:00Z",
        "updatedAt": "2026-09-12T00:01:00Z",
        "heartbeatAt": "2026-09-12T00:01:00Z",
        "progressAt": "2026-09-12T00:01:00Z",
        "deadlineAt": "2026-09-12T00:10:00Z",
        "lease": {
            "owner": "w1",
            "fencingToken": 1,
            "expiresAt": "2026-09-12T00:02:00Z",
        },
        "cancellation": "none",
        "externalOperationRefs": [],
        "evidenceRefs": [],
        "artifactRefs": [],
    }
    assert validator.validate_document("job", job) == [
        "job: terminal state must not retain an active lease"
    ]


def test_generator_extends_canonical_python_generator() -> None:
    generator = _load(
        SKILL / "tools" / "generate_steward.py",
        "generate_steward",
    )
    files = generator.steward_files(
        "python",
        "sample_steward",
        "Sample Steward",
        "sample",
        "verification",
    )
    assert "src/sample_steward/kernel.py" in files
    assert "src/sample_steward/steward_runtime.py" in files
    assert "tests/test_steward_runtime.py" in files
    assert "steward/contracts/external-operation-receipt.schema.json" in files
    profile = yaml.safe_load(files["steward/steward-profile.yaml"])
    assert profile["steward"]["kind"] == "verification"
    assert profile["durability"] == {
        "profile": "single-node-durable",
        "crash_model": ["process-restart"],
        "transactional_store_required": True,
        "lineage_fencing": True,
        "attempt_fencing": True,
    }
    assert (
        profile["external_operations"]["ambiguous_delivery"]
        == "reconcile-before-retry"
    )


def test_generator_extends_canonical_dotnet_generator() -> None:
    generator = _load(
        SKILL / "tools" / "generate_steward.py",
        "generate_steward_dotnet",
    )
    files = generator.steward_files(
        "dotnet",
        "Example",
        "Example Steward",
        "example",
        "generic",
    )
    assert "src/Example.Mcp.Domain/StewardContracts.cs" in files
    assert "src/Example.Mcp.Server/StewardFileStore.cs" in files
    assert "tests/Example.Mcp.Smoke/StewardRuntimeRegressions.cs" in files
    assert "StewardRuntimeRegressions.Verify();" in files[
        "tests/Example.Mcp.Smoke/Program.cs"
    ]
    assert "steward/contracts/steward-job.schema.json" in files
    profile = yaml.safe_load(files["steward/steward-profile.yaml"])
    assert profile["durability"]["profile"] == "constrained-file"
    assert profile["durability"]["transactional_store_required"] is False
    assert any(path.endswith(".csproj") for path in files)


def test_python_generator_publishes_without_overwrite_and_runtime_recovers(
    tmp_path: Path,
) -> None:
    generator = _load(
        SKILL / "tools" / "generate_steward.py",
        "generate_steward_publish",
    )
    destination = tmp_path / "sample"
    generator.generate_project(
        destination,
        language="python",
        identity="sample_steward",
        server_name="Sample Steward",
        steward_id="sample",
        profile="verification",
    )
    runtime = _load(
        destination / "src" / "sample_steward" / "steward_runtime.py",
        "generated_steward_runtime",
    )
    database = tmp_path / "durable.db"
    store = runtime.StewardStore(database)
    store.admit(
        job_id="j1",
        lineage_id="l1",
        generation=1,
        attempt_id="a1",
        subject={"type": "repo", "id": "r"},
        now="2026-09-12T00:00:00Z",
    )
    store.reserve_external(
        operation_id="op1",
        job_id="j1",
        generation=1,
        attempt_id="a1",
        request_digest="sha256:" + "0" * 64,
        credential_slot_id="primary",
    )
    store.mark_delivery_unknown("op1")
    assert runtime.StewardStore(database).receipt("op1") == (
        "delivery-unknown",
        "reconcile-first",
    )

    with pytest.raises(FileExistsError):
        generator.generate_project(
            destination,
            language="python",
            identity="sample_steward",
            server_name="Sample Steward",
            steward_id="sample",
            profile="verification",
        )


def test_standard_names_cross_product_invariants() -> None:
    standard = (SKILL / "STANDARD.md").read_text(encoding="utf-8")
    for phrase in (
        "delivery-unknown",
        "current lineage generation",
        "heartbeatAt",
        "progressAt",
        "completion obligations",
        "Credential failover",
        "controllable clock",
        "exact packaged/deployed artifact",
    ):
        assert phrase in standard

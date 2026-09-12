"""Executable acceptance contracts for the MCP Steward architecture skill."""

from __future__ import annotations

import importlib
import importlib.util
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "mcp-steward-architect"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _profile(generator: ModuleType) -> dict[str, Any]:
    return generator._profile_document("sample", "verification", durability_profile="single-node-durable")


def _proof(generator: ModuleType) -> dict[str, Any]:
    return generator._proof_recipe_document("sample")


def _handoff(validator: ModuleType) -> dict[str, Any]:
    value = {
        "schema_version": 1,
        "handoffId": "h1",
        "jobId": "j1",
        "lineageId": "l1",
        "generation": 2,
        "subject": {"type": "target", "id": "repo", "revision": "abc"},
        "status": "completed",
        "actionable": True,
        "outcome": "verified",
        "evidenceRefs": ["e1"],
        "artifactRefs": [],
        "externalOperationRefs": ["op1"],
        "gaps": [],
        "sealedAt": "2026-09-12T00:05:00Z",
        "digest": "sha256:" + "0" * 64,
    }
    value["digest"] = validator.compute_handoff_digest(value)
    return value


def _completion() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "evaluationId": "c1",
        "jobId": "j1",
        "lineageId": "l1",
        "generation": 2,
        "subject": {"type": "target", "id": "repo", "revision": "abc"},
        "decisionIdentity": {
            "generation": 2,
            "profileRevision": 1,
            "proofRecipeRevision": 1,
            "subjectRevision": "abc",
        },
        "disposition": "eligible",
        "obligations": [{"id": "provider-result", "state": "satisfied", "evidenceRefs": ["e1"]}],
        "ambiguousOperationRefs": [],
        "evaluatedAt": "2026-09-12T00:05:00Z",
    }


def _evidence(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": 1,
        "evidenceId": "e1",
        "jobId": "j1",
        "lineageId": "l1",
        "generation": 2,
        "subject": {"type": "target", "id": "repo", "revision": "abc"},
        "criterionId": "provider-result",
        "evidenceClass": "provider-observation",
        "authorityClass": "observed",
        "producerId": "seed-provider",
        "proofRecipeId": "sample-seed-proof@1",
        "observedAt": "2026-09-12T00:04:30Z",
        "expiresAt": "2026-09-12T00:09:30Z",
        "payloadDigest": "sha256:" + "1" * 64,
    }
    value.update(overrides)
    return value


def test_manifest_composes_server_and_consumer_standards() -> None:
    manifest = yaml.safe_load((SKILL / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["version"] == "2.1.0"
    assert manifest["maturity"] == "stable"
    assert manifest["dependencies"]["skills"] == ["mcp-server-architect", "mcp-server-consumer"]
    for required in manifest["required"]:
        assert (SKILL / required).is_file(), required

    credential_policy = yaml.safe_load(
        (SKILL / "templates" / "credential-policy.yaml.template").read_text(encoding="utf-8")
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
        "steward-evidence.schema.json",
        "steward-handoff.schema.json",
        "steward-lineage.schema.json",
        "steward-completion.schema.json",
        "upstream-capability.schema.json",
    ):
        schema = json.loads((ROOT / "contracts" / name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False


def test_delivery_unknown_is_reconciliation_not_retry() -> None:
    validator = _load(SKILL / "tools" / "validate_steward.py", "validate_steward_receipt")
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
    assert validator.validate_document("receipt", receipt) == [
        "receipt: delivery-unknown requires retryDisposition=reconcile-first"
    ]
    receipt["retryDisposition"] = "reconcile-first"
    assert validator.validate_document("receipt", receipt) == []


def test_stale_generation_handoff_cannot_be_actionable_before_digest_check() -> None:
    validator = _load(SKILL / "tools" / "validate_steward.py", "validate_steward_handoff_stale")
    handoff = _handoff(validator)
    handoff["jobId"] = "old"
    handoff["generation"] = 1
    handoff["digest"] = "sha256:" + "f" * 64
    assert validator.validate_handoff_current(
        handoff,
        current_job_id="j1",
        current_generation=2,
        current_subject={"type": "target", "id": "repo", "revision": "abc"},
    ) == ["handoff: stale job/generation cannot be actionable"]


def test_current_handoff_digest_is_recomputed_and_tampering_is_rejected() -> None:
    validator = _load(SKILL / "tools" / "validate_steward.py", "validate_steward_handoff_digest")
    handoff = _handoff(validator)
    context = {
        "current_job_id": "j1",
        "current_generation": 2,
        "current_subject": {"type": "target", "id": "repo", "revision": "abc"},
    }
    assert validator.validate_handoff_current(handoff, **context) == []
    handoff["outcome"] = "tampered"
    findings = validator.validate_handoff_current(handoff, **context)
    assert len(findings) == 1
    assert findings[0].startswith("handoff: digest mismatch; expected sha256:")


def test_actionable_handoff_cli_requires_current_lineage_context(tmp_path: Path) -> None:
    validator = _load(SKILL / "tools" / "validate_steward.py", "validate_steward_handoff_cli")
    handoff = _handoff(validator)
    handoff_path = tmp_path / "handoff.json"
    subject_path = tmp_path / "subject.json"
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
    subject_path.write_text(json.dumps(handoff["subject"]), encoding="utf-8")
    tool = SKILL / "tools" / "validate_steward.py"

    missing = subprocess.run(
        [sys.executable, str(tool), "handoff", str(handoff_path)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert missing.returncode == 1
    assert "actionable validation requires" in missing.stdout

    valid = subprocess.run(
        [
            sys.executable,
            str(tool),
            "handoff",
            str(handoff_path),
            "--current-job-id",
            "j1",
            "--current-generation",
            "2",
            "--current-subject",
            str(subject_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert valid.returncode == 0, valid.stdout + valid.stderr


def test_completion_gate_resolves_subject_authority_freshness_producer_and_recipe() -> None:
    validator = _load(SKILL / "tools" / "validate_steward.py", "validate_steward_completion_context")
    generator = _load(SKILL / "tools" / "generate_steward.py", "generate_steward_completion_context")
    profile = _profile(generator)
    proof = _proof(generator)
    completion = _completion()
    evidence = _evidence()
    current_subject = {"type": "target", "id": "repo", "revision": "abc"}

    assert (
        validator.validate_completion_context(
            completion,
            profile=profile,
            proof_recipe=proof,
            evidence_documents=[evidence],
            current_job_id="j1",
            current_generation=2,
            current_subject=current_subject,
            now=datetime(2026, 9, 12, 0, 5, tzinfo=UTC),
        )
        == []
    )

    for field, bad_value, expected in (
        ("producerId", "untrusted-producer", "producer not approved"),
        ("authorityClass", "advisory", "insufficient authority"),
        ("generation", 1, "stale job/generation"),
        ("proofRecipeId", "other@1", "proof recipe mismatch"),
    ):
        broken = _evidence(**{field: bad_value})
        findings = validator.validate_completion_context(
            completion,
            profile=profile,
            proof_recipe=proof,
            evidence_documents=[broken],
            current_job_id="j1",
            current_generation=2,
            current_subject=current_subject,
            now=datetime(2026, 9, 12, 0, 5, tzinfo=UTC),
        )
        assert any(expected in finding for finding in findings), findings
        assert findings[-1] == "completion: eligible disposition is not supported by current resolved evidence"

    stale = _evidence(observedAt="2026-09-11T23:00:00Z", expiresAt="2026-09-12T01:00:00Z")
    findings = validator.validate_completion_context(
        completion,
        profile=profile,
        proof_recipe=proof,
        evidence_documents=[stale],
        current_job_id="j1",
        current_generation=2,
        current_subject=current_subject,
        now=datetime(2026, 9, 12, 0, 5, tzinfo=UTC),
    )
    assert any("evidence is stale" in finding for finding in findings)


def test_terminal_job_cannot_retain_lease() -> None:
    validator = _load(SKILL / "tools" / "validate_steward.py", "validate_steward_job")
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
        "lease": {"owner": "w1", "fencingToken": 1, "expiresAt": "2026-09-12T00:02:00Z"},
        "cancellation": "none",
        "externalOperationRefs": [],
        "evidenceRefs": [],
        "artifactRefs": [],
    }
    assert validator.validate_document("job", job) == ["job: terminal state must not retain an active lease"]


def test_generator_replaces_sample_python_surface_with_executable_steward() -> None:
    generator = _load(SKILL / "tools" / "generate_steward.py", "generate_steward_python")
    files = generator.steward_files("python", "sample_steward", "Sample Steward", "sample", "verification")
    expected_tools = {
        "describe_capabilities",
        "steward_submit",
        "steward_status",
        "steward_get",
        "steward_cancel",
        "steward_doctor",
    }
    capability_paths = {
        Path(path).stem
        for path in files
        if path.startswith("src/sample_steward/capabilities/") and path.endswith(".json")
    }
    assert capability_paths == expected_tools
    server = files["src/sample_steward/server.py"]
    assert "steward_submit" in server
    assert "steward_get" in server
    assert "list_items" not in server
    assert "put_item" not in server
    runtime = files["src/sample_steward/steward_runtime.py"]
    for phrase in (
        "BEGIN IMMEDIATE",
        "idempotency_key",
        "delivery-unknown",
        "reconcile",
        "completion gate",
        "steward_evidence",
        "audit_events",
        "FakeClock",
        "FaultInjector",
        "start_background",
        "compute_handoff_digest",
    ):
        assert phrase in runtime
    assert "steward/contracts/steward-evidence.schema.json" in files
    assert "steward/proof-recipe.yaml" in files


def test_generator_dotnet_surface_exposes_same_semantic_lifecycle() -> None:
    generator = _load(SKILL / "tools" / "generate_steward.py", "generate_steward_dotnet")
    files = generator.steward_files("dotnet", "Example", "Example Steward", "example", "generic")
    assert "src/Example.Mcp.Server/StewardSeedRuntime.cs" in files
    tools = files["src/Example.Mcp.Server/Tools.cs"]
    for name in ("steward_submit", "steward_status", "steward_get", "steward_cancel", "steward_doctor"):
        assert name in tools
    assert "StewardSeedRuntime" in files["src/Example.Mcp.Server/Program.cs"]
    assert "VerifyStewardSeed();" in files["tests/Example.Mcp.Smoke/Program.cs"]
    assert "steward/contracts/steward-evidence.schema.json" in files
    profile = yaml.safe_load(files["steward/steward-profile.yaml"])
    assert profile["durability"]["profile"] == "constrained-file"


def test_generated_python_runtime_recovers_unknown_delivery_and_mandatory_gate(tmp_path: Path) -> None:
    generator = _load(SKILL / "tools" / "generate_steward.py", "generate_steward_runtime")
    destination = tmp_path / "sample"
    generator.generate_project(
        destination,
        language="python",
        identity="sample_steward",
        server_name="Sample Steward",
        steward_id="sample",
        profile="verification",
    )
    runtime_module = _load(
        destination / "src" / "sample_steward" / "steward_runtime.py",
        "generated_steward_runtime",
    )
    profile = json.loads((destination / "src/sample_steward/steward_profile.json").read_text(encoding="utf-8"))
    proof = json.loads((destination / "src/sample_steward/steward_proof_recipe.json").read_text(encoding="utf-8"))
    path = tmp_path / "durable.db"
    clock = runtime_module.FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    first = runtime_module.StewardRuntime(
        runtime_module.StewardStore(path, clock),
        profile,
        proof,
        faults=runtime_module.FaultInjector({"after-dispatch"}),
    )
    admitted = first.submit("repo", "abc", "idem-1")
    first.run_once()
    first.run_once()
    assert first.status(admitted["jobId"])["status"] == "reconciling"

    recovered = runtime_module.StewardRuntime(runtime_module.StewardStore(path, clock), profile, proof)
    recovered.recover_until_idle()
    result = recovered.get(admitted["jobId"])
    assert result["job"]["status"] == "completed"
    assert result["completion"]["disposition"] == "eligible"
    assert result["evidence"][0]["producerId"] == "seed-provider"
    assert result["handoff"]["digest"] == runtime_module.compute_handoff_digest(result["handoff"])

    stale = recovered.submit("repo-2", "abc", "supersede-1")
    recovered.run_once()
    recovered.run_once()
    latest = recovered.submit("repo-2", "abc", "supersede-2")
    assert recovered.status(stale["jobId"])["status"] == "superseded"
    recovered.recover_until_idle()
    assert recovered.status(latest["jobId"])["status"] == "completed"
    assert recovered.get(stale["jobId"])["handoff"] is None

    with pytest.raises(FileExistsError):
        generator.generate_project(
            destination,
            language="python",
            identity="sample_steward",
            server_name="Sample Steward",
            steward_id="sample",
            profile="verification",
        )


@pytest.mark.anyio
async def test_generated_public_mcp_controls_durable_steward_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import anyio
    from mcp import Client

    generator = _load(SKILL / "tools" / "generate_steward.py", "generate_steward_mcp_e2e")
    destination = tmp_path / "mcp"
    generator.generate_project(
        destination,
        language="python",
        identity="acceptance_steward",
        server_name="Acceptance Steward",
        steward_id="acceptance",
        profile="verification",
    )
    monkeypatch.syspath_prepend(str(destination / "src"))
    monkeypatch.setenv("STEWARD_STATE_PATH", str(tmp_path / "mcp-state.db"))
    for name in [
        key for key in list(sys.modules) if key == "acceptance_steward" or key.startswith("acceptance_steward.")
    ]:
        del sys.modules[name]
    server = importlib.import_module("acceptance_steward.server")
    runtime_module = importlib.import_module("acceptance_steward.steward_runtime")
    runtime = runtime_module.default_runtime()
    runtime.start_background(interval_seconds=0.005)
    try:
        async with Client(server.mcp) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools.tools}
            assert names == {
                "describe_capabilities",
                "steward_submit",
                "steward_status",
                "steward_get",
                "steward_cancel",
                "steward_doctor",
            }
            submitted = await client.call_tool(
                "steward_submit",
                {"subject_id": "repo", "subject_revision": "abc", "idempotency_key": "idem-1"},
            )
            assert submitted.structured_content is not None
            job_id = submitted.structured_content["jobId"]
            duplicate = await client.call_tool(
                "steward_submit",
                {"subject_id": "repo", "subject_revision": "abc", "idempotency_key": "idem-1"},
            )
            assert duplicate.structured_content is not None
            assert duplicate.structured_content["jobId"] == job_id
            assert duplicate.structured_content["duplicate"] is True

            for _ in range(200):
                result = await client.call_tool("steward_get", {"job_id": job_id})
                assert result.structured_content is not None
                if result.structured_content["job"]["status"] == "completed":
                    break
                await anyio.sleep(0.005)
            else:
                pytest.fail("generated Steward did not reach completion through recovery supervisor")

            assert result.structured_content["completion"]["disposition"] == "eligible"
            assert result.structured_content["handoff"]["digest"] == runtime_module.compute_handoff_digest(
                result.structured_content["handoff"]
            )
            doctor = await client.call_tool("steward_doctor", {"job_id": job_id})
            assert doctor.structured_content is not None
            assert doctor.structured_content["deliveryUnknown"] == 0
    finally:
        runtime.stop_background()


def test_profile_and_upstream_cross_product_fail_closed() -> None:
    validator = _load(SKILL / "tools" / "validate_steward.py", "validate_steward_cross_product")
    profile = yaml.safe_load((SKILL / "templates" / "steward-profile.yaml.template").read_text(encoding="utf-8"))
    profile["subject_identity"]["freshness_dimensions"] = ["runtime-generation"]
    obligation = {"id": "proof", "required": True, "evidence_class": "observed"}
    profile["completion"]["obligations"] = [obligation, {**obligation, "required": False}]
    assert validator.validate_document("profile", profile) == [
        "subject_identity: freshness dimensions must also be required dimensions: runtime-generation",
        "completion: duplicate obligation ids: proof",
    ]

    capability = yaml.safe_load((SKILL / "templates" / "upstream-capability.yaml.template").read_text(encoding="utf-8"))
    capability["interaction"] = "stateful"
    capability["delivery"] = "durable-async"
    assert validator.validate_document("upstream", capability) == [
        "upstream: stateful capability requires recovery and ambiguous-delivery reconciliation",
        "upstream: durable-async capability requires status/resume by handle",
        "upstream: durable-async capability requires progress semantics",
    ]


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

"""Executable v3 acceptance contracts for the MCP Steward architecture skill."""

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


def _generator(name: str = "steward_generator") -> ModuleType:
    return _load(SKILL / "tools" / "generate_steward.py", name)


def _validator(name: str = "steward_validator") -> ModuleType:
    return _load(SKILL / "tools" / "validate_steward.py", name)


def _docs(generator: ModuleType) -> dict[str, dict[str, Any]]:
    return generator._embedded_docs("sample", "verification", "single-node-durable")


def _job(docs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    now = "2026-09-12T00:00:00Z"
    subject = {"type": "target", "id": "repo", "revision": "abc"}
    candidate = {"type": "subject-snapshot", "id": "repo", "revision": "abc", "digest": "sha256:" + "2" * 64}
    return {
        "schema_version": 2,
        "jobId": "j1",
        "lineageId": "l1",
        "generation": 2,
        "attemptId": "a1",
        "version": 1,
        "subject": subject,
        "candidate": candidate,
        "requestDigest": "sha256:" + "4" * 64,
        "status": "queued",
        "stage": "admitted",
        "createdAt": now,
        "updatedAt": now,
        "heartbeatAt": now,
        "progressAt": now,
        "progressRevision": 1,
        "progressMarker": "admitted",
        "deadlineAt": "2026-09-12T00:15:00Z",
        "finalizationStartsAt": None,
        "lease": {"owner": "steward-runtime:a1", "fencingToken": 2, "expiresAt": "2026-09-12T00:15:00Z"},
        "cancellation": "none",
        "blockedReason": None,
        "externalOperationRefs": [],
        "evidenceRefs": [],
        "artifactRefs": [],
        "failure": None,
    }


def _receipt(docs: dict[str, dict[str, Any]], job: dict[str, Any]) -> dict[str, Any]:
    upstream = docs["steward_upstream_capability"]
    return {
        "schema_version": 2,
        "operationId": "op1",
        "operationKind": "submit",
        "jobId": "j1",
        "lineageId": "l1",
        "generation": 2,
        "attemptId": "a1",
        "jobVersion": 1,
        "capabilityIdentity": upstream["capability_id"],
        "capabilityContractDigest": upstream["contract"]["digest"],
        "targetIdentity": "target:repo:abc",
        "candidateDigest": job["candidate"]["digest"],
        "requestDigest": "sha256:" + "1" * 64,
        "idempotencyKeyDigest": None,
        "mutationDecisionRef": "admission-1",
        "state": "reserved",
        "delivery": "not-delivered",
        "retryDisposition": "forbidden",
        "remoteHandle": None,
        "credentialSlotId": "primary",
        "providerIdentity": "seed-provider",
        "createdAt": "2026-09-12T00:00:00Z",
        "observedAt": "2026-09-12T00:00:00Z",
        "retryCount": 0,
        "reconcileCount": 0,
        "nextRetryAt": None,
        "nextReconcileAt": None,
        "failureClass": None,
    }


def _evidence(job: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": 2,
        "evidenceId": "e1",
        "jobId": "j1",
        "lineageId": "l1",
        "generation": 2,
        "subject": job["subject"],
        "candidate": job["candidate"],
        "criterionId": "provider-result",
        "claimId": "provider-result",
        "evidenceClass": "provider-observation",
        "observationGrade": "observed",
        "authorityClass": "observed",
        "producerId": "seed-provider",
        "proofRecipeId": "sample-seed-proof@1",
        "binding": {"required": ["target", "candidate"], "satisfied": ["target", "candidate"], "status": "complete"},
        "coverage": {"state": "complete", "required": 1, "observed": 1},
        "observedAt": "2026-09-12T00:04:30Z",
        "expiresAt": "2026-09-12T00:09:30Z",
        "payloadDigest": "sha256:" + "3" * 64,
    }
    value.update(overrides)
    return value


def _completion(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "evaluationId": "c1",
        "jobId": "j1",
        "lineageId": "l1",
        "generation": 2,
        "subject": job["subject"],
        "candidate": job["candidate"],
        "decisionIdentity": {
            "generation": 2,
            "profileRevision": 2,
            "proofRecipeRevision": 1,
            "subjectRevision": "abc",
            "candidateDigest": job["candidate"]["digest"],
        },
        "disposition": "eligible",
        "obligations": [{"id": "provider-result", "state": "satisfied", "evidenceRefs": ["e1"]}],
        "ambiguousOperationRefs": [],
        "ambiguousCancellationRefs": [],
        "evaluatedAt": "2026-09-12T00:05:00Z",
    }


def _handoff(validator: ModuleType, job: dict[str, Any]) -> dict[str, Any]:
    value = {
        "schema_version": 2,
        "handoffId": "h1",
        "jobId": "j1",
        "lineageId": "l1",
        "generation": 2,
        "subject": job["subject"],
        "candidate": job["candidate"],
        "status": "completed",
        "actionable": True,
        "outcome": "verified",
        "evidenceRefs": ["e1"],
        "artifactRefs": [],
        "externalOperationRefs": ["op1"],
        "gaps": [],
        "failureClass": None,
        "correlationId": "j1",
        "sealedAt": "2026-09-12T00:05:00Z",
        "digest": "sha256:" + "0" * 64,
    }
    value["digest"] = validator.compute_handoff_digest(value)
    return value


def test_manifest_is_v3_and_composes_base_standards() -> None:
    manifest = yaml.safe_load((SKILL / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["version"] == "3.0.0"
    assert manifest["dependencies"]["skills"] == ["mcp-server-architect", "mcp-server-consumer"]
    for required in manifest["required"]:
        assert (SKILL / required).is_file(), required
    assert {"durable_external_async", "causal_claims", "external_cancellation", "exact_candidate_binding"} <= set(
        manifest["applicability"]["derived_flags"]
    )


def test_all_steward_contract_schemas_are_closed_draft_2020_12() -> None:
    names = (
        "steward-profile.schema.json",
        "steward-job.schema.json",
        "external-operation-receipt.schema.json",
        "steward-evidence.schema.json",
        "steward-handoff.schema.json",
        "steward-lineage.schema.json",
        "steward-completion.schema.json",
        "upstream-capability.schema.json",
        "steward-state-machine.schema.json",
        "steward-mutation-policy.schema.json",
        "steward-proof-recipe.schema.json",
        "steward-acceptance.schema.json",
    )
    for name in names:
        schema = json.loads((ROOT / "contracts" / name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False


def test_generated_design_pack_is_cross_contract_valid() -> None:
    generator, validator = _generator("gen_design"), _validator("val_design")
    docs = _docs(generator)
    assert (
        validator.validate_design_pack(
            profile=docs["steward_profile"],
            state_machine=docs["steward_state_machine"],
            mutation_policy=docs["steward_mutation_policy"],
            proof_recipe=docs["steward_proof_recipe"],
            acceptance=docs["steward_acceptance"],
            upstreams=[docs["steward_upstream_capability"]],
        )
        == []
    )


def test_mutation_admission_fails_closed_on_authority_fences_capability_candidate_budget_and_ambiguity() -> None:
    generator, validator = _generator("gen_admission"), _validator("val_admission")
    docs = _docs(generator)
    job = _job(docs)
    receipt = _receipt(docs, job)
    authority = {
        "source": "steward-runtime",
        "principal": "steward-runtime:a1",
        "scope": "external-dispatch",
        "target": "target:repo:abc",
        "attemptId": "a1",
        "jobVersion": 1,
        "leaseOwner": "steward-runtime:a1",
        "leaseFencingToken": 2,
    }
    base = dict(
        effect_id="external-dispatch",
        mutation_policy=docs["steward_mutation_policy"],
        job=job,
        capability=docs["steward_upstream_capability"],
        current_job_id="j1",
        current_generation=2,
        current_attempt_id="a1",
        current_version=1,
        current_subject=job["subject"],
        effective_authority=authority,
        remaining_budget_ms=5000,
        expected_request_digest=receipt["requestDigest"],
        receipt=receipt,
        candidate=job["candidate"],
        now=datetime(2026, 9, 12, tzinfo=UTC),
    )
    assert validator.evaluate_mutation_admission(**base)["disposition"] == "Admitted"
    cases = (
        ({"effective_authority": {**authority, "source": "other-authority"}}, "LostAuthority"),
        ({"effective_authority": {**authority, "leaseOwner": "other-owner"}}, "LostAuthority"),
        ({"effective_authority": {**authority, "leaseFencingToken": 1}}, "LostAuthority"),
        ({"current_attempt_id": "a2"}, "LostAuthority"),
        ({"current_version": 2}, "LostAuthority"),
        ({"current_subject": {**job["subject"], "revision": "def"}}, "LostAuthority"),
        ({"candidate": {**job["candidate"], "digest": "sha256:" + "9" * 64}}, "StaleCandidate"),
        ({"receipt": {**receipt, "jobId": "foreign-job"}}, "LostAuthority"),
        ({"receipt": {**receipt, "lineageId": "foreign-lineage"}}, "LostAuthority"),
        ({"receipt": {**receipt, "generation": 1}}, "LostAuthority"),
        ({"receipt": {**receipt, "attemptId": "foreign-attempt"}}, "LostAuthority"),
        ({"receipt": {**receipt, "jobVersion": 0}}, "LostAuthority"),
        ({"receipt": {**receipt, "operationKind": "cancel"}}, "LostAuthority"),
        ({"receipt": {**receipt, "requestDigest": "sha256:" + "8" * 64}}, "LostAuthority"),
        ({"receipt": {**receipt, "candidateDigest": "sha256:" + "7" * 64}}, "StaleCandidate"),
        ({"remaining_budget_ms": 1499}, "BudgetUnavailable"),
        (
            {
                "receipt": {
                    **receipt,
                    "state": "dispatching",
                    "delivery": "delivery-unknown",
                    "retryDisposition": "reconcile-first",
                }
            },
            "ReconciliationRequired",
        ),
    )
    for changes, expected in cases:
        assert validator.evaluate_mutation_admission(**{**base, **changes})["disposition"] == expected

    drift = json.loads(json.dumps(docs["steward_upstream_capability"]))
    drift["contract"]["revision"] = "2"
    identity = {key: drift["contract"][key] for key in ("source", "id", "revision")}
    import hashlib

    drift["contract"]["digest"] = (
        "sha256:" + hashlib.sha256(json.dumps(identity, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
    )
    assert (
        validator.evaluate_mutation_admission(**{**base, "capability": drift})["disposition"] == "CapabilityUnavailable"
    )

    cancel_effect = next(
        item for item in docs["steward_mutation_policy"]["effects"] if item["id"] == "cancellation-dispatch"
    )
    cancel_job = {**job, "cancellation": "requested"}
    cancel_authority = {**authority, "scope": "cancellation-dispatch"}
    cancel_receipt = {**receipt, "operationKind": "cancel"}
    cancel_request_digest = "sha256:" + "6" * 64
    cancel_receipt["requestDigest"] = cancel_request_digest
    assert cancel_effect["operation_kind"] == "cancel"
    assert (
        validator.evaluate_mutation_admission(
            effect_id="cancellation-dispatch",
            mutation_policy=docs["steward_mutation_policy"],
            job=cancel_job,
            capability=docs["steward_upstream_capability"],
            current_job_id="j1",
            current_generation=2,
            current_attempt_id="a1",
            current_version=1,
            current_subject=job["subject"],
            effective_authority=cancel_authority,
            remaining_budget_ms=5000,
            expected_request_digest=cancel_request_digest,
            receipt=cancel_receipt,
            candidate=job["candidate"],
            now=datetime(2026, 9, 12, tzinfo=UTC),
        )["disposition"]
        == "Admitted"
    )


def test_design_pack_rejects_unresolved_capability_profile_ref_and_producer_dimension_drift() -> None:
    generator, validator = _generator("gen_design_negative"), _validator("val_design_negative")
    docs = _docs(generator)
    mutation = json.loads(json.dumps(docs["steward_mutation_policy"]))
    mutation["effects"][0]["capability_ref"] = "missing:capability"
    findings = validator.validate_design_pack(
        profile=docs["steward_profile"],
        state_machine=docs["steward_state_machine"],
        mutation_policy=mutation,
        proof_recipe=docs["steward_proof_recipe"],
        acceptance=docs["steward_acceptance"],
        upstreams=[docs["steward_upstream_capability"]],
    )
    assert any("capability_ref must resolve" in item for item in findings)

    contract_drift = json.loads(json.dumps(docs["steward_mutation_policy"]))
    contract_drift["effects"][0]["capability_contract"]["revision"] = "2"
    findings = validator.validate_design_pack(
        profile=docs["steward_profile"],
        state_machine=docs["steward_state_machine"],
        mutation_policy=contract_drift,
        proof_recipe=docs["steward_proof_recipe"],
        acceptance=docs["steward_acceptance"],
        upstreams=[docs["steward_upstream_capability"]],
    )
    assert any("capability contract" in item for item in findings)

    profile = json.loads(json.dumps(docs["steward_profile"]))
    profile["contracts"]["proof_recipe"] = "wrong-proof@1"
    findings = validator.validate_design_pack(
        profile=profile,
        state_machine=docs["steward_state_machine"],
        mutation_policy=docs["steward_mutation_policy"],
        proof_recipe=docs["steward_proof_recipe"],
        acceptance=docs["steward_acceptance"],
        upstreams=[docs["steward_upstream_capability"]],
    )
    assert any("profile contract proof_recipe" in item for item in findings)

    proof = json.loads(json.dumps(docs["steward_proof_recipe"]))
    proof["producers"][0]["subject_dimensions"] = []
    assert any(
        "cannot observe required subject dimensions" in item for item in validator.validate_document("proof", proof)
    )


def test_job_validator_rejects_timezone_less_nested_lease_expiry() -> None:
    generator, validator = _generator("gen_lease_timestamp"), _validator("val_lease_timestamp")
    job = _job(_docs(generator))
    job["lease"]["expiresAt"] = "2026-09-12T00:15:00"
    assert any("lease.expiresAt" in item for item in validator.validate_document("job", job))


def test_capability_truth_is_not_health_and_stateful_cancel_requires_reconciliation() -> None:
    generator, validator = _generator("gen_upstream"), _validator("val_upstream")
    upstream = _docs(generator)["steward_upstream_capability"]
    assert validator.validate_document("upstream", upstream) == []
    broken = json.loads(json.dumps(upstream))
    broken["cancellation"]["reconciliation"] = "unsupported"
    broken["cancellation"]["local_terminal_requires_remote_resolution"] = False
    findings = validator.validate_document("upstream", broken)
    assert any("stateful cancellation requires reconciliation" in item for item in findings)
    assert any("must not equate local terminal state" in item for item in findings)


def test_proof_requires_binding_and_independent_producer_when_claimed() -> None:
    generator, validator = _generator("gen_proof"), _validator("val_proof")
    proof = _docs(generator)["steward_proof_recipe"]
    assert validator.validate_document("proof", proof) == []
    broken = json.loads(json.dumps(proof))
    broken["criteria"][0]["required_authority"] = "independent"
    assert any("no independent producer" in item for item in validator.validate_document("proof", broken))
    job = _job(_docs(generator))
    ev = _evidence(job)
    ev["binding"] = {"required": ["target", "candidate"], "satisfied": ["target"], "status": "partial"}
    ev["authorityClass"] = "verified"
    assert any("incomplete binding" in item for item in validator.validate_document("evidence", ev))


def test_completion_resolves_candidate_binding_producer_authority_and_freshness() -> None:
    generator, validator = _generator("gen_completion"), _validator("val_completion")
    docs = _docs(generator)
    job = _job(docs)
    completion = _completion(job)
    evidence = _evidence(job)
    context = dict(
        profile=docs["steward_profile"],
        proof_recipe=docs["steward_proof_recipe"],
        evidence_documents=[evidence],
        current_job_id="j1",
        current_generation=2,
        current_lineage_id=job["lineageId"],
        current_subject=job["subject"],
        current_candidate=job["candidate"],
        now=datetime(2026, 9, 12, 0, 5, tzinfo=UTC),
    )
    assert validator.validate_completion_context(completion, **context) == []
    stale_candidate = {**job["candidate"], "digest": "sha256:" + "8" * 64}
    findings = validator.validate_completion_context(completion, **{**context, "current_candidate": stale_candidate})
    assert any("stale candidate" in item for item in findings)
    partial = _evidence(
        job, binding={"required": ["target", "candidate"], "satisfied": ["target"], "status": "partial"}
    )
    findings = validator.validate_completion_context(completion, **{**context, "evidence_documents": [partial]})
    assert any("incomplete claim binding" in item or "incomplete binding" in item for item in findings)


def test_actionable_handoff_binds_current_candidate_and_digest() -> None:
    generator, validator = _generator("gen_handoff"), _validator("val_handoff")
    job = _job(_docs(generator))
    handoff = _handoff(validator, job)
    context = dict(
        current_job_id="j1",
        current_generation=2,
        current_lineage_id=job["lineageId"],
        current_subject=job["subject"],
        current_candidate=job["candidate"],
    )
    assert validator.validate_handoff_current(handoff, **context) == []
    bad_candidate = {**job["candidate"], "digest": "sha256:" + "f" * 64}
    assert validator.validate_handoff_current(handoff, **{**context, "current_candidate": bad_candidate}) == [
        "handoff: stale candidate identity cannot be actionable"
    ]
    handoff["outcome"] = "tampered"
    assert any("digest mismatch" in item for item in validator.validate_handoff_current(handoff, **context))


def test_production_acceptance_cannot_skip_independent_live_or_exact_full_path() -> None:
    generator, validator = _generator("gen_accept"), _validator("val_accept")
    plan = _docs(generator)["steward_acceptance"]
    assert validator.validate_document("acceptance", plan) == []
    prod = json.loads(json.dumps(plan))
    prod["claim_class"] = "production-workflow"
    findings = validator.validate_document("acceptance", prod)
    assert any("independent-delta and live-full-path" in item for item in findings)
    prod["required_lanes"] += ["independent-delta", "live-full-path"]
    prod["independent_required"] = True
    prod["live_full_path_required"] = True
    assert validator.validate_document("acceptance", prod) == []


def test_generator_emits_design_pack_and_semantic_surfaces() -> None:
    generator = _generator("gen_surface")
    files = generator.steward_files("python", "sample_steward", "Sample Steward", "sample", "verification")
    for path in (
        "steward/steward-profile.yaml",
        "steward/steward-state-machine.yaml",
        "steward/mutation-policy.yaml",
        "steward/proof-recipe.yaml",
        "steward/upstream-capability.yaml",
        "steward/acceptance.yaml",
        "steward/contracts/steward-state-machine.schema.json",
        "steward/contracts/steward-mutation-policy.schema.json",
    ):
        assert path in files
    capabilities = {Path(path).stem for path in files if path.startswith("src/sample_steward/capabilities/")}
    assert capabilities == {
        "describe_capabilities",
        "steward_submit",
        "steward_status",
        "steward_get",
        "steward_cancel",
        "steward_doctor",
    }
    assert all(
        "put_item" not in text and "list_items" not in text for path, text in files.items() if path.startswith("tests/")
    )


def test_generated_python_runtime_imports_recovers_cancels_and_does_not_hot_poll(tmp_path: Path) -> None:
    generator = _generator("gen_runtime")
    destination = tmp_path / "sample"
    generator.generate_project(
        destination,
        language="python",
        identity="sample_steward",
        server_name="Sample Steward",
        steward_id="sample",
        profile="verification",
    )
    subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(destination / "src"), str(destination / "tests")], check=True
    )
    runtime_module = _load(destination / "src/sample_steward/steward_runtime.py", "generated_v3_runtime")
    profile = json.loads((destination / "src/sample_steward/steward_profile.json").read_text(encoding="utf-8"))
    proof = json.loads((destination / "src/sample_steward/steward_proof_recipe.json").read_text(encoding="utf-8"))
    mutation = json.loads((destination / "src/sample_steward/steward_mutation_policy.json").read_text(encoding="utf-8"))
    upstream = json.loads(
        (destination / "src/sample_steward/steward_upstream_capability.json").read_text(encoding="utf-8")
    )
    clock = runtime_module.FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    path = tmp_path / "state.db"
    first = runtime_module.StewardRuntime(
        runtime_module.StewardStore(path, clock),
        profile,
        proof,
        mutation,
        upstream=upstream,
        faults=runtime_module.FaultInjector({"after-dispatch"}),
    )
    job_id = first.submit("repo", "abc", "idem-1")["jobId"]
    first.run_once()
    first.run_once()
    assert first.status(job_id)["status"] == "reconciling"
    recovered = runtime_module.StewardRuntime(
        runtime_module.StewardStore(path, clock), profile, proof, mutation, upstream=upstream
    )
    recovered.recover_until_idle()
    result = recovered.get(job_id)
    assert result["job"]["status"] == "completed"
    assert result["handoff"]["candidate"] == result["job"]["candidate"]
    assert recovered.cancel(job_id)["status"] == "completed"

    class Counting(runtime_module.FakeProvider):
        def __init__(self) -> None:
            self.poll_count = 0
            self.cancel_count = 0
            self.cancel_reconcile_count = 0

        def poll(self, remote_handle: str, subject: dict[str, Any]) -> dict[str, Any]:
            self.poll_count += 1
            return super().poll(remote_handle, subject)

        def cancel(self, op: str, handle: str, subject: dict[str, Any]) -> str:
            self.cancel_count += 1
            return super().cancel(op, handle, subject)

        def reconcile_cancel(self, op: str, handle: str, subject: dict[str, Any]) -> str:
            self.cancel_reconcile_count += 1
            return super().reconcile_cancel(op, handle, subject)

    provider = Counting()
    cancel_path = tmp_path / "cancel.db"
    cancel_rt = runtime_module.StewardRuntime(
        runtime_module.StewardStore(cancel_path, clock),
        profile,
        proof,
        mutation,
        upstream=upstream,
        provider=provider,
        faults=runtime_module.FaultInjector({"after-cancel-dispatch"}),
    )
    cancel_id = cancel_rt.submit("repo2", "abc", "cancel-1")["jobId"]
    cancel_rt.run_once()
    cancel_rt.run_once()
    cancel_rt.cancel(cancel_id)
    cancel_rt.run_once()
    cancel_rt.run_once()
    assert cancel_rt.status(cancel_id)["status"] == "cancelling"
    restarted = runtime_module.StewardRuntime(
        runtime_module.StewardStore(cancel_path, clock), profile, proof, mutation, upstream=upstream, provider=provider
    )
    restarted.recover_until_idle()
    assert restarted.status(cancel_id)["status"] == "cancelled"
    assert provider.cancel_reconcile_count >= 1
    assert all(
        item["state"] == "captured"
        for item in restarted.get(cancel_id)["operations"]
        if item["operation_kind"] == "submit"
    )

    class Unapproved(Counting):
        producer_id = "unapproved"

    bad = Unapproved()
    blocked_rt = runtime_module.StewardRuntime(
        runtime_module.StewardStore(tmp_path / "blocked.db", clock),
        profile,
        proof,
        mutation,
        upstream=upstream,
        provider=bad,
    )
    blocked_id = blocked_rt.submit("repo3", "abc", "blocked-1")["jobId"]
    for _ in range(10):
        blocked_rt.run_once()
    assert blocked_rt.status(blocked_id)["status"] == "blocked"
    assert bad.poll_count == 1
    assert blocked_rt.run_once() is False


@pytest.mark.anyio
async def test_generated_public_mcp_controls_v3_durable_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import anyio
    from mcp import Client

    generator = _generator("gen_mcp_e2e")
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
    monkeypatch.setenv("STEWARD_STATE_PATH", str(tmp_path / "mcp.db"))
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
            names = {tool.name for tool in (await client.list_tools()).tools}
            assert names == {
                "describe_capabilities",
                "steward_submit",
                "steward_status",
                "steward_get",
                "steward_cancel",
                "steward_doctor",
            }
            submitted = await client.call_tool(
                "steward_submit", {"subject_id": "repo", "subject_revision": "abc", "idempotency_key": "idem-public"}
            )
            assert submitted.structured_content is not None
            job_id = submitted.structured_content["jobId"]
            for _ in range(200):
                result = await client.call_tool("steward_get", {"job_id": job_id})
                assert result.structured_content is not None
                if result.structured_content["job"]["status"] == "completed":
                    break
                await anyio.sleep(0.005)
            else:
                pytest.fail("generated Steward did not complete")
            assert result.structured_content["handoff"]["candidate"] == result.structured_content["job"]["candidate"]
    finally:
        runtime.stop_background()


def test_generator_dotnet_surface_carries_v3_design_pack() -> None:
    generator = _generator("gen_dotnet")
    files = generator.steward_files("dotnet", "Example", "Example Steward", "example", "verification")
    assert "src/Example.Mcp.Server/StewardSeedRuntime.cs" in files
    for name in (
        "steward_profile",
        "steward_state_machine",
        "steward_mutation_policy",
        "steward_proof_recipe",
        "steward_upstream_capability",
        "steward_acceptance",
    ):
        assert f"src/Example.Mcp.Server/{name}.json" in files
    assert "StewardRecoveryService" in files["src/Example.Mcp.Server/Program.cs"]


def test_standard_names_v3_cross_product_invariants() -> None:
    standard = (SKILL / "STANDARD.md").read_text(encoding="utf-8")
    for phrase in (
        "Mutation Admission Gate",
        "CandidateIdentity",
        "Missing observation is not a negative observation",
        "local `cancelled` status MUST NOT imply upstream work stopped",
        "Recovery equivalence is required",
        "production workflow acceptance claim",
        "exact packaged/deployed artifact",
    ):
        assert phrase in standard


def test_generator_rejects_nested_symlink_destination(tmp_path: Path) -> None:
    generator = _generator("gen_symlink_confinement")
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable on this platform")
    with pytest.raises(ValueError, match="symlinks|reparse"):
        generator.generate_project(
            linked / "project",
            language="python",
            identity="safe_steward",
            server_name="Safe Steward",
            steward_id="safe",
            profile="verification",
        )
    assert not (outside / "project").exists()

"""Atomic fail-closed controls for Steward authority and delivery semantics."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "mcp-steward-architect"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _generator() -> ModuleType:
    return _load(SKILL / "tools" / "generate_steward.py", "steward_atomic_generator")


def _validator() -> ModuleType:
    return _load(SKILL / "tools" / "validate_steward.py", "steward_atomic_validator")


def _documents() -> dict[str, dict[str, Any]]:
    return _generator()._embedded_docs("atomic", "verification", "single-node-durable")


def _job() -> dict[str, Any]:
    now = "2026-09-13T00:00:00Z"
    return {
        "schema_version": 2,
        "jobId": "job-1",
        "lineageId": "lineage-1",
        "generation": 3,
        "attemptId": "attempt-1",
        "version": 1,
        "subject": {"type": "target", "id": "repo", "revision": "abc"},
        "candidate": {
            "type": "subject-snapshot",
            "id": "repo",
            "revision": "abc",
            "digest": "sha256:" + "2" * 64,
        },
        "requestDigest": "sha256:" + "3" * 64,
        "status": "queued",
        "stage": "admitted",
        "createdAt": now,
        "updatedAt": now,
        "heartbeatAt": now,
        "progressAt": now,
        "progressRevision": 1,
        "progressMarker": "admitted",
        "deadlineAt": "2026-09-13T00:15:00Z",
        "finalizationStartsAt": None,
        "lease": {
            "owner": "steward-runtime:attempt-1",
            "fencingToken": 3,
            "expiresAt": "2026-09-13T00:10:00Z",
        },
        "cancellation": "none",
        "blockedReason": None,
        "externalOperationRefs": [],
        "evidenceRefs": [],
        "artifactRefs": [],
        "failure": None,
    }


def _receipt(documents: dict[str, dict[str, Any]], job: dict[str, Any]) -> dict[str, Any]:
    upstream = documents["steward_upstream_capability"]
    return {
        "schema_version": 2,
        "operationId": "operation-1",
        "operationKind": "submit",
        "jobId": job["jobId"],
        "lineageId": job["lineageId"],
        "generation": job["generation"],
        "attemptId": job["attemptId"],
        "jobVersion": job["version"],
        "capabilityIdentity": upstream["capability_id"],
        "capabilityContractDigest": upstream["contract"]["digest"],
        "targetIdentity": "target:repo:abc",
        "candidateDigest": job["candidate"]["digest"],
        "requestDigest": "sha256:" + "1" * 64,
        "idempotencyKeyDigest": None,
        "mutationDecisionRef": "admission-1",
        "semanticSlot": "submit",
        "operationDeadlineAt": "2026-09-13T00:15:00Z",
        "cancellationCause": None,
        "state": "dispatching",
        "delivery": "delivery-unknown",
        "retryDisposition": "reconcile-first",
        "remoteHandle": None,
        "credentialSlotId": "primary",
        "providerIdentity": "seed-provider",
        "createdAt": "2026-09-13T00:00:00Z",
        "observedAt": "2026-09-13T00:00:01Z",
        "retryCount": 0,
        "reconcileCount": 0,
        "nextRetryAt": None,
        "nextReconcileAt": "2026-09-13T00:00:02Z",
        "failureClass": None,
    }


def _effective_authority(job: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    lease = job["lease"]
    assert isinstance(lease, dict)
    return {
        "source": "steward-runtime",
        "principal": f"steward-runtime:{job['attemptId']}",
        "scope": "external-dispatch",
        "target": receipt["targetIdentity"],
        "attemptId": job["attemptId"],
        "jobVersion": job["version"],
        "leaseOwner": lease["owner"],
        "leaseFencingToken": lease["fencingToken"],
    }


def _evaluate_external_dispatch(
    validator: ModuleType,
    documents: dict[str, dict[str, Any]],
    job: dict[str, Any],
    receipt: dict[str, Any],
) -> dict[str, Any]:
    return validator.evaluate_mutation_admission(
        effect_id="external-dispatch",
        mutation_policy=documents["steward_mutation_policy"],
        job=job,
        capability=documents["steward_upstream_capability"],
        current_job_id=job["jobId"],
        current_generation=job["generation"],
        current_attempt_id=job["attemptId"],
        current_version=job["version"],
        current_subject=job["subject"],
        effective_authority=_effective_authority(job, receipt),
        remaining_budget_ms=5000,
        expected_request_digest=receipt["requestDigest"],
        receipt=receipt,
        candidate=job["candidate"],
        now=datetime(2026, 9, 13, tzinfo=UTC),
    )


def test_delivery_unknown_is_reconciliation_not_retry() -> None:
    validator = _validator()
    documents = _documents()
    job = _job()
    receipt = _receipt(documents, job)
    assert validator.validate_document("receipt", receipt) == []

    replayable = {**receipt, "retryDisposition": "eligible", "nextRetryAt": "2026-09-13T00:00:03Z"}
    findings = validator.validate_document("receipt", replayable)
    assert any("delivery-unknown requires retryDisposition=reconcile-first" in item for item in findings)
    assert any("cannot schedule retry before reconciliation" in item for item in findings)

    # All authority, identity, capability, candidate and budget axes are intentionally valid here;
    # delivery ambiguity is the sole reason fresh dispatch must be rejected in favor of reconciliation.
    decision = _evaluate_external_dispatch(validator, documents, job, receipt)
    assert decision["disposition"] == "ReconciliationRequired"


def test_stale_generation_handoff_cannot_be_actionable_before_digest_check() -> None:
    validator = _validator()
    job = _job()
    handoff = {
        "schema_version": 2,
        "handoffId": "handoff-1",
        "jobId": job["jobId"],
        "lineageId": job["lineageId"],
        "generation": job["generation"],
        "subject": job["subject"],
        "candidate": job["candidate"],
        "status": "completed",
        "actionable": True,
        "outcome": "verified",
        "evidenceRefs": ["evidence-1"],
        "artifactRefs": [],
        "externalOperationRefs": ["operation-1"],
        "gaps": [],
        "failureClass": None,
        "correlationId": job["jobId"],
        "sealedAt": "2026-09-13T00:05:00Z",
        "digest": "sha256:" + "0" * 64,
    }
    handoff["digest"] = validator.compute_handoff_digest(handoff)
    findings = validator.validate_handoff_current(
        handoff,
        current_job_id=job["jobId"],
        current_generation=job["generation"] + 1,
        current_lineage_id=job["lineageId"],
        current_subject=job["subject"],
        current_candidate=job["candidate"],
    )
    assert findings == ["handoff: stale job/generation cannot be actionable"]


def test_manifest_composes_server_and_consumer_standards() -> None:
    documents = _documents()
    validator = _validator()
    profile = json.loads(json.dumps(documents["steward_profile"]))
    profile["credentials"]["fallback"]["enabled"] = True
    profile["credentials"]["fallback"]["preserve_principal_scope"] = False
    profile["credentials"]["fallback"]["preserve_target"] = False
    findings = validator.validate_document("profile", profile)
    assert findings
    assert any("preserve_principal_scope" in item or "preserve_target" in item for item in findings)

    manifest = (SKILL / "manifest.yaml").read_text(encoding="utf-8")
    assert "mcp-server-architect" in manifest
    assert "mcp-server-consumer" in manifest

    job = _job()
    receipt = _receipt(documents, job)
    decision = _evaluate_external_dispatch(validator, documents, job, receipt)
    assert decision["disposition"] == "ReconciliationRequired"


def test_state_machine_v2_requires_production_reachability_and_liveness_closure() -> None:
    validator = _validator()
    machine = json.loads(json.dumps(_documents()["steward_state_machine"]))
    assert validator.validate_document("state-machine", machine) == []

    unreachable = json.loads(json.dumps(machine))
    unreachable["transitions"][0]["producer_refs"] = ["missing-producer"]
    findings = validator.validate_document("state-machine", unreachable)
    assert any("references unknown producers" in item for item in findings)

    no_producer = json.loads(json.dumps(machine))
    no_producer["transitions"][0]["producer_refs"] = []
    findings = validator.validate_document("state-machine", no_producer)
    assert any("no declared production producer path" in item or "non-empty" in item for item in findings)

    orphan = json.loads(json.dumps(machine))
    queued = next(item for item in orphan["states"] if item["id"] == "queued")
    queued["owner_lane"] = "none"
    queued["recovery"] = "none"
    queued["liveness"] = "active-work"
    findings = validator.validate_document("state-machine", orphan)
    assert any("requires an owning lane" in item for item in findings)

    direct_test_fixture_is_not_a_producer = json.loads(json.dumps(machine))
    direct_test_fixture_is_not_a_producer["producers"][0]["kind"] = "test-fixture"
    findings = validator.validate_document("state-machine", direct_test_fixture_is_not_a_producer)
    assert any("is not one of" in item and "test-fixture" in item for item in findings)

    gate_without_producer = json.loads(json.dumps(machine))
    work_gate = next(item for item in gate_without_producer["gates"] if item["id"] == "work-admission")
    work_gate["producer_refs"] = ["missing-producer"]
    findings = validator.validate_document("state-machine", gate_without_producer)
    assert any("gate work-admission references unknown producers" in item for item in findings)

    uncovered_mutation = json.loads(json.dumps(machine))
    mutation_gate = next(item for item in uncovered_mutation["gates"] if item["id"] == "mutation-admission")
    mutation_gate["transition_refs"].remove("dispatch-start")
    findings = validator.validate_document("state-machine", uncovered_mutation)
    assert any("does not cover mutation-gated transitions" in item for item in findings)

    shared_artifact_class = json.loads(json.dumps(machine))
    shared_artifact_class["checkpoints"][1]["artifact_class"] = shared_artifact_class["checkpoints"][0]["artifact_class"]
    assert validator.validate_document("state-machine", shared_artifact_class) == []

    terminal_resume = json.loads(json.dumps(machine))
    terminal_resume["checkpoints"][0]["resume_state"] = "completed"
    findings = validator.validate_document("state-machine", terminal_resume)
    assert any("resume state must be nonterminal" in item for item in findings)

    unreachable_resume = json.loads(json.dumps(machine))
    unreachable_resume["checkpoints"][0]["resume_state"] = "finalizing"
    findings = validator.validate_document("state-machine", unreachable_resume)
    assert any("resume state cannot reach checkpoint state" in item for item in findings)


def test_checkpoint_plan_reuses_current_artifacts_and_derives_minimum_recomputation() -> None:
    validator = _validator()
    machine = _documents()["steward_state_machine"]
    current = {
        dependency["id"]: f"{dependency['id']}@v1"
        for dependency in machine["semantic_dependencies"]
    }

    bindings: dict[str, dict[str, Any]] = {}
    ordered = sorted(machine["checkpoints"], key=lambda item: item["order"])
    for index, checkpoint in enumerate(ordered, start=1):
        upstream_bindings = {
            upstream_id: {
                "artifactRef": bindings[upstream_id]["artifactRef"],
                "artifactDigest": bindings[upstream_id]["artifactDigest"],
            }
            for upstream_id in checkpoint["upstream_checkpoint_refs"]
        }
        binding = {
            "schema_version": 1,
            "checkpointId": checkpoint["id"],
            "machineId": machine["machine_id"],
            "machineRevision": machine["revision"],
            "generation": 3,
            "artifactClass": checkpoint["artifact_class"],
            "artifactRef": f"artifact:{checkpoint['id']}:v1",
            "artifactDigest": "sha256:" + f"{index:064x}",
            "dependencyBindings": {
                dependency_id: current[dependency_id]
                for dependency_id in checkpoint["dependency_refs"]
            },
            "upstreamCheckpointBindings": upstream_bindings,
            "recoveryBindings": {
                "subjectIdentity": current["subject"],
                "candidateIdentity": current["candidate"],
                "authorityRef": "authority:steward-runtime",
                "ownershipRef": "lease:attempt-1",
                "progressRevision": index,
                "budgetRef": "budget:job-1",
                "deadlineRef": "deadline:job-1",
                "blockerRefs": [],
                "externalOperationRefs": [],
            },
        }
        assert validator.validate_document("checkpoint", binding) == []
        bindings[checkpoint["id"]] = binding

    baseline = validator.derive_checkpoint_plan(
        machine,
        current_generation=3,
        current_dependencies=current,
        checkpoint_bindings=bindings,
    )
    assert baseline["requiredRecomputations"] == []
    assert baseline["earliestSafeStage"] is None
    assert baseline["reasonCodes"] == []

    late_outage_bindings = json.loads(json.dumps(bindings))
    late_outage_bindings.pop("completion-candidate")
    late_outage = validator.derive_checkpoint_plan(
        machine,
        current_generation=3,
        current_dependencies=current,
        checkpoint_bindings=late_outage_bindings,
    )
    assert late_outage["requiredRecomputations"] == ["completion-candidate"]
    assert late_outage["earliestSafeStage"] == "finalizing"
    assert late_outage["reusableArtifactRefs"] == [
        "artifact:external-dispatch:v1",
        "artifact:provider-result:v1",
    ]
    assert late_outage["staleArtifactRefs"] == []
    assert late_outage["reasonCodes"] == ["checkpoint-missing:completion-candidate"]

    changed_late_policy = dict(current)
    changed_late_policy["completion-policy"] = "completion-policy@v2"
    plan = validator.derive_checkpoint_plan(
        machine,
        current_generation=3,
        current_dependencies=changed_late_policy,
        checkpoint_bindings=bindings,
    )
    assert plan["requiredRecomputations"] == ["completion-candidate"]
    assert plan["earliestSafeStage"] == "finalizing"
    assert plan["reusableArtifactRefs"] == [
        "artifact:external-dispatch:v1",
        "artifact:provider-result:v1",
    ]
    assert plan["staleArtifactRefs"] == ["artifact:completion-candidate:v1"]
    assert plan["reasonCodes"] == [
        "dependency-changed:completion-candidate:completion-policy"
    ]

    restarted = validator.derive_checkpoint_plan(
        machine,
        current_generation=3,
        current_dependencies=changed_late_policy,
        checkpoint_bindings=bindings,
    )
    assert restarted == plan

    changed_evidence = dict(current)
    changed_evidence["provider-result"] = "provider-result@v2"
    evidence_plan = validator.derive_checkpoint_plan(
        machine,
        current_generation=3,
        current_dependencies=changed_evidence,
        checkpoint_bindings=bindings,
    )
    assert evidence_plan["requiredRecomputations"] == [
        "provider-result",
        "completion-candidate",
    ]
    assert evidence_plan["earliestSafeStage"] == "waiting-external"
    assert evidence_plan["reusableArtifactRefs"] == ["artifact:external-dispatch:v1"]
    assert "dependency-changed:provider-result:provider-result" in evidence_plan["reasonCodes"]
    assert "upstream-stale:completion-candidate:provider-result" in evidence_plan["reasonCodes"]

    mismatched_recovery_subject = json.loads(json.dumps(bindings))
    mismatched_recovery_subject["completion-candidate"]["recoveryBindings"]["subjectIdentity"] = "subject:other"
    recovery_subject_plan = validator.derive_checkpoint_plan(
        machine,
        current_generation=3,
        current_dependencies=current,
        checkpoint_bindings=mismatched_recovery_subject,
    )
    assert recovery_subject_plan["requiredRecomputations"] == ["completion-candidate"]
    assert recovery_subject_plan["reasonCodes"] == ["recovery-subject-mismatch:completion-candidate"]

    mismatched_recovery_candidate = json.loads(json.dumps(bindings))
    mismatched_recovery_candidate["provider-result"]["recoveryBindings"]["candidateIdentity"] = "candidate:other"
    recovery_candidate_plan = validator.derive_checkpoint_plan(
        machine,
        current_generation=3,
        current_dependencies=current,
        checkpoint_bindings=mismatched_recovery_candidate,
    )
    assert recovery_candidate_plan["requiredRecomputations"] == [
        "provider-result",
        "completion-candidate",
    ]
    assert "recovery-candidate-mismatch:provider-result" in recovery_candidate_plan["reasonCodes"]
    assert "upstream-stale:completion-candidate:provider-result" in recovery_candidate_plan["reasonCodes"]

    changed_upstream_artifact = json.loads(json.dumps(bindings))
    changed_upstream_artifact["completion-candidate"]["upstreamCheckpointBindings"]["provider-result"][
        "artifactDigest"
    ] = "sha256:" + "f" * 64
    upstream_plan = validator.derive_checkpoint_plan(
        machine,
        current_generation=3,
        current_dependencies=current,
        checkpoint_bindings=changed_upstream_artifact,
    )
    assert upstream_plan["requiredRecomputations"] == ["completion-candidate"]
    assert upstream_plan["reusableArtifactRefs"] == [
        "artifact:external-dispatch:v1",
        "artifact:provider-result:v1",
    ]
    assert upstream_plan["reasonCodes"] == [
        "upstream-artifact-changed:completion-candidate:provider-result"
    ]

    changed_candidate = dict(current)
    changed_candidate["candidate"] = "candidate@v2"
    invalidated = validator.derive_checkpoint_plan(
        machine,
        current_generation=3,
        current_dependencies=changed_candidate,
        checkpoint_bindings=bindings,
    )
    assert invalidated["requiredRecomputations"] == [
        "external-dispatch",
        "provider-result",
        "completion-candidate",
    ]
    assert invalidated["earliestSafeStage"] == "queued"

    next_generation = validator.derive_checkpoint_plan(
        machine,
        current_generation=4,
        current_dependencies=current,
        checkpoint_bindings=bindings,
    )
    assert next_generation["requiredRecomputations"] == [
        "external-dispatch",
        "provider-result",
        "completion-candidate",
    ]
    assert next_generation["earliestSafeStage"] == "queued"
    assert all(
        code.startswith("checkpoint-generation-mismatch:")
        or code.startswith("upstream-stale:")
        for code in next_generation["reasonCodes"]
    )

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

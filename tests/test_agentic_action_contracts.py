from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
if str(CONTRACTS) not in sys.path:
    sys.path.insert(0, str(CONTRACTS))

from deployment_lease import DeploymentLeaseError, admit_lease  # noqa: E402
from runtime_identity import RuntimeIdentityError, verify_runtime_chain  # noqa: E402
from tool_result_envelope import add_runtime_annotation, source_sha256  # noqa: E402


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


def _outcome(**overrides: object) -> dict:
    value = {
        "schema_version": 1,
        "transport": "succeeded",
        "execution": "succeeded",
        "side_effect": "confirmed",
        "artifact": "none",
        "verification": "passed",
        "disposition": "completed",
        "safe_to_retry": "no",
    }
    value.update(overrides)
    return value


def test_timeout_can_coexist_with_confirmed_external_side_effect() -> None:
    value = _outcome(transport="timed_out", side_effect="confirmed", safe_to_retry="no")
    _validator("action-outcome.schema.json").validate(value)


def test_worker_completed_without_required_artifact_cannot_be_completed() -> None:
    with pytest.raises(ValidationError):
        _validator("action-outcome.schema.json").validate(_outcome(artifact="missing"))


def test_published_artifact_and_failed_verification_remain_distinct() -> None:
    value = _outcome(
        artifact="published",
        verification="failed",
        disposition="failed",
        side_effect="published",
    )
    _validator("action-outcome.schema.json").validate(value)
    assert value["artifact"] == "published"
    assert value["verification"] == "failed"


def test_stale_verification_cannot_be_completed() -> None:
    with pytest.raises(ValidationError):
        _validator("action-outcome.schema.json").validate(_outcome(verification="stale"))


def _runtime(generation: str, *, source: str = "a" * 40, digest: str | None = None) -> dict:
    return {
        "schema_version": 1,
        "runtime_id": "service-a",
        "source_revision": source,
        "artifact_digest": digest or "sha256:" + "b" * 64,
        "artifact_version": "2.0.0",
        "instance_generation": generation,
        "config_revision": "config-1",
        "started_at": "2026-09-10T00:00:00Z",
        "owner": "service-owner",
        "provenance_refs": [],
    }


def test_runtime_identity_chain_rejects_candidate_source_mismatch() -> None:
    with pytest.raises(RuntimeIdentityError, match="candidate runtime source revision"):
        verify_runtime_chain(
            expected_source_revision="a" * 40,
            expected_artifact_digest="sha256:" + "b" * 64,
            candidate_runtime=_runtime("candidate-1", source="c" * 40),
            deployed_runtime=_runtime("deployed-1"),
        )


def test_restart_same_artifact_requires_new_generation_when_requested() -> None:
    receipt = verify_runtime_chain(
        expected_source_revision="a" * 40,
        expected_artifact_digest="sha256:" + "b" * 64,
        candidate_runtime=_runtime("candidate-1"),
        deployed_runtime=_runtime("deployed-2"),
        previous_deployed_runtime=_runtime("deployed-1"),
        require_new_generation=True,
    )
    assert receipt.artifact_digest == "sha256:" + "b" * 64
    assert receipt.previous_evidence_stale is True


def test_same_generation_cannot_prove_restart() -> None:
    with pytest.raises(RuntimeIdentityError, match="new instance generation"):
        verify_runtime_chain(
            expected_source_revision="a" * 40,
            expected_artifact_digest="sha256:" + "b" * 64,
            candidate_runtime=_runtime("candidate-1"),
            deployed_runtime=_runtime("deployed-1"),
            previous_deployed_runtime=_runtime("deployed-1"),
            require_new_generation=True,
        )


def test_source_hash_is_stable_when_runtime_annotation_is_added() -> None:
    source = b"provider exact bytes\n"
    digest = source_sha256(source)
    envelope = {
        "schema_version": 1,
        "data": source.decode(),
        "data_sha256": digest,
        "provenance": {"data_source": "provider", "source_id": "provider:1"},
        "annotations": [],
    }
    updated = add_runtime_annotation(envelope, kind="routing", text="open details only if needed")
    _validator("tool-result-envelope.schema.json").validate(updated)
    assert updated["data"] == envelope["data"]
    assert updated["data_sha256"] == digest
    assert envelope["annotations"] == []


def test_multipart_parts_keep_independent_provenance_and_annotations() -> None:
    envelope = {
        "schema_version": 1,
        "parts": [
            {
                "data": "first",
                "data_sha256": source_sha256(b"first"),
                "provenance": {"data_source": "tool", "source_id": "stream:1"},
                "annotations": [],
            },
            {
                "data": "second",
                "data_sha256": source_sha256(b"second"),
                "provenance": {"data_source": "tool", "source_id": "stream:2"},
                "annotations": [],
            },
        ],
        "annotations": [],
    }
    updated = add_runtime_annotation(envelope, kind="warning", text="second part is truncated", part_index=1)
    _validator("tool-result-envelope.schema.json").validate(updated)
    assert updated["parts"][0]["annotations"] == []
    assert updated["parts"][1]["annotations"][0]["source"] == "runtime"
    assert updated["parts"][1]["data"] == "second"


def _lease(**overrides: object) -> dict:
    value = {
        "schema_version": 1,
        "lease_id": "lease-1",
        "principal": "release-agent",
        "session": "session-1",
        "target": {"project": "owner/repo", "environment": "staging", "resource": "service/api"},
        "artifact_digest": "sha256:" + "b" * 64,
        "source_revision": "a" * 40,
        "action": "deploy",
        "normalized_args_digest": "hmac-sha256:" + "c" * 64,
        "policy_revision": "deploy-policy-1",
        "issued_at": "2026-09-10T00:00:00Z",
        "expires_at": "2026-09-10T01:00:00Z",
        "state": "active",
        "evidence_refs": [],
    }
    value.update(overrides)
    return value


def _admit(lease: dict, **overrides: object):
    args = {
        "principal": "release-agent",
        "session": "session-1",
        "target": {"project": "owner/repo", "environment": "staging", "resource": "service/api"},
        "artifact_digest": "sha256:" + "b" * 64,
        "action": "deploy",
        "normalized_args_digest": "hmac-sha256:" + "c" * 64,
        "now": datetime(2026, 9, 10, 0, 30, tzinfo=timezone.utc),
        "consumed_lease_ids": (),
    }
    args.update(overrides)
    return admit_lease(lease, **args)


def test_deployment_lease_admits_exact_target_only() -> None:
    lease = _lease()
    _validator("deployment-lease.schema.json").validate(lease)
    admission = _admit(lease)
    assert admission.target_environment == "staging"
    assert admission.session == "session-1"
    with pytest.raises(DeploymentLeaseError, match="target.environment"):
        _admit(lease, target={"project": "owner/repo", "environment": "production", "resource": "service/api"})


def test_deployment_lease_rejects_session_mismatch_or_missing_session() -> None:
    with pytest.raises(DeploymentLeaseError, match="session"):
        _admit(_lease(), session="session-2")
    with pytest.raises(DeploymentLeaseError, match="session"):
        _admit(_lease(), session=None)


@pytest.mark.parametrize("state", ["used", "revoked", "expired"])
def test_non_active_lease_fails_before_mutation(state: str) -> None:
    with pytest.raises(DeploymentLeaseError, match="not active"):
        _admit(_lease(state=state))


def test_consumed_lease_cannot_be_replayed() -> None:
    with pytest.raises(DeploymentLeaseError, match="already consumed"):
        _admit(_lease(), consumed_lease_ids={"lease-1"})


def test_parent_lease_does_not_authorize_child_principal() -> None:
    with pytest.raises(DeploymentLeaseError, match="principal"):
        _admit(_lease(), principal="delegated-child")


def test_audit_event_accepts_ambiguous_mutation_without_false_success() -> None:
    event = {
        "schema_version": 1,
        "event_id": "event-1",
        "correlation_id": "task-1",
        "timestamp": "2026-09-10T00:30:00Z",
        "actor": {"principal": "agent", "session": "session-1"},
        "action": {
            "capability": "external.send",
            "operation": "create",
            "target": "message:customer",
            "normalized_args_digest": "hmac-sha256:" + "d" * 64,
            "idempotency_key_ref": "opaque://send/1",
        },
        "runtime": None,
        "outcome": _outcome(
            transport="timed_out",
            execution="unknown",
            side_effect="unknown",
            artifact="none",
            verification="not_run",
            disposition="reconcile_required",
            safe_to_retry="unknown",
        ),
        "artifact_refs": [],
        "evidence_refs": ["reconcile://pending/1"],
        "policy_refs": ["policy://external-send/1"],
        "approval_refs": [],
        "retention_class": "operational-90d",
        "extensions": {},
    }
    _validator("audit-event.schema.json").validate(event)


def test_audit_rejects_plain_sha256_argument_fingerprint() -> None:
    event = {
        "schema_version": 1,
        "event_id": "event-2",
        "correlation_id": "task-1",
        "timestamp": "2026-09-10T00:30:00Z",
        "actor": {"principal": "agent"},
        "action": {
            "capability": "deploy",
            "operation": "invoke",
            "target": "staging",
            "normalized_args_digest": "sha256:" + "e" * 64,
        },
        "outcome": _outcome(),
        "retention_class": "operational-90d",
    }
    with pytest.raises(ValidationError):
        _validator("audit-event.schema.json").validate(event)

"""Regressions for DeploymentLease v2 target-generation fencing."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
if str(CONTRACTS) not in sys.path:
    sys.path.insert(0, str(CONTRACTS))

from deployment_lease import (  # noqa: E402
    DeploymentAdmissionDisposition,
    DeploymentLeaseAuthorityRecord,
    DeploymentMutationReservation,
    DeploymentTargetState,
    FenceMode,
    MutationDomainSnapshot,
    admit_and_reserve_fenced_mutation,
    admit_fenced_lease,
    fencing_audit_projection,
    mark_delivery_unknown,
    reconcile_mutation,
    snapshot_after_reservation,
)

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


def _lease(*, lease_id: str = "lease:A", artifact: str | None = None, action: str = "deploy") -> dict[str, Any]:
    return {
        "schema_version": 2,
        "lease_id": lease_id,
        "principal": "release-control",
        "session": "run:1",
        "target": {
            "project": "owner/repo",
            "environment": "production",
            "resource": "service/api",
            "mutation_domain": "service/api:production:active",
        },
        "artifact_digest": artifact or "sha256:" + "a" * 64,
        "source_revision": "b" * 40,
        "action": action,
        "normalized_args_digest": "hmac-sha256:" + "c" * 64,
        "policy_revision": "deploy-policy:2",
        "issued_at": "2026-10-06T11:00:00Z",
        "expires_at": "2026-10-06T13:00:00Z",
        "state": "active",
        "expected_current": {
            "deployment_generation": "deploy:7",
            "runtime_instance_generation": "runtime:7",
            "artifact_digest": "sha256:" + "0" * 64,
            "config_revision": "config:7",
            "provider_revision_or_etag": "etag:7",
        },
        "fence": {"mode": "broker_single_writer", "token_or_generation": "fence:7"},
        "evidence_refs": ["runtime-acceptance:7"],
    }


def _target_state(*, fence: str = "fence:7", domain: str = "service/api:production:active") -> DeploymentTargetState:
    advanced = fence != "fence:7"
    return DeploymentTargetState(
        mutation_domain=domain,
        fence_token_or_generation=fence,
        deployment_generation="deploy:8" if advanced else "deploy:7",
        runtime_instance_generation="runtime:8" if advanced else "runtime:7",
        artifact_digest="sha256:" + ("a" if advanced else "0") * 64,
        config_revision="config:8" if advanced else "config:7",
        provider_revision_or_etag="etag:8" if advanced else "etag:7",
    )


def _record(value: dict[str, Any]) -> DeploymentLeaseAuthorityRecord:
    return DeploymentLeaseAuthorityRecord("authority:primary", "attestation:" + str(value["lease_id"]), value)


def _verifier(expected: dict[str, Any]):
    def verify(value: DeploymentLeaseAuthorityRecord) -> bool:
        return value.source_ref == "authority:primary" and value.lease == expected
    return verify


def _args(value: dict[str, Any], snapshot: MutationDomainSnapshot) -> dict[str, Any]:
    target = value["target"]
    assert isinstance(target, dict)
    return {
        "verify_authority_record": _verifier(value),
        "principal": "release-control",
        "session": "run:1",
        "target": target,
        "artifact_digest": str(value["artifact_digest"]),
        "action": str(value["action"]),
        "normalized_args_digest": "hmac-sha256:" + "c" * 64,
        "policy_revision": "deploy-policy:2",
        "source_revision": "b" * 40,
        "now": NOW,
        "domain_snapshot": snapshot,
    }


class _Store:
    def __init__(self, snapshot: MutationDomainSnapshot) -> None:
        self.snapshot = snapshot

    def reserve(self, expected: MutationDomainSnapshot, reservation: DeploymentMutationReservation) -> bool:
        if self.snapshot != expected or self.snapshot.active_operation_ref is not None:
            return False
        self.snapshot = snapshot_after_reservation(self.snapshot, reservation)
        return True


def test_v1_schema_remains_valid_while_v2_requires_fencing_fields() -> None:
    schema = json.loads((CONTRACTS / "deployment-lease.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    v1 = _lease()
    v1["schema_version"] = 1
    target = dict(v1["target"])
    target.pop("mutation_domain")
    v1["target"] = target
    v1.pop("expected_current")
    v1.pop("fence")
    validator.validate(v1)
    validator.validate(_lease())
    missing_fence = _lease()
    missing_fence.pop("fence")
    with pytest.raises(ValidationError):
        validator.validate(missing_fence)


def test_concurrent_leases_same_domain_have_one_dispatch_winner() -> None:
    initial = MutationDomainSnapshot(_target_state())
    first = _lease(lease_id="lease:A", artifact="sha256:" + "a" * 64)
    second = _lease(lease_id="lease:B", artifact="sha256:" + "d" * 64)
    store = _Store(initial)
    admitted, reservation = admit_and_reserve_fenced_mutation(
        _record(first), operation_ref="op:A", reserve_if_current=store.reserve, **_args(first, initial)
    )
    assert admitted.operation_may_dispatch and reservation is not None
    lost, second_reservation = admit_and_reserve_fenced_mutation(
        _record(second), operation_ref="op:B", reserve_if_current=store.reserve, **_args(second, initial)
    )
    assert lost.disposition is DeploymentAdmissionDisposition.CONFLICTING_MUTATION_ACTIVE
    assert not lost.operation_may_dispatch and second_reservation is None


def test_restart_unknown_delivery_and_rollback_race_stay_blocked() -> None:
    initial = MutationDomainSnapshot(_target_state())
    first = _lease(lease_id="lease:A")
    rollback = _lease(lease_id="lease:B", action="rollback")
    store = _Store(initial)
    admitted, reservation = admit_and_reserve_fenced_mutation(
        _record(first), operation_ref="op:A", reserve_if_current=store.reserve, **_args(first, initial)
    )
    assert admitted.operation_may_dispatch and reservation is not None
    rollback_args = _args(rollback, store.snapshot)
    assert admit_fenced_lease(_record(rollback), **rollback_args).disposition is DeploymentAdmissionDisposition.CONFLICTING_MUTATION_ACTIVE
    pending = mark_delivery_unknown(store.snapshot, operation_ref="op:A")
    assert pending.unresolved_external_effect
    assert admit_fenced_lease(_record(rollback), **{**rollback_args, "domain_snapshot": pending}).disposition is DeploymentAdmissionDisposition.CONFLICTING_MUTATION_ACTIVE


def test_success_advances_fence_and_old_lease_is_stale() -> None:
    initial = MutationDomainSnapshot(_target_state())
    value = _lease()
    store = _Store(initial)
    admitted, reservation = admit_and_reserve_fenced_mutation(
        _record(value), operation_ref="op:A", reserve_if_current=store.reserve, **_args(value, initial)
    )
    assert admitted.operation_may_dispatch and reservation is not None
    pending = mark_delivery_unknown(store.snapshot, operation_ref="op:A")
    advanced = reconcile_mutation(pending, operation_ref="op:A", effect_applied=True, observed_target=_target_state(fence="fence:8"))
    stale = admit_fenced_lease(_record(_lease(lease_id="lease:B")), **_args(_lease(lease_id="lease:B"), advanced))
    assert stale.disposition is DeploymentAdmissionDisposition.STALE_LEASE
    assert not stale.operation_may_dispatch


def test_independent_domains_and_provider_cas_precondition() -> None:
    value = _lease(lease_id="lease:worker")
    target = dict(value["target"])
    target["resource"] = "service/worker"
    target["mutation_domain"] = "service/worker:production:active"
    value["target"] = target
    snapshot = MutationDomainSnapshot(_target_state(domain="service/worker:production:active"))
    assert admit_fenced_lease(_record(value), **_args(value, snapshot)).operation_may_dispatch
    provider = _lease(lease_id="lease:provider")
    provider["fence"] = {"mode": "provider_cas", "token_or_generation": "fence:7"}
    admitted = admit_fenced_lease(_record(provider), **_args(provider, MutationDomainSnapshot(_target_state())))
    assert admitted.fence_mode is FenceMode.PROVIDER_CAS
    assert admitted.provider_precondition_token == "fence:7"


def test_changed_unknown_and_compatible_target_states_never_dispatch() -> None:
    value = _lease()
    current = _target_state()
    changed = DeploymentTargetState(
        mutation_domain=current.mutation_domain,
        fence_token_or_generation=current.fence_token_or_generation,
        deployment_generation="deploy:8",
        runtime_instance_generation=current.runtime_instance_generation,
        artifact_digest=current.artifact_digest,
        config_revision=current.config_revision,
        provider_revision_or_etag=current.provider_revision_or_etag,
    )
    result = admit_fenced_lease(_record(value), **_args(value, MutationDomainSnapshot(changed)))
    assert result.disposition is DeploymentAdmissionDisposition.TARGET_CHANGED and not result.operation_may_dispatch
    unknown = DeploymentTargetState(
        mutation_domain=current.mutation_domain,
        fence_token_or_generation=current.fence_token_or_generation,
        deployment_generation=None,
        runtime_instance_generation=current.runtime_instance_generation,
        artifact_digest=current.artifact_digest,
        config_revision=current.config_revision,
        provider_revision_or_etag=current.provider_revision_or_etag,
    )
    result = admit_fenced_lease(_record(value), **_args(value, MutationDomainSnapshot(unknown)))
    assert result.disposition is DeploymentAdmissionDisposition.TARGET_STATE_UNKNOWN and not result.operation_may_dispatch
    result = admit_fenced_lease(
        _record(value),
        compatible_advancement_proof_ref="policy-proof:1",
        **_args(value, MutationDomainSnapshot(changed)),
    )
    assert result.disposition is DeploymentAdmissionDisposition.TARGET_ADVANCED_COMPATIBLE
    assert not result.operation_may_dispatch


def test_candidate_cannot_refresh_authority_and_runtime_evidence_never_mints_it() -> None:
    authoritative = _lease()
    tampered = dict(authoritative)
    tampered["fence"] = {"mode": "broker_single_writer", "token_or_generation": "fence:8"}
    kwargs = _args(tampered, MutationDomainSnapshot(_target_state(fence="fence:8")))
    kwargs["verify_authority_record"] = _verifier(authoritative)
    assert admit_fenced_lease(_record(tampered), **kwargs).disposition is DeploymentAdmissionDisposition.LOST_AUTHORITY
    runtime_only = _args(authoritative, MutationDomainSnapshot(_target_state()))
    runtime_only["verify_authority_record"] = lambda _: False
    assert admit_fenced_lease(_record(authoritative), **runtime_only).disposition is DeploymentAdmissionDisposition.LOST_AUTHORITY


def test_no_effect_and_audit_projection_are_bounded() -> None:
    initial = MutationDomainSnapshot(_target_state())
    value = _lease()
    store = _Store(initial)
    admission, reservation = admit_and_reserve_fenced_mutation(
        _record(value), operation_ref="op:A", reserve_if_current=store.reserve, **_args(value, initial)
    )
    assert reservation is not None
    assert reconcile_mutation(store.snapshot, operation_ref="op:A", effect_applied=False, observed_target=initial.target) == initial
    projection = fencing_audit_projection(admission, reservation)
    assert projection["mutationDomain"] == "service/api:production:active"
    assert "principal" not in projection and "session" not in projection
    assert "credential" not in repr(projection).lower()


class _ConsumingStore:
    def __init__(self, snapshot: MutationDomainSnapshot) -> None:
        self.snapshot = snapshot
        self.consumed_lease_ids: set[str] = set()

    def reserve(self, expected: MutationDomainSnapshot, reservation: DeploymentMutationReservation) -> bool:
        if reservation.lease_id in self.consumed_lease_ids:
            return False
        if self.snapshot != expected or self.snapshot.active_operation_ref is not None:
            return False
        self.consumed_lease_ids.add(reservation.lease_id)
        self.snapshot = snapshot_after_reservation(self.snapshot, reservation)
        return True


def test_consumed_v2_lease_cannot_replay_after_no_effect_reconciliation() -> None:
    initial = MutationDomainSnapshot(_target_state())
    value = _lease(lease_id="lease:one-shot")
    store = _ConsumingStore(initial)
    admission, reservation = admit_and_reserve_fenced_mutation(
        _record(value),
        operation_ref="op:one-shot",
        reserve_if_current=store.reserve,
        **_args(value, initial),
    )
    assert admission.operation_may_dispatch and reservation is not None

    cleared = reconcile_mutation(
        store.snapshot,
        operation_ref="op:one-shot",
        effect_applied=False,
        observed_target=initial.target,
    )
    replay = admit_fenced_lease(
        _record(value),
        consumed_lease_ids=store.consumed_lease_ids,
        **_args(value, cleared),
    )
    assert replay.disposition is DeploymentAdmissionDisposition.LEASE_NOT_ACTIVE
    assert not replay.operation_may_dispatch


def test_provider_cas_rejects_stale_provider_revision_before_dispatch() -> None:
    value = _lease(lease_id="lease:provider-cas")
    value["fence"] = {"mode": "provider_cas", "token_or_generation": "fence:7"}
    current = _target_state()
    drifted = DeploymentTargetState(
        mutation_domain=current.mutation_domain,
        fence_token_or_generation=current.fence_token_or_generation,
        deployment_generation=current.deployment_generation,
        runtime_instance_generation=current.runtime_instance_generation,
        artifact_digest=current.artifact_digest,
        config_revision=current.config_revision,
        provider_revision_or_etag="etag:8",
    )
    admission = admit_fenced_lease(_record(value), **_args(value, MutationDomainSnapshot(drifted)))
    assert admission.fence_mode is FenceMode.PROVIDER_CAS
    assert admission.disposition is DeploymentAdmissionDisposition.TARGET_CHANGED
    assert not admission.operation_may_dispatch


def test_independent_mutation_domains_can_reserve_concurrently() -> None:
    api = _lease(lease_id="lease:api")
    api_store = _ConsumingStore(MutationDomainSnapshot(_target_state()))
    api_admission, api_reservation = admit_and_reserve_fenced_mutation(
        _record(api),
        operation_ref="op:api",
        reserve_if_current=api_store.reserve,
        **_args(api, api_store.snapshot),
    )

    worker = _lease(lease_id="lease:worker")
    target = dict(worker["target"])
    target["resource"] = "service/worker"
    target["mutation_domain"] = "service/worker:production:active"
    worker["target"] = target
    worker_store = _ConsumingStore(
        MutationDomainSnapshot(_target_state(domain="service/worker:production:active"))
    )
    worker_admission, worker_reservation = admit_and_reserve_fenced_mutation(
        _record(worker),
        operation_ref="op:worker",
        reserve_if_current=worker_store.reserve,
        **_args(worker, worker_store.snapshot),
    )

    assert api_admission.operation_may_dispatch and api_reservation is not None
    assert worker_admission.operation_may_dispatch and worker_reservation is not None


def test_audit_projection_includes_resulting_target_without_secrets() -> None:
    initial = MutationDomainSnapshot(_target_state())
    value = _lease(lease_id="lease:audit")
    store = _ConsumingStore(initial)
    admission, reservation = admit_and_reserve_fenced_mutation(
        _record(value),
        operation_ref="op:audit",
        reserve_if_current=store.reserve,
        **_args(value, initial),
    )
    assert reservation is not None
    resulting = _target_state(fence="fence:8")
    projection = fencing_audit_projection(admission, reservation, resulting)
    assert projection["resultingFenceTokenOrGeneration"] == "fence:8"
    assert projection["resultingArtifactDigest"] == "sha256:" + "a" * 64
    assert "principal" not in projection
    assert "session" not in projection
    assert "credential" not in repr(projection).lower()

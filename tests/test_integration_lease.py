"""Regressions for exact autonomous repository integration authority."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/mcp-steward-architect"
TOOL = SKILL / "tools/integration_lease.py"
REFERENCE = SKILL / "references/integration-lease.md"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _fixture(module: ModuleType):
    issued = datetime(2026, 10, 6, 8, 0, tzinfo=timezone.utc)
    lease = module.IntegrationLease(
        lease_id="lease:1",
        authority_principal_ref="control:release",
        repository_ref="repo:a",
        change_ref="change:10",
        candidate_head_sha="C1",
        candidate_tree_sha="TREE1",
        target_ref="refs/heads/main",
        observed_base_sha="B1",
        base_policy=module.BasePolicy.EXACT,
        merge_strategy=module.MergeStrategy.SQUASH,
        required_evidence_set_digest="sha256:E1",
        review_policy_revision="review:v2",
        verification_policy_revision="verify:v3",
        autonomy_policy_revision="autonomy:v4",
        execution_generation="gen:7",
        issued_at=issued,
        expires_at=issued + timedelta(hours=1),
    )
    evidence = module.IntegrationEvidenceSnapshot(
        evidence_set_digest="sha256:E1",
        review_ref="review:1",
        review_current=True,
        verification_ref="verify:1",
        verification_current=True,
        review_policy_revision="review:v2",
        verification_policy_revision="verify:v3",
    )
    repository = module.IntegrationRepositoryState(
        repository_ref="repo:a",
        change_ref="change:10",
        current_head_sha="C1",
        current_tree_sha="TREE1",
        current_target_ref="refs/heads/main",
        current_base_sha="B1",
        base_advance_compatible=False,
        provider_allows_integration=True,
        execution_generation="gen:7",
        current_autonomy_policy_revision="autonomy:v4",
    )
    return lease, evidence, repository, issued


def _admit(module: ModuleType, lease, evidence, repository, issued, *, actor="control:release"):
    return module.admit_integration(
        lease,
        acting_principal_ref=actor,
        now=issued + timedelta(minutes=5),
        repository=repository,
        evidence=evidence,
    )


def _reserve(module: ModuleType, lease, evidence, repository, issued, *, operation_ref="op:1"):
    return module.admit_and_reserve_integration(
        lease,
        acting_principal_ref="control:release",
        now=issued + timedelta(minutes=5),
        repository=repository,
        evidence=evidence,
        operation_ref=operation_ref,
    )


def test_squash_reconciliation_preserves_candidate_to_integrated_lineage() -> None:
    integration = _load("integration_lease_squash")
    lease, evidence, repository, issued = _fixture(integration)
    admission, used, operation = _reserve(
        integration, lease, evidence, repository, issued
    )
    assert admission.operation_may_dispatch
    assert operation is not None
    assert used.state is integration.IntegrationLeaseState.USED
    assert used.consumed_by_operation_ref == "op:1"

    operation = integration.note_dispatch(
        operation,
        integration.DispatchObservation.DELIVERY_UNKNOWN,
    )
    observation = integration.IntegrationObservation(
        change_ref="change:10",
        observed_candidate_sha="C1",
        target_ref="refs/heads/main",
        target_before_sha="B1",
        target_after_sha="I1",
        integrated=True,
        integrated_sha="I1",
    )
    operation, result = integration.reconcile_integration(
        operation,
        observation,
        lineage_proof_ref="proof:squash:C1:I1",
    )

    assert operation.state is integration.IntegrationOperationState.INTEGRATED
    assert result is not None
    assert result.candidate_sha == "C1"
    assert result.integrated_sha == "I1"
    assert result.candidate_sha != result.integrated_sha
    projection = integration.to_integration_receipt_projection(result)
    assert projection["receiptKind"] == "integration"
    assert projection["evidenceSetDigest"] == "sha256:E1"
    assert projection["autonomyPolicyRevision"] == "autonomy:v4"


def test_push_writer_or_child_actor_cannot_mint_integration_authority() -> None:
    integration = _load("integration_lease_child")
    lease, evidence, repository, issued = _fixture(integration)
    admission = _admit(
        integration,
        lease,
        evidence,
        repository,
        issued,
        actor="worker:child-with-push-token",
    )
    assert admission.disposition is integration.IntegrationAdmissionDisposition.LOST_AUTHORITY
    assert not admission.operation_may_dispatch


def test_candidate_base_tree_policy_and_evidence_drift_fail_closed() -> None:
    integration = _load("integration_lease_drift")
    lease, evidence, repository, issued = _fixture(integration)

    assert _admit(
        integration,
        lease,
        evidence,
        replace(repository, current_head_sha="C2"),
        issued,
    ).disposition is integration.IntegrationAdmissionDisposition.STALE_CANDIDATE
    assert _admit(
        integration,
        lease,
        evidence,
        replace(repository, current_tree_sha="TREE2"),
        issued,
    ).disposition is integration.IntegrationAdmissionDisposition.STALE_CANDIDATE
    assert _admit(
        integration,
        lease,
        evidence,
        replace(repository, current_autonomy_policy_revision="autonomy:v5"),
        issued,
    ).disposition is integration.IntegrationAdmissionDisposition.LOST_AUTHORITY
    assert _admit(
        integration,
        lease,
        evidence,
        replace(repository, current_base_sha="B2"),
        issued,
    ).disposition is integration.IntegrationAdmissionDisposition.BASE_TOPOLOGY_CHANGED

    admission, unchanged, operation = integration.admit_and_reserve_integration(
        lease,
        acting_principal_ref="control:release",
        now=issued + timedelta(minutes=5),
        repository=replace(repository, current_head_sha="C2"),
        evidence=evidence,
        operation_ref="op:stale",
    )
    assert admission.disposition is integration.IntegrationAdmissionDisposition.STALE_CANDIDATE
    assert unchanged.state is integration.IntegrationLeaseState.ACTIVE
    assert operation is None

    compatible = replace(lease, base_policy=integration.BasePolicy.COMPATIBLE_ADVANCE)
    assert _admit(
        integration,
        compatible,
        evidence,
        replace(repository, current_base_sha="B2", base_advance_compatible=True),
        issued,
    ).disposition is integration.IntegrationAdmissionDisposition.BASE_ADVANCED_COMPATIBLE
    assert _admit(
        integration,
        lease,
        replace(evidence, verification_current=False),
        repository,
        issued,
    ).disposition is integration.IntegrationAdmissionDisposition.EVIDENCE_STALE
    assert _admit(
        integration,
        lease,
        replace(evidence, review_ref=None),
        repository,
        issued,
    ).disposition is integration.IntegrationAdmissionDisposition.EVIDENCE_STALE
    assert _admit(
        integration,
        lease,
        evidence,
        replace(repository, provider_allows_integration=None),
        issued,
    ).disposition is integration.IntegrationAdmissionDisposition.PROVIDER_BLOCKED


def test_timeout_requires_reconciliation_and_consumed_lease_cannot_replay() -> None:
    integration = _load("integration_lease_timeout")
    lease, evidence, repository, issued = _fixture(integration)
    admission, used, operation = _reserve(
        integration, lease, evidence, repository, issued
    )
    assert admission.operation_may_dispatch
    assert operation is not None
    assert not _admit(integration, used, evidence, repository, issued).operation_may_dispatch

    operation = integration.note_dispatch(
        operation,
        integration.DispatchObservation.DELIVERY_UNKNOWN,
    )
    assert operation.state is integration.IntegrationOperationState.RECONCILIATION_REQUIRED
    with pytest.raises(ValueError):
        integration.note_dispatch(operation, integration.DispatchObservation.ACKNOWLEDGED)

    operation, result = integration.reconcile_integration(
        operation,
        integration.IntegrationObservation(
            change_ref="change:10",
            observed_candidate_sha="C1",
            target_ref="refs/heads/main",
            target_before_sha="B1",
            target_after_sha=None,
            integrated=None,
            integrated_sha=None,
        ),
        lineage_proof_ref=None,
    )
    assert operation.state is integration.IntegrationOperationState.RECONCILIATION_REQUIRED
    assert result is None


def test_used_revoked_expired_or_stale_evidence_cannot_dispatch() -> None:
    integration = _load("integration_lease_lifecycle")
    lease, evidence, repository, issued = _fixture(integration)
    used = replace(
        lease,
        state=integration.IntegrationLeaseState.USED,
        consumed_by_operation_ref="op:used",
    )
    assert not _admit(integration, used, evidence, repository, issued).operation_may_dispatch
    for state in (
        integration.IntegrationLeaseState.REVOKED,
        integration.IntegrationLeaseState.EXPIRED,
    ):
        inactive = replace(lease, state=state)
        assert not _admit(integration, inactive, evidence, repository, issued).operation_may_dispatch

    late = integration.admit_integration(
        lease,
        acting_principal_ref="control:release",
        now=lease.expires_at,
        repository=repository,
        evidence=evidence,
    )
    assert late.disposition is integration.IntegrationAdmissionDisposition.LEASE_EXPIRED
    stale = replace(evidence, evidence_set_digest="sha256:other")
    assert _admit(
        integration,
        lease,
        stale,
        repository,
        issued,
    ).disposition is integration.IntegrationAdmissionDisposition.EVIDENCE_STALE


def test_reconciliation_requires_exact_candidate_and_strategy_lineage_proof() -> None:
    integration = _load("integration_lease_observation")
    lease, evidence, repository, issued = _fixture(integration)
    admission, used, operation = _reserve(
        integration, lease, evidence, repository, issued
    )
    assert admission.operation_may_dispatch
    assert operation is not None
    assert used.consumed_by_operation_ref == "op:1"
    operation = integration.note_dispatch(
        operation,
        integration.DispatchObservation.ACKNOWLEDGED,
    )

    mismatched = integration.IntegrationObservation(
        change_ref="change:10",
        observed_candidate_sha="C2",
        target_ref="refs/heads/main",
        target_before_sha="B1",
        target_after_sha="I1",
        integrated=True,
        integrated_sha="I1",
    )
    operation, result = integration.reconcile_integration(
        operation,
        mismatched,
        lineage_proof_ref="proof:bad",
    )
    assert operation.state is integration.IntegrationOperationState.RECONCILIATION_REQUIRED
    assert result is None


def test_reference_is_provider_neutral_and_credential_free() -> None:
    reference = REFERENCE.read_text(encoding="utf-8")
    assert "Generic repository write/push access is not integration authority." in reference
    assert "Consumers must not assume `C == I`." in reference
    assert "must not be retroactively represented as lease-authorized" in reference
    assert "GitHub pull requests" in reference
    assert "cannot supply authority principal" in reference

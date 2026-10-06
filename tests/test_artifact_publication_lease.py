from __future__ import annotations

import dataclasses
import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills/ci-cd-architect/tools/artifact_publication_lease.py"


def load():
    spec = importlib.util.spec_from_file_location("artifact_publication_lease", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fixture(module, *, tags=("stable",), version="1.2.3", digest="sha256:" + "a" * 64):
    now = datetime(2026, 10, 6, 8, 0, tzinfo=UTC)
    artifact = module.PublicationArtifact(
        "build://release/package",
        digest,
        "application/octet-stream",
        "quarantine://release/package",
    )
    destination = module.PublicationDestination(
        "registry.example",
        "team",
        "package",
        version,
        tags,
    )
    lease = module.ArtifactPublicationLease(
        "lease-1",
        "publisher/operator",
        artifact,
        destination,
        module.PublicationAction.PUBLISH_PACKAGE,
        "publication-policy-v4",
        "sha256:" + "e" * 64,
        "generation-7",
        now,
        now + timedelta(minutes=10),
    )
    authority = module.PublicationLeaseAuthorityRecord(
        "authority://publication/lease-1",
        "attestation://lease-1",
        lease,
    )
    evidence = module.PublicationEvidenceSnapshot(
        artifact.artifact_ref,
        artifact.artifact_digest,
        True,
        lease.required_evidence_set_digest,
        ("evidence://build", "evidence://tests"),
    )
    state = module.PublicationDestinationState(
        destination,
        True,
        None,
        None,
        tuple((channel, None) for channel in destination.tags_or_channels),
        True,
        True,
        lease.policy_revision,
        lease.execution_generation,
    )
    return now, artifact, destination, lease, authority, evidence, state


def verify(record):
    return record.source_ref.startswith("authority://") and bool(record.attestation_ref)


def test_producer_or_generic_credentials_do_not_mint_publication_authority():
    m = load()
    now, _, _, _, authority, evidence, state = fixture(m)

    untrusted = dataclasses.replace(authority, source_ref="candidate://self-declared")
    admission = m.admit_publication(
        untrusted,
        verify_authority_record=verify,
        acting_principal_ref="publisher/operator",
        now=now,
        evidence=evidence,
        destination_state=state,
    )
    assert admission.disposition is m.PublicationAdmissionDisposition.LOST_AUTHORITY
    assert not admission.operation_may_dispatch

    admission = m.admit_publication(
        authority,
        verify_authority_record=verify,
        acting_principal_ref="build-worker-with-registry-creds",
        now=now,
        evidence=evidence,
        destination_state=state,
    )
    assert admission.disposition is m.PublicationAdmissionDisposition.LOST_AUTHORITY


def test_exact_artifact_and_destination_scope_cannot_be_widened_or_rebuilt():
    m = load()
    now, _, destination, _, authority, evidence, state = fixture(m)

    rebuilt = dataclasses.replace(evidence, artifact_digest="sha256:" + "b" * 64)
    admission = m.admit_publication(
        authority,
        verify_authority_record=verify,
        acting_principal_ref="publisher/operator",
        now=now,
        evidence=rebuilt,
        destination_state=state,
    )
    assert admission.disposition is m.PublicationAdmissionDisposition.ARTIFACT_MISMATCH

    widened = dataclasses.replace(destination, version="1.2.4")
    widened_state = dataclasses.replace(state, destination=widened)
    admission = m.admit_publication(
        authority,
        verify_authority_record=verify,
        acting_principal_ref="publisher/operator",
        now=now,
        evidence=evidence,
        destination_state=widened_state,
    )
    assert admission.disposition is m.PublicationAdmissionDisposition.SCOPE_MISMATCH

    widened_tags = dataclasses.replace(destination, tags_or_channels=("latest", "stable"))
    widened_state = dataclasses.replace(state, destination=widened_tags)
    admission = m.admit_publication(
        authority,
        verify_authority_record=verify,
        acting_principal_ref="publisher/operator",
        now=now,
        evidence=evidence,
        destination_state=widened_state,
    )
    assert admission.disposition is m.PublicationAdmissionDisposition.SCOPE_MISMATCH


def test_same_artifact_converges_without_dispatch_but_different_artifact_conflicts():
    m = load()
    now, artifact, _, _, authority, evidence, state = fixture(m)
    same_state = dataclasses.replace(
        state,
        existing_artifact_digest=artifact.artifact_digest,
        existing_provider_artifact_id="pkg-id-123",
        channel_digests=(("stable", artifact.artifact_digest),),
        provider_allows_publication=False,
    )
    admission, consumed, operation = m.admit_and_reserve_publication(
        authority,
        verify_authority_record=verify,
        acting_principal_ref="publisher/operator",
        now=now,
        evidence=evidence,
        destination_state=same_state,
        operation_ref="publication-op-1",
    )
    assert admission.disposition is m.PublicationAdmissionDisposition.ALREADY_PRESENT_SAME_ARTIFACT
    assert admission.may_complete_without_dispatch
    assert consumed.state is m.PublicationLeaseState.USED
    assert operation is not None
    with pytest.raises(ValueError):
        m.note_dispatch(operation, m.DispatchObservation.ACKNOWLEDGED)

    observation = m.PublicationDestinationObservation(
        same_state.destination,
        True,
        artifact.artifact_digest,
        "pkg-id-123",
        same_state.channel_digests,
        True,
    )
    settled, receipt = m.reconcile_publication(operation, observation, observed_at=now)
    assert settled.state is m.PublicationOperationState.PUBLISHED
    assert receipt is not None
    assert receipt.outcome is m.PublicationOutcome.RECONCILED_ALREADY_PRESENT

    different = dataclasses.replace(
        state,
        existing_artifact_digest="sha256:" + "c" * 64,
        channel_digests=(("stable", "sha256:" + "c" * 64),),
    )
    admission = m.admit_publication(
        authority,
        verify_authority_record=verify,
        acting_principal_ref="publisher/operator",
        now=now,
        evidence=evidence,
        destination_state=different,
    )
    assert admission.disposition is m.PublicationAdmissionDisposition.ALREADY_PRESENT_DIFFERENT_ARTIFACT
    assert not admission.operation_may_dispatch


@pytest.mark.parametrize("dispatch_observation", [
    "REJECTED_OR_CONFLICT",
    "DELIVERY_UNKNOWN",
])
def test_ambiguous_or_conflict_dispatch_requires_authoritative_readback(dispatch_observation):
    m = load()
    now, artifact, _, _, authority, evidence, state = fixture(m)
    admission, consumed, operation = m.admit_and_reserve_publication(
        authority,
        verify_authority_record=verify,
        acting_principal_ref="publisher/operator",
        now=now,
        evidence=evidence,
        destination_state=state,
        operation_ref="publication-op-2",
    )
    assert admission.operation_may_dispatch
    assert consumed.state is m.PublicationLeaseState.USED
    assert operation is not None

    operation = m.note_dispatch(operation, m.DispatchObservation[dispatch_observation])
    assert operation.state is m.PublicationOperationState.RECONCILIATION_REQUIRED
    with pytest.raises(ValueError):
        m.note_dispatch(operation, m.DispatchObservation.ACKNOWLEDGED)

    observed = m.PublicationDestinationObservation(
        state.destination,
        True,
        artifact.artifact_digest,
        "registry-object-9",
        (("stable", artifact.artifact_digest),),
        True,
    )
    settled, receipt = m.reconcile_publication(operation, observed, observed_at=now)
    assert settled.state is m.PublicationOperationState.PUBLISHED
    assert receipt is not None
    assert receipt.artifact_digest == artifact.artifact_digest


def test_absent_after_ambiguous_dispatch_is_terminal_for_consumed_lease_not_blind_retry():
    m = load()
    now, _, _, _, authority, evidence, state = fixture(m)
    _, consumed, operation = m.admit_and_reserve_publication(
        authority,
        verify_authority_record=verify,
        acting_principal_ref="publisher/operator",
        now=now,
        evidence=evidence,
        destination_state=state,
        operation_ref="publication-op-3",
    )
    assert operation is not None
    operation = m.note_dispatch(operation, m.DispatchObservation.DELIVERY_UNKNOWN)
    observed = m.PublicationDestinationObservation(
        state.destination,
        True,
        None,
        None,
        (("stable", None),),
        True,
    )
    settled, receipt = m.reconcile_publication(operation, observed, observed_at=now)
    assert settled.state is m.PublicationOperationState.NOT_PUBLISHED
    assert receipt is None
    assert consumed.state is m.PublicationLeaseState.USED

    stale_authority = dataclasses.replace(authority, lease=consumed)
    admission = m.admit_publication(
        stale_authority,
        verify_authority_record=verify,
        acting_principal_ref="publisher/operator",
        now=now,
        evidence=evidence,
        destination_state=state,
    )
    assert admission.disposition is m.PublicationAdmissionDisposition.LEASE_NOT_ACTIVE


def test_mutable_channel_movement_records_before_and_after_exact_artifact_identity():
    m = load()
    now, artifact, destination, lease, authority, evidence, state = fixture(m, tags=("stable",))
    old = "sha256:" + "d" * 64
    state = dataclasses.replace(
        state,
        existing_artifact_digest=artifact.artifact_digest,
        existing_provider_artifact_id="image@sha256:a",
        channel_digests=(("stable", old),),
    )
    admission, _, operation = m.admit_and_reserve_publication(
        authority,
        verify_authority_record=verify,
        acting_principal_ref="publisher/operator",
        now=now,
        evidence=evidence,
        destination_state=state,
        operation_ref="publication-op-4",
    )
    assert admission.disposition is m.PublicationAdmissionDisposition.AVAILABLE
    assert operation is not None
    operation = m.note_dispatch(operation, m.DispatchObservation.ACKNOWLEDGED)
    observation = m.PublicationDestinationObservation(
        destination,
        True,
        artifact.artifact_digest,
        "image@sha256:a",
        (("stable", artifact.artifact_digest),),
        True,
    )
    settled, receipt = m.reconcile_publication(operation, observation, observed_at=now)
    assert settled.state is m.PublicationOperationState.PUBLISHED
    assert receipt is not None
    assert receipt.channel_before_digests == (("stable", old),)
    assert receipt.channel_after_digests == (("stable", artifact.artifact_digest),)
    assert lease.destination.tags_or_channels == ("stable",)


def test_receipt_composes_with_artifact_accepted_and_deployment_without_authority_transfer():
    m = load()
    now, artifact, destination, _, authority, evidence, state = fixture(m, tags=())
    admission, _, operation = m.admit_and_reserve_publication(
        authority,
        verify_authority_record=verify,
        acting_principal_ref="publisher/operator",
        now=now,
        evidence=evidence,
        destination_state=state,
        operation_ref="publication-op-5",
    )
    assert admission.operation_may_dispatch and operation is not None
    operation = m.note_dispatch(operation, m.DispatchObservation.ACKNOWLEDGED)
    observation = m.PublicationDestinationObservation(
        destination,
        True,
        artifact.artifact_digest,
        "provider-package-id",
        (),
        True,
    )
    _, receipt = m.reconcile_publication(operation, observation, observed_at=now)
    assert receipt is not None
    assert receipt.receipt_kind == "artifact_publication"
    assert m.satisfies_artifact_accepted(
        receipt,
        artifact_digest=artifact.artifact_digest,
        destination=destination,
    )
    deployment_ref = m.deployment_artifact_reference(receipt)
    assert deployment_ref.artifact_digest == artifact.artifact_digest
    assert not hasattr(deployment_ref, "lease_ref")
    assert not hasattr(deployment_ref, "authority_principal_ref")
    assert not hasattr(deployment_ref, "policy_revision")


@pytest.mark.parametrize(
    ("provider", "namespace", "package", "version", "action"),    [
        ("pypi", "org", "lib", "1.2.3", "PUBLISH_PACKAGE"),
        ("oci", "registry.example/org", "service", None, "PROMOTE_DIGEST"),
        ("github-release", "owner/repo", "asset.tar.gz", "v1.2.3", "PUBLISH_RELEASE_ASSET"),
    ],
)
def test_contract_is_provider_neutral(provider, namespace, package, version, action):
    m = load()
    now = datetime(2026, 10, 6, 8, 0, tzinfo=UTC)
    artifact = m.PublicationArtifact("artifact://1", "sha256:" + "f" * 64)
    destination = m.PublicationDestination(provider, namespace, package, version)
    lease = m.ArtifactPublicationLease(
        "lease-provider-neutral",
        "publisher",
        artifact,
        destination,
        m.PublicationAction[action],
        "policy",
        "sha256:" + "e" * 64,
        "generation",
        now,
        now + timedelta(minutes=1),
    )
    assert lease.destination.provider_or_registry == provider
    assert lease.action is m.PublicationAction[action]


def test_revoked_expired_policy_stale_unknown_destination_and_incomplete_channels_fail_closed():
    m = load()
    now, _, _, lease, authority, evidence, state = fixture(m)

    revoked = dataclasses.replace(lease, state=m.PublicationLeaseState.REVOKED)
    admission = m.admit_publication(
        dataclasses.replace(authority, lease=revoked),
        verify_authority_record=verify,
        acting_principal_ref="publisher/operator",
        now=now,
        evidence=evidence,
        destination_state=state,
    )
    assert admission.disposition is m.PublicationAdmissionDisposition.LEASE_NOT_ACTIVE

    admission = m.admit_publication(
        authority,
        verify_authority_record=verify,
        acting_principal_ref="publisher/operator",
        now=lease.expires_at,
        evidence=evidence,
        destination_state=state,
    )
    assert admission.disposition is m.PublicationAdmissionDisposition.LEASE_EXPIRED

    stale_policy = dataclasses.replace(state, current_policy_revision="policy-v5")
    admission = m.admit_publication(
        authority,
        verify_authority_record=verify,
        acting_principal_ref="publisher/operator",
        now=now,
        evidence=evidence,
        destination_state=stale_policy,
    )
    assert admission.disposition is m.PublicationAdmissionDisposition.POLICY_STALE

    unknown = dataclasses.replace(state, observable=None)
    admission = m.admit_publication(
        authority,
        verify_authority_record=verify,
        acting_principal_ref="publisher/operator",
        now=now,
        evidence=evidence,
        destination_state=unknown,
    )
    assert admission.disposition is m.PublicationAdmissionDisposition.DESTINATION_UNKNOWN

    incomplete = dataclasses.replace(state, channels_observed_complete=False)
    admission = m.admit_publication(
        authority,
        verify_authority_record=verify,
        acting_principal_ref="publisher/operator",
        now=now,
        evidence=evidence,
        destination_state=incomplete,
    )
    assert admission.disposition is m.PublicationAdmissionDisposition.DESTINATION_UNKNOWN

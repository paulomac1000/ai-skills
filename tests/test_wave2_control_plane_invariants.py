"""Wave 2 regressions for canonical authority, projection outbox, and retarget identity."""

from __future__ import annotations

import fnmatch
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import yaml

ROOT = Path(__file__).resolve().parents[1]
ARCHITECT = ROOT / "skills/mcp-server-architect"
TOOL = ARCHITECT / "tools/control_plane_invariants.py"
STANDARD = ARCHITECT / "STANDARD.md"
MANIFEST = ARCHITECT / "manifest.yaml"
QUALITY_TARGETS = ROOT / "scripts/quality_targets.py"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _covered(targets: tuple[str, ...], path: str) -> bool:
    return any(
        path == target or path.startswith(f"{target.rstrip('/')}/") or ("*" in target and fnmatch.fnmatch(path, target))
        for target in targets
    )


def test_outbox_ambiguity_requires_authoritative_reconciliation() -> None:
    control = _load("wave2_control_plane_outbox", TOOL)
    pending = control.ProjectionOutboxEntry("entity-7", "projection-gen-4", "idem-9")
    ambiguous = control.mark_projection_ambiguous(pending)

    assert ambiguous.state.value == "RECONCILE_REQUIRED"
    assert control.reconcile_projection_delivery(ambiguous, None) is ambiguous
    assert control.reconcile_projection_delivery(ambiguous, True).state.value == "CONFIRMED"
    assert control.reconcile_projection_delivery(ambiguous, False).state.value == "DISPROVEN"


def test_retarget_preserves_canonical_identity_and_audits_transition() -> None:
    control = _load("wave2_control_plane_retarget", TOOL)
    original = control.CanonicalEntity("entity-7", "canonical-store", "board-a/item-3")
    moved = control.retarget_projection(original, "board-b/item-8", reason="provider transfer")

    assert moved.canonical_id == original.canonical_id
    assert moved.owner == original.owner
    assert moved.projection_target == "board-b/item-8"
    assert moved.transition_history[-1].startswith("retarget:board-a/item-3->board-b/item-8:")


def test_provider_scoped_external_identity_separates_github_local_numbers_and_markers() -> None:
    control = _load("wave2_control_plane_external_identity", TOOL)
    repo_a = control.ProviderScopedExternalIdentity(
        "github", "issue", "42", ("installation-7", "owner", "repo-a")
    )
    repo_b = control.ProviderScopedExternalIdentity(
        "github", "issue", "42", ("installation-7", "owner", "repo-b")
    )
    assert repo_a.binding_key != repo_b.binding_key

    try:
        control.ProviderScopedExternalIdentity("github", "issue", "42")
    except ValueError as exc:
        assert "complete provider namespace" in str(exc)
    else:
        raise AssertionError("bare provider-local issue number must fail closed")

    binding_a = control.ExternalBinding("entity-a", repo_a, recovery_locator="managed:entity-7")
    binding_b = control.ExternalBinding("entity-b", repo_b, recovery_locator="managed:entity-7")
    assert not control.binding_matches_external(binding_a, repo_b)
    assert binding_a.canonical_id != binding_b.canonical_id


def test_event_ingress_deduplicates_and_reconciles_authoritative_state() -> None:
    control = _load("wave2_control_plane_event_ingress", TOOL)
    identity = control.ProviderScopedExternalIdentity(
        "github", "issue", "42", ("installation-7", "owner", "repo-a")
    )
    first = control.EventIngressReceipt(
        "github", "delivery-1", "issues", identity, "2026-10-05T17:00:00Z", ("installation-7",)
    )
    recorded, is_new = control.admit_event_receipt(None, first)
    assert is_new

    other_source = control.EventIngressReceipt(
        "github", "delivery-1", "issues", identity, "2026-10-05T17:00:30Z", ("installation-8",)
    )
    assert other_source.dedup_key != first.dedup_key

    try:
        control.EventIngressReceipt(
            "github", "delivery-without-scope", "issues", identity, "2026-10-05T17:00:45Z"
        )
    except ValueError as exc:
        assert "requires source scope" in str(exc)
    else:
        raise AssertionError("bare delivery ID must not self-declare global uniqueness")

    retry = control.EventIngressReceipt(
        "github", "delivery-1", "issues", identity, "2026-10-05T17:01:00Z", ("installation-7",)
    )
    same, is_new = control.admit_event_receipt(recorded, retry)
    assert same is recorded
    assert not is_new

    changed_subject = control.EventIngressReceipt(
        "github",
        "delivery-1",
        "issue_comment",
        identity,
        "2026-10-05T17:01:30Z",
        ("installation-7",),
    )
    try:
        control.admit_event_receipt(recorded, changed_subject)
    except ValueError as exc:
        assert "changed event subject" in str(exc)
    else:
        raise AssertionError("one delivery identity cannot be rebound to another semantic subject")

    latest = control.begin_event_reconciliation(recorded)
    applied = control.settle_event_reconciliation(
        latest,
        canonical_id="entity-a",
        authoritative_state_revision="etag-9",
        policy_authorized=True,
        expected_resource_generation="gen-4",
        current_resource_generation="gen-4",
        semantic_change=True,
    )
    assert applied.state.value == "APPLIED"

    older = control.EventIngressReceipt(
        "github", "delivery-0", "issues", identity, "2026-10-05T16:00:00Z", ("installation-7",)
    )
    older = control.begin_event_reconciliation(older)
    no_change = control.settle_event_reconciliation(
        older,
        canonical_id="entity-a",
        authoritative_state_revision="etag-9",
        policy_authorized=True,
        expected_resource_generation="gen-5",
        current_resource_generation="gen-5",
        semantic_change=False,
    )
    assert no_change.state.value == "NO_CHANGE"
    assert no_change.authoritative_state_revision == "etag-9"


def test_event_ingress_fence_authority_and_restart_fail_closed() -> None:
    control = _load("wave2_control_plane_event_fence", TOOL)
    identity = control.ProviderScopedExternalIdentity(
        "github", "issue", "42", ("installation-7", "owner", "repo-a")
    )
    received = control.EventIngressReceipt(
        "github", "delivery-2", "issues", identity, "2026-10-05T17:02:00Z", ("installation-7",)
    )
    queued = control.begin_event_reconciliation(received)

    stale = control.settle_event_reconciliation(
        queued,
        canonical_id="entity-a",
        authoritative_state_revision="etag-10",
        policy_authorized=True,
        expected_resource_generation="gen-5",
        current_resource_generation="gen-6",
        semantic_change=True,
    )
    assert stale.state.value == "RECONCILE_REQUIRED"

    try:
        control.settle_event_reconciliation(
            queued,
            canonical_id="entity-a",
            authoritative_state_revision="etag-10",
            policy_authorized=False,
            expected_resource_generation="gen-6",
            current_resource_generation="gen-6",
            semantic_change=True,
        )
    except ValueError as exc:
        assert "does not grant canonical transition authority" in str(exc)
    else:
        raise AssertionError("event delivery must not self-authorize")

    reloaded = control.EventIngressReceipt(
        received.provider,
        received.delivery_id,
        received.event_kind,
        received.external_identity,
        received.received_at,
        received.source_scope,
        state=control.EventIngressState.RECONCILE_REQUIRED,
    )
    assert control.begin_event_reconciliation(reloaded) is reloaded


def test_external_rebind_preserves_canonical_identity() -> None:
    control = _load("wave2_control_plane_external_rebind", TOOL)
    before = control.ProviderScopedExternalIdentity(
        "github", "issue", "42", ("installation-7", "owner", "repo-a")
    )
    after = control.ProviderScopedExternalIdentity(
        "github", "issue", "42", ("installation-7", "owner", "repo-b")
    )
    binding = control.ExternalBinding("entity-a", before, recovery_locator="managed:entity-a")
    moved = control.rebind_external_resource(binding, after, reason="repository transfer")

    assert moved.canonical_id == binding.canonical_id
    assert moved.external_identity == after
    assert moved.transition_history[-1].startswith("rebind:")


def test_standard_covers_complete_canonical_projection_pattern_bundle() -> None:
    text = STANDARD.read_text(encoding="utf-8")
    for phrase in (
        "one canonical store/authority",
        "Ingress records both observation context and affected canonical owner",
        "durable idempotent outbox",
        "Raw provider adapters refuse mutation",
        "preserves canonical entity identity/history",
        "completed externally or by an operator",
        "bounded actionable brief/status",
        "complete provider namespace",
        "External events are authenticated reconciliation triggers",
        "owner/repository/issues/42",
    ):
        assert phrase in text


def test_control_plane_tool_is_required_and_in_all_quality_inventories() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert "tools/control_plane_invariants.py" in manifest["required"]
    inventories = _load("wave2_quality_targets_control_plane", QUALITY_TARGETS)
    path = "skills/mcp-server-architect/tools/control_plane_invariants.py"
    for targets in (
        inventories.QUALITY_PATHS,
        inventories.TYPE_PATHS,
        inventories.BANDIT_PATHS,
        inventories.POLICY_COVERAGE_PATHS,
    ):
        assert _covered(targets, path)

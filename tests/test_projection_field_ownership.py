"""Regressions for field-level projection ownership and external automation."""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
ARCHITECT = ROOT / "skills/mcp-server-architect"
TOOL = ARCHITECT / "tools/control_plane_invariants.py"
STANDARD = ARCHITECT / "STANDARD.md"
REFERENCE = ARCHITECT / "references/projection-field-ownership.md"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _policy(control: ModuleType):
    return control.ProjectionFieldPolicy(
        "projection-field-ownership/v1",
        (
            control.ProjectionFieldRule(
                "lifecycle_state", control.ProjectionFieldOwnership.CANONICAL_OWNED, "canonical", "reconcile"
            ),
            control.ProjectionFieldRule(
                "canonical_priority", control.ProjectionFieldOwnership.CANONICAL_OWNED, "canonical", "reconcile"
            ),
            control.ProjectionFieldRule(
                "advisory_labels", control.ProjectionFieldOwnership.EXTERNAL_ADVISORY, "advisory", "preserve"
            ),
            control.ProjectionFieldRule(
                "human_assignee", control.ProjectionFieldOwnership.EXTERNAL_ADVISORY, "advisory", "preserve"
            ),
            control.ProjectionFieldRule(
                "description",
                control.ProjectionFieldOwnership.SHARED_MANAGED_REGIONS,
                "split",
                "preserve_external_regions",
                managed_regions=("managed_status",),
            ),
            control.ProjectionFieldRule(
                "agent_assignee",
                control.ProjectionFieldOwnership.EXTERNAL_EXECUTION,
                "none",
                "prohibit_or_reconcile",
                side_effect_class="starts_work",
            ),
        ),
    )


def test_advisory_metadata_and_fake_priority_do_not_gain_authority() -> None:
    control = _load("projection_field_advisory")
    policy = _policy(control)
    triage = control.ExternalAutomationCapability(
        "triage",
        (
            control.ExternalAutomationGrant("advisory_labels", ("set", "suggest")),
            control.ExternalAutomationGrant("human_assignee", ("set",)),
        ),
    )

    assert control.admit_external_automation(policy, triage, field="advisory_labels", action="set")
    assert not control.admit_external_automation(policy, triage, field="canonical_priority", action="set")
    assert control.classify_projection_change(policy, "advisory_labels") is control.ProjectionDriftKind.ADVISORY_METADATA_CHANGE
    assert control.classify_projection_change(policy, "canonical_priority") is control.ProjectionDriftKind.CANONICAL_FIELD_DRIFT
    assert control.classify_projection_change(policy, "human_assignee") is control.ProjectionDriftKind.ADVISORY_METADATA_CHANGE


def test_confidence_is_bounded_evidence_not_automation_authority() -> None:
    control = _load("projection_field_confidence")
    policy = _policy(control)
    triage = control.ExternalAutomationCapability(
        "triage", (control.ExternalAutomationGrant("advisory_labels", ("set",)),)
    )
    evidence = control.ProjectionAuditEvidence(
        "github-agent",
        "canonical_priority",
        policy.revision,
        "reconcile",
        provider_confidence="high",
        provider_rationale="provider auto-approved this suggestion",
    )

    assert evidence.provider_confidence == "high"
    assert "provider_confidence" not in inspect.signature(control.admit_external_automation).parameters
    assert not control.admit_external_automation(policy, triage, field="canonical_priority", action="set")
    with pytest.raises(ValueError, match="bounded"):
        control.ProjectionAuditEvidence(
            "github-agent",
            "canonical_priority",
            policy.revision,
            "reconcile",
            provider_rationale="x" * 257,
        )


def test_agent_assignment_is_external_execution_and_blocks_parallel_claim() -> None:
    control = _load("projection_field_execution")
    policy = _policy(control)
    triage = control.ExternalAutomationCapability(
        "triage", (control.ExternalAutomationGrant("advisory_labels", ("set",)),)
    )
    assert control.classify_projection_change(policy, "agent_assignee") is control.ProjectionDriftKind.EXTERNAL_EXECUTION_CONFLICT
    assert not control.admit_external_automation(policy, triage, field="agent_assignee", action="assign")

    with pytest.raises(ValueError, match="execution boundary"):
        control.ExternalAutomationCapability(
            "executor",
            (control.ExternalAutomationGrant("agent_assignee", ("assign",)),),
            ("starts_work",),
        )

    executor = control.ExternalAutomationCapability(
        "executor",
        (control.ExternalAutomationGrant("agent_assignee", ("assign",)),),
        ("starts_work",),
        control.ExecutionBoundaryIdentity("github-copilot-agent", "provider-cloud-prod"),
    )
    assert control.admit_external_automation(policy, executor, field="agent_assignee", action="assign")
    for state in (
        control.ExternalWorkState.OBSERVED_UNRECONCILED,
        control.ExternalWorkState.ACTIVE_ADOPTED,
        control.ExternalWorkState.BLOCKED_PENDING_REVERT,
    ):
        assert not control.canonical_scheduler_may_claim(state)
    assert control.canonical_scheduler_may_claim(control.ExternalWorkState.NONE)
    assert control.canonical_scheduler_may_claim(control.ExternalWorkState.TERMINAL_RECONCILED)


def test_capabilities_are_field_action_scoped_without_cross_product() -> None:
    control = _load("projection_field_capabilities")
    policy = _policy(control)
    triage = control.ExternalAutomationCapability(
        "triage",
        (
            control.ExternalAutomationGrant("advisory_labels", ("set", "suggest")),
            control.ExternalAutomationGrant("human_assignee", ("set",)),
        ),
    )
    assert control.admit_external_automation(policy, triage, field="advisory_labels", action="suggest")
    assert not control.admit_external_automation(policy, triage, field="human_assignee", action="suggest")
    assert not control.admit_external_automation(policy, triage, field="lifecycle_state", action="set")


def test_shared_regions_preserve_external_enrichment_and_unknown_fields_fail_conservative() -> None:
    control = _load("projection_field_shared")
    policy = _policy(control)
    rule = policy.rule_for("description")

    merged = control.reconcile_shared_regions(
        rule,
        canonical_regions={"managed_status": "ready"},
        external_regions={"managed_status": "old", "human_notes": "keep me"},
    )
    assert merged == {"managed_status": "ready", "human_notes": "keep me"}
    assert control.classify_projection_change(policy, "description", managed_region_touched=False) is control.ProjectionDriftKind.ADVISORY_METADATA_CHANGE
    assert control.classify_projection_change(policy, "description", managed_region_touched=True) is control.ProjectionDriftKind.SHARED_REGION_CONFLICT
    assert control.classify_projection_change(policy, "provider_new_field") is control.ProjectionDriftKind.UNKNOWN_FIELD_POLICY

    shared_editor = control.ExternalAutomationCapability(
        "shared-editor",
        (control.ExternalAutomationGrant("description", ("annotate",), ("human_notes",)),),
    )
    assert control.admit_external_automation(
        policy, shared_editor, field="description", action="annotate", region="human_notes"
    )
    assert not control.admit_external_automation(
        policy, shared_editor, field="description", action="annotate", region="managed_status"
    )
    assert not control.admit_external_automation(policy, shared_editor, field="description", action="annotate")

    triage = control.ExternalAutomationCapability(
        "triage", (control.ExternalAutomationGrant("advisory_labels", ("set",)),)
    )
    assert not control.admit_external_automation(policy, triage, field="provider_new_field", action="set")
    with pytest.raises(ValueError, match="undeclared"):
        control.reconcile_shared_regions(
            rule,
            canonical_regions={"human_notes": "overwrite"},
            external_regions={"human_notes": "keep"},
        )


def test_standard_routes_provider_neutral_field_ownership_contract() -> None:
    standard = " ".join(STANDARD.read_text(encoding="utf-8").split())
    reference = REFERENCE.read_text(encoding="utf-8")

    assert "field/namespace ownership policy" in standard
    assert "provider confidence/rationale is evidence, never authorization" in standard
    assert "project-steward-mcp#123" in reference
    assert "opencode-stack-guides#195" in reference
    for provider in ("GitHub", "Jira", "Linear", "Trello", "ServiceNow"):
        assert provider in reference

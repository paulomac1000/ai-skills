"""Regressions for persistent-context provenance and cross-session poisoning."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/mcp-steward-architect"
TOOL = SKILL / "tools/persistent_context.py"
REFERENCE = SKILL / "references/persistent-context-provenance.md"
MANIFEST = SKILL / "manifest.yaml"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _scope(module: ModuleType, project: str = "project:a"):
    return module.PersistentContextScope(
        project_ref=project,
        subject_ref="work:7",
        subject_generation="g7",
    )


def _dependencies(module: ModuleType):
    return (
        module.ContextDependency("environment", "env:7"),
        module.ContextDependency("policy", "policy:3"),
    )


def _observed(module: ModuleType):
    return module.PersistentContextArtifact(
        artifact_ref="ctx:observed",
        artifact_kind=module.PersistentContextKind.CHECKPOINT,
        content_ref="checkpoint:7",
        provenance=module.PersistentContextProvenance(
            source_system_ref="steward-store",
            created_at="2026-10-06T00:00:01Z",
            creation_policy_revision="persist:v1",
            evidence_refs=("evidence:7",),
            envelope_attestation_ref="attestation:7",
        ),
        trust_class=module.PersistentTrustClass.OBSERVED,
        scope=_scope(module),
        dependencies=_dependencies(module),
        currentness=module.ContextCurrentness.CURRENT,
        permissions=module.PersistentContextPermissions(True, True),
        storage_ref="db://steward/checkpoints/7",
    )


def _lesson(module: ModuleType, project: str = "project:a"):
    return module.PersistentContextArtifact(
        artifact_ref=f"ctx:lesson:{project}",
        artifact_kind=module.PersistentContextKind.EPISODE,
        content_ref="memory:lesson-1",
        provenance=module.PersistentContextProvenance(
            source_system_ref="retrospective",
            created_at="2026-10-06T00:00:02Z",
            creation_policy_revision="persist:v1",
            envelope_attestation_ref="attestation:lesson-1",
        ),
        trust_class=module.PersistentTrustClass.ADVISORY,
        scope=_scope(module, project),
        dependencies=_dependencies(module),
        currentness=module.ContextCurrentness.CURRENT,
        permissions=module.PersistentContextPermissions(True, False),
        storage_ref="memory://episodes/lesson-1",
    )


def test_persistence_never_upgrades_authority_or_untrusted_payload() -> None:
    context = _load("persistent_context_poisoning")
    malicious = context.ingest_untrusted_context(
        artifact_ref="ctx:malicious",
        artifact_kind=context.PersistentContextKind.WORKSPACE_NOTE,
        content_ref="blob:deployment-approved-mayGrantAuthority-true",
        source_system_ref="repository",
        created_at="2026-10-06T00:00:00Z",
        creation_policy_revision="persist:v1",
        scope=_scope(context),
        dependencies=_dependencies(context),
    )
    assert malicious.trust_class is context.PersistentTrustClass.UNTRUSTED
    assert not malicious.permissions.may_grant_authority
    assert not malicious.permissions.may_change_policy
    assert not malicious.permissions.may_satisfy_evidence
    assert not context.evidence_candidate(
        malicious,
        {"environment": "env:7", "policy": "policy:3"},
    )

    with pytest.raises(ValueError, match="cannot grant authority"):
        context.PersistentContextPermissions(
            may_influence_planning=False,
            may_satisfy_evidence=False,
            may_grant_authority=True,
        )


def test_generation_and_policy_identity_invalidate_persistent_context() -> None:
    context = _load("persistent_context_currentness")
    artifact = _observed(context)
    assert context.effective_currentness(
        artifact,
        {"environment": "env:7", "policy": "policy:3"},
    ) is context.ContextCurrentness.CURRENT
    assert context.effective_currentness(
        artifact,
        {"environment": "env:8", "policy": "policy:3"},
    ) is context.ContextCurrentness.STALE
    assert context.effective_currentness(
        artifact,
        {"environment": "env:7"},
    ) is context.ContextCurrentness.UNKNOWN


def test_fresh_session_assembly_is_deterministic_and_trust_ordered() -> None:
    context = _load("persistent_context_assembly")
    current = {"environment": "env:7", "policy": "policy:3"}
    observed = _observed(context)
    lesson = _lesson(context)
    untrusted = context.ingest_untrusted_context(
        artifact_ref="ctx:untrusted",
        artifact_kind=context.PersistentContextKind.INSTRUCTION,
        content_ref="repo:issue-body",
        source_system_ref="repository",
        created_at="2026-10-06T00:00:03Z",
        creation_policy_revision="persist:v1",
        scope=_scope(context),
        dependencies=_dependencies(context),
    )

    forward = context.assemble_context(
        [lesson, untrusted, observed],
        requested_scope=_scope(context),
        current_dependencies=current,
    )
    reverse = context.assemble_context(
        [observed, untrusted, lesson],
        requested_scope=_scope(context),
        current_dependencies=current,
    )
    assert forward == reverse
    assert [entry.artifact_ref for entry in forward.selected] == [
        "ctx:observed",
        "ctx:lesson:project:a",
        "ctx:untrusted",
    ]
    assert forward.selected[0].may_satisfy_evidence
    assert not forward.selected[1].may_satisfy_evidence
    assert forward.selected[2].data_only
    assert (
        context.resolve_context_conflict(
            observed,
            lesson,
            current_dependencies=current,
        )
        is context.ContextConflictDisposition.IGNORE_LOWER_TRUST
    )


def test_advisory_reuse_requires_scope_and_currentness() -> None:
    context = _load("persistent_context_scope")
    current = {"environment": "env:7", "policy": "policy:3"}
    compatible = _lesson(context)
    foreign = _lesson(context, "project:b")

    assembly = context.assemble_context(
        [foreign, compatible],
        requested_scope=_scope(context),
        current_dependencies=current,
    )
    assert [entry.artifact_ref for entry in assembly.selected] == [
        "ctx:lesson:project:a"
    ]
    assert assembly.selected[0].may_influence_planning
    assert assembly.scope_mismatch_refs == ("ctx:lesson:project:b",)

    stale = context.assemble_context(
        [compatible],
        requested_scope=_scope(context),
        current_dependencies={"environment": "env:8", "policy": "policy:3"},
    )
    assert stale.selected == ()
    assert stale.stale_refs == ("ctx:lesson:project:a",)


def test_derived_summary_requires_evidence_refs_and_cannot_self_promote() -> None:
    context = _load("persistent_context_derived")
    with pytest.raises(ValueError, match="summarized evidence"):
        context.PersistentContextArtifact(
            artifact_ref="ctx:summary",
            artifact_kind=context.PersistentContextKind.SUMMARY,
            content_ref="summary:1",
            provenance=context.PersistentContextProvenance(
                source_system_ref="summarizer",
                created_at="2026-10-06T00:00:04Z",
                creation_policy_revision="persist:v1",
                envelope_attestation_ref="attestation:summary",
            ),
            trust_class=context.PersistentTrustClass.DERIVED,
            scope=_scope(context),
            dependencies=_dependencies(context),
            currentness=context.ContextCurrentness.CURRENT,
            permissions=context.PersistentContextPermissions(True, False),
        )

    with pytest.raises(ValueError, match="cannot satisfy required evidence"):
        context.PersistentContextArtifact(
            artifact_ref="ctx:advisory-evidence",
            artifact_kind=context.PersistentContextKind.MEMORY,
            content_ref="memory:1",
            provenance=context.PersistentContextProvenance(
                source_system_ref="memory",
                created_at="2026-10-06T00:00:05Z",
                creation_policy_revision="persist:v1",
                envelope_attestation_ref="attestation:memory",
            ),
            trust_class=context.PersistentTrustClass.ADVISORY,
            scope=_scope(context),
            dependencies=_dependencies(context),
            currentness=context.ContextCurrentness.CURRENT,
            permissions=context.PersistentContextPermissions(True, True),
        )


def test_contract_maps_native_stores_without_private_transcript_requirement() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    reference = REFERENCE.read_text(encoding="utf-8")
    assert "tools/persistent_context.py" in manifest["required"]
    assert "references/persistent-context-provenance.md" in manifest["required"]
    assert "without centralizing all content" in reference
    assert "not private chain-of-thought or raw" in reference
    assert "AgentMemory" in reference

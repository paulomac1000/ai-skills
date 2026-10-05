"""Provider-neutral persistent-context provenance and freshness helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

_MAX_REF = 256
_MAX_REFS = 32


class PersistentContextKind(StrEnum):
    CHECKPOINT = "checkpoint"
    HANDOFF = "handoff"
    MEMORY = "memory"
    INSTRUCTION = "instruction"
    EPISODE = "episode"
    SUMMARY = "summary"
    WORKSPACE_NOTE = "workspace_note"
    OTHER = "other"


class PersistentTrustClass(StrEnum):
    AUTHORITATIVE = "AUTHORITATIVE"
    OBSERVED = "OBSERVED"
    DERIVED = "DERIVED"
    ADVISORY = "ADVISORY"
    UNTRUSTED = "UNTRUSTED"


class ContextCurrentness(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class ContextConflictDisposition(StrEnum):
    IGNORE_LOWER_TRUST = "IGNORE_LOWER_TRUST"
    REVALIDATE = "REVALIDATE"
    UNKNOWN = "UNKNOWN"


_TRUST_RANK = {
    PersistentTrustClass.AUTHORITATIVE: 4,
    PersistentTrustClass.OBSERVED: 3,
    PersistentTrustClass.DERIVED: 2,
    PersistentTrustClass.ADVISORY: 1,
    PersistentTrustClass.UNTRUSTED: 0,
}


def _require_ref(value: str, name: str) -> None:
    if not value.strip() or len(value) > _MAX_REF:
        raise ValueError(f"{name} must be non-empty and at most {_MAX_REF} characters")


def _validate_optional_ref(value: str | None, name: str) -> None:
    if value is not None:
        _require_ref(value, name)


def _validate_refs(values: tuple[str, ...], name: str) -> None:
    if len(values) > _MAX_REFS:
        raise ValueError(f"{name} must contain at most {_MAX_REFS} references")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must not contain duplicate references")
    for value in values:
        _require_ref(value, name)


@dataclass(frozen=True)
class ContextDependency:
    """Exact load-bearing identity whose change invalidates persistent context."""

    name: str
    identity: str

    def __post_init__(self) -> None:
        _require_ref(self.name, "dependency name")
        _require_ref(self.identity, "dependency identity")


@dataclass(frozen=True)
class PersistentContextScope:
    """Scope boundary for later-session reuse."""

    project_ref: str | None = None
    work_ref: str | None = None
    campaign_ref: str | None = None
    subject_ref: str | None = None
    subject_generation: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("project_ref", self.project_ref),
            ("work_ref", self.work_ref),
            ("campaign_ref", self.campaign_ref),
            ("subject_ref", self.subject_ref),
            ("subject_generation", self.subject_generation),
        ):
            _validate_optional_ref(value, name)


@dataclass(frozen=True)
class PersistentContextProvenance:
    """Trusted-envelope provenance; content cannot assign these fields to itself."""

    source_system_ref: str
    created_at: str
    creation_policy_revision: str
    source_principal_ref: str | None = None
    evidence_refs: tuple[str, ...] = ()
    envelope_attestation_ref: str | None = None

    def __post_init__(self) -> None:
        _require_ref(self.source_system_ref, "source system ref")
        _require_ref(self.created_at, "created_at")
        _require_ref(self.creation_policy_revision, "creation policy revision")
        _validate_optional_ref(self.source_principal_ref, "source principal ref")
        _validate_optional_ref(self.envelope_attestation_ref, "envelope attestation ref")
        _validate_refs(self.evidence_refs, "evidence refs")


@dataclass(frozen=True)
class PersistentContextPermissions:
    """Permitted influence. Persistent context never grants authority or changes policy."""

    may_influence_planning: bool
    may_satisfy_evidence: bool
    may_grant_authority: bool = False
    may_change_policy: bool = False

    def __post_init__(self) -> None:
        if self.may_grant_authority or self.may_change_policy:
            raise ValueError("persistent context cannot grant authority or change policy")


@dataclass(frozen=True)
class PersistentContextArtifact:
    """Bounded provenance envelope for content stored in any native persistent store."""

    artifact_ref: str
    artifact_kind: PersistentContextKind
    content_ref: str
    provenance: PersistentContextProvenance
    trust_class: PersistentTrustClass
    scope: PersistentContextScope
    dependencies: tuple[ContextDependency, ...]
    currentness: ContextCurrentness
    permissions: PersistentContextPermissions
    storage_ref: str | None = None

    def __post_init__(self) -> None:
        _require_ref(self.artifact_ref, "artifact ref")
        _require_ref(self.content_ref, "content ref")
        _validate_optional_ref(self.storage_ref, "storage ref")
        if len(self.dependencies) > _MAX_REFS:
            raise ValueError(f"dependencies must contain at most {_MAX_REFS} entries")
        names = [item.name for item in self.dependencies]
        if len(set(names)) != len(names):
            raise ValueError("dependency names must be unique")
        if (
            self.trust_class is not PersistentTrustClass.UNTRUSTED
            and self.provenance.envelope_attestation_ref is None
        ):
            raise ValueError("non-untrusted context requires trusted envelope attestation")
        if self.permissions.may_satisfy_evidence and self.trust_class not in {
            PersistentTrustClass.AUTHORITATIVE,
            PersistentTrustClass.OBSERVED,
        }:
            raise ValueError("derived/advisory/untrusted context cannot satisfy required evidence")
        if self.trust_class is PersistentTrustClass.DERIVED and not self.provenance.evidence_refs:
            raise ValueError("derived context requires provenance references to summarized evidence")


@dataclass(frozen=True)
class ContextAssemblyEntry:
    artifact_ref: str
    trust_class: PersistentTrustClass
    may_influence_planning: bool
    may_satisfy_evidence: bool
    data_only: bool


@dataclass(frozen=True)
class ContextAssembly:
    selected: tuple[ContextAssemblyEntry, ...]
    stale_refs: tuple[str, ...]
    unknown_refs: tuple[str, ...]
    scope_mismatch_refs: tuple[str, ...]


def effective_currentness(
    artifact: PersistentContextArtifact,
    current_dependencies: Mapping[str, str],
) -> ContextCurrentness:
    """Derive currentness without upgrading an explicitly stale/unknown artifact."""
    if artifact.currentness is not ContextCurrentness.CURRENT:
        return artifact.currentness
    for dependency in artifact.dependencies:
        current = current_dependencies.get(dependency.name)
        if current is None:
            return ContextCurrentness.UNKNOWN
        if current != dependency.identity:
            return ContextCurrentness.STALE
    return ContextCurrentness.CURRENT


def scope_compatible(
    artifact_scope: PersistentContextScope,
    requested_scope: PersistentContextScope,
) -> bool:
    """Require explicit equality for every requested scope dimension."""
    for name in (
        "project_ref",
        "work_ref",
        "campaign_ref",
        "subject_ref",
        "subject_generation",
    ):
        requested = getattr(requested_scope, name)
        if requested is not None and getattr(artifact_scope, name) != requested:
            return False
    return True


def evidence_candidate(
    artifact: PersistentContextArtifact,
    current_dependencies: Mapping[str, str],
) -> bool:
    """Return eligibility only; actual proof authority remains external policy."""
    return (
        artifact.permissions.may_satisfy_evidence
        and artifact.trust_class
        in {PersistentTrustClass.AUTHORITATIVE, PersistentTrustClass.OBSERVED}
        and effective_currentness(artifact, current_dependencies) is ContextCurrentness.CURRENT
    )


def assemble_context(
    artifacts: Sequence[PersistentContextArtifact],
    *,
    requested_scope: PersistentContextScope,
    current_dependencies: Mapping[str, str],
) -> ContextAssembly:
    """Assemble fresh-session context deterministically by scope, currentness, and trust."""
    selected: list[PersistentContextArtifact] = []
    stale: list[str] = []
    unknown: list[str] = []
    scope_mismatch: list[str] = []

    for artifact in artifacts:
        if not scope_compatible(artifact.scope, requested_scope):
            scope_mismatch.append(artifact.artifact_ref)
            continue
        state = effective_currentness(artifact, current_dependencies)
        if state is ContextCurrentness.STALE:
            stale.append(artifact.artifact_ref)
            continue
        if state is ContextCurrentness.UNKNOWN:
            unknown.append(artifact.artifact_ref)
            continue
        selected.append(artifact)

    selected.sort(key=lambda item: (-_TRUST_RANK[item.trust_class], item.artifact_ref))
    return ContextAssembly(
        selected=tuple(
            ContextAssemblyEntry(
                artifact_ref=item.artifact_ref,
                trust_class=item.trust_class,
                may_influence_planning=item.permissions.may_influence_planning,
                may_satisfy_evidence=evidence_candidate(item, current_dependencies),
                data_only=(
                    item.trust_class is PersistentTrustClass.UNTRUSTED
                    or not item.permissions.may_influence_planning
                ),
            )
            for item in selected
        ),
        stale_refs=tuple(sorted(stale)),
        unknown_refs=tuple(sorted(unknown)),
        scope_mismatch_refs=tuple(sorted(scope_mismatch)),
    )


def resolve_context_conflict(
    higher: PersistentContextArtifact,
    lower: PersistentContextArtifact,
    *,
    current_dependencies: Mapping[str, str],
) -> ContextConflictDisposition:
    """Prevent stale or lower-trust context from overriding a current higher-trust fact."""
    higher_state = effective_currentness(higher, current_dependencies)
    lower_state = effective_currentness(lower, current_dependencies)
    if higher_state is not ContextCurrentness.CURRENT or lower_state is not ContextCurrentness.CURRENT:
        return ContextConflictDisposition.REVALIDATE
    if _TRUST_RANK[higher.trust_class] > _TRUST_RANK[lower.trust_class]:
        return ContextConflictDisposition.IGNORE_LOWER_TRUST
    return ContextConflictDisposition.UNKNOWN


def ingest_untrusted_context(
    *,
    artifact_ref: str,
    artifact_kind: PersistentContextKind,
    content_ref: str,
    source_system_ref: str,
    created_at: str,
    creation_policy_revision: str,
    scope: PersistentContextScope,
    dependencies: tuple[ContextDependency, ...] = (),
    storage_ref: str | None = None,
) -> PersistentContextArtifact:
    """Admit model/repository/user content as data without parsing self-asserted authority."""
    return PersistentContextArtifact(
        artifact_ref=artifact_ref,
        artifact_kind=artifact_kind,
        content_ref=content_ref,
        provenance=PersistentContextProvenance(
            source_system_ref=source_system_ref,
            created_at=created_at,
            creation_policy_revision=creation_policy_revision,
        ),
        trust_class=PersistentTrustClass.UNTRUSTED,
        scope=scope,
        dependencies=dependencies,
        currentness=ContextCurrentness.CURRENT,
        permissions=PersistentContextPermissions(
            may_influence_planning=False,
            may_satisfy_evidence=False,
        ),
        storage_ref=storage_ref,
    )

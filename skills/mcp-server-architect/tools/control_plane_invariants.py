"""Pure helpers for canonical-control-plane projection and identity invariants."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum


class ProjectionDeliveryState(StrEnum):
    PENDING = "PENDING"
    RECONCILE_REQUIRED = "RECONCILE_REQUIRED"
    CONFIRMED = "CONFIRMED"
    DISPROVEN = "DISPROVEN"


class EventIngressState(StrEnum):
    RECEIVED = "RECEIVED"
    RECONCILE_REQUIRED = "RECONCILE_REQUIRED"
    APPLIED = "APPLIED"
    NO_CHANGE = "NO_CHANGE"


@dataclass(frozen=True)
class ProjectionOutboxEntry:
    canonical_id: str
    projection_generation: str
    idempotency_key: str
    state: ProjectionDeliveryState = ProjectionDeliveryState.PENDING

    def __post_init__(self) -> None:
        if not self.canonical_id.strip() or not self.projection_generation.strip() or not self.idempotency_key.strip():
            raise ValueError("outbox identity fields must be non-empty")


@dataclass(frozen=True)
class CanonicalEntity:
    canonical_id: str
    owner: str
    projection_target: str
    transition_history: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.canonical_id.strip() or not self.owner.strip() or not self.projection_target.strip():
            raise ValueError("canonical entity identity fields must be non-empty")


@dataclass(frozen=True)
class ProviderScopedExternalIdentity:
    """Provider-scoped identity; e.g. GitHub repo-a/issues/42 differs from repo-b/issues/42."""

    provider: str
    resource_kind: str
    resource_id: str
    provider_namespace: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.resource_kind.strip() or not self.resource_id.strip():
            raise ValueError("external identity fields must be non-empty")
        if any(not component.strip() for component in self.provider_namespace):
            raise ValueError("provider namespace components must be non-empty")
        if not self.provider_namespace:
            raise ValueError("external identity requires complete provider namespace")

    @property
    def binding_key(self) -> tuple[str, ...]:
        return (self.provider, *self.provider_namespace, self.resource_kind, self.resource_id)


@dataclass(frozen=True)
class ExternalBinding:
    """Keep canonical identity, provider identity, and recovery locator as separate concerns."""

    canonical_id: str
    external_identity: ProviderScopedExternalIdentity
    recovery_locator: str | None = None
    transition_history: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.canonical_id.strip():
            raise ValueError("canonical binding identity must be non-empty")
        if self.recovery_locator is not None and not self.recovery_locator.strip():
            raise ValueError("recovery locator must be non-empty when supplied")


@dataclass(frozen=True)
class EventIngressReceipt:
    """Durable receipt identity for one authenticated external delivery."""

    provider: str
    delivery_id: str
    event_kind: str
    external_identity: ProviderScopedExternalIdentity
    received_at: str
    source_scope: tuple[str, ...] = ()
    state: EventIngressState = EventIngressState.RECEIVED
    canonical_id: str | None = None
    authoritative_state_revision: str | None = None
    resource_generation: str | None = None

    def __post_init__(self) -> None:
        identity_fields = (self.provider, self.delivery_id, self.event_kind, self.received_at)
        if any(not value.strip() for value in identity_fields):
            raise ValueError("event receipt identity fields must be non-empty")
        if self.provider != self.external_identity.provider:
            raise ValueError("event provider must match external resource provider")
        if any(not component.strip() for component in self.source_scope):
            raise ValueError("event source scope components must be non-empty")
        if not self.source_scope:
            raise ValueError("provider-scoped delivery identity requires source scope")

    @property
    def dedup_key(self) -> tuple[str, ...]:
        return (self.provider, *self.source_scope, self.delivery_id)

    @property
    def delivery_subject(self) -> tuple[object, ...]:
        return (self.dedup_key, self.event_kind, self.external_identity.binding_key)


def admit_event_receipt(
    existing: EventIngressReceipt | None,
    incoming: EventIngressReceipt,
) -> tuple[EventIngressReceipt, bool]:
    """Persist once by provider/source-scoped delivery identity; a retry reuses the durable receipt."""
    if incoming.state is not EventIngressState.RECEIVED:
        raise ValueError("only a newly received event may enter ingress admission")
    if existing is None:
        return incoming, True
    if existing.dedup_key != incoming.dedup_key:
        raise ValueError("existing receipt must use the incoming delivery dedup key")
    if existing.delivery_subject != incoming.delivery_subject:
        raise ValueError("delivery dedup identity collision changed event subject")
    return existing, False


def begin_event_reconciliation(receipt: EventIngressReceipt) -> EventIngressReceipt:
    """Event arrival is only a reconciliation trigger; it is never direct transition authority."""
    if receipt.state is EventIngressState.RECEIVED:
        return replace(receipt, state=EventIngressState.RECONCILE_REQUIRED)
    if receipt.state is EventIngressState.RECONCILE_REQUIRED:
        return receipt
    raise ValueError("terminal event receipt cannot begin another semantic effect")


def settle_event_reconciliation(
    receipt: EventIngressReceipt,
    *,
    canonical_id: str,
    authoritative_state_revision: str,
    policy_authorized: bool,
    expected_resource_generation: str,
    current_resource_generation: str,
    semantic_change: bool,
) -> EventIngressReceipt:
    """Settle after trusted current-state observation, canonical policy, and a per-resource generation fence.

    policy_authorized is an input from canonical server policy, never from the event payload.
    """
    if receipt.state is not EventIngressState.RECONCILE_REQUIRED:
        raise ValueError("event settlement requires RECONCILE_REQUIRED")
    if not canonical_id.strip() or not authoritative_state_revision.strip():
        raise ValueError("canonical identity and authoritative state revision are required")
    if not expected_resource_generation.strip() or not current_resource_generation.strip():
        raise ValueError("resource generation fence values are required")
    if not policy_authorized:
        raise ValueError("event delivery does not grant canonical transition authority")
    if expected_resource_generation != current_resource_generation:
        return receipt
    state = EventIngressState.APPLIED if semantic_change else EventIngressState.NO_CHANGE
    return replace(
        receipt,
        state=state,
        canonical_id=canonical_id,
        authoritative_state_revision=authoritative_state_revision,
        resource_generation=current_resource_generation,
    )


def rebind_external_resource(
    binding: ExternalBinding,
    new_external_identity: ProviderScopedExternalIdentity,
    *,
    reason: str,
) -> ExternalBinding:
    """Rename/transfer/move an external projection without creating a second canonical entity."""
    if not reason.strip():
        raise ValueError("rebind reason must be non-empty")
    transition = f"rebind:{binding.external_identity.binding_key!r}->{new_external_identity.binding_key!r}:{reason}"
    return replace(
        binding,
        external_identity=new_external_identity,
        transition_history=(*binding.transition_history, transition),
    )


def binding_matches_external(binding: ExternalBinding, candidate: ProviderScopedExternalIdentity) -> bool:
    """Recovery locators never participate in binding authority."""
    return binding.external_identity.binding_key == candidate.binding_key


def mark_projection_ambiguous(entry: ProjectionOutboxEntry) -> ProjectionOutboxEntry:
    """Ambiguous provider delivery requires reconciliation, never optimistic replay."""
    if entry.state is not ProjectionDeliveryState.PENDING:
        raise ValueError("only a pending projection write can become ambiguous")
    return replace(entry, state=ProjectionDeliveryState.RECONCILE_REQUIRED)


def reconcile_projection_delivery(
    entry: ProjectionOutboxEntry,
    authoritative_present: bool | None,
) -> ProjectionOutboxEntry:
    """Resolve ambiguous projection delivery from authoritative provider state."""
    if entry.state is not ProjectionDeliveryState.RECONCILE_REQUIRED:
        raise ValueError("projection reconciliation requires RECONCILE_REQUIRED")
    if authoritative_present is True:
        return replace(entry, state=ProjectionDeliveryState.CONFIRMED)
    if authoritative_present is False:
        return replace(entry, state=ProjectionDeliveryState.DISPROVEN)
    return entry


def retarget_projection(entity: CanonicalEntity, new_projection_target: str, *, reason: str) -> CanonicalEntity:
    """Move/replace a projection without changing canonical entity identity or owner."""
    if not new_projection_target.strip() or not reason.strip():
        raise ValueError("retarget target and reason must be non-empty")
    transition = f"retarget:{entity.projection_target}->{new_projection_target}:{reason}"
    return replace(
        entity,
        projection_target=new_projection_target,
        transition_history=(*entity.transition_history, transition),
    )

class ProjectionFieldOwnership(StrEnum):
    """Authority class for one semantic projection field or namespace."""

    CANONICAL_OWNED = "canonical_owned"
    EXTERNAL_ADVISORY = "external_advisory"
    SHARED_MANAGED_REGIONS = "shared_managed_regions"
    EXTERNAL_EXECUTION = "external_execution"
    UNKNOWN = "unknown"


class ProjectionDriftKind(StrEnum):
    """Operational drift class emitted after field-policy classification."""

    CANONICAL_FIELD_DRIFT = "canonical_field_drift"
    ADVISORY_METADATA_CHANGE = "advisory_metadata_change"
    EXTERNAL_EXECUTION_CONFLICT = "external_execution_conflict"
    SHARED_REGION_CONFLICT = "shared_region_conflict"
    UNKNOWN_FIELD_POLICY = "unknown_field_policy"


class ExternalWorkState(StrEnum):
    """Canonical scheduler view of externally started work."""

    NONE = "none"
    OBSERVED_UNRECONCILED = "observed_unreconciled"
    ACTIVE_ADOPTED = "active_adopted"
    BLOCKED_PENDING_REVERT = "blocked_pending_revert"
    TERMINAL_RECONCILED = "terminal_reconciled"


@dataclass(frozen=True)
class ProjectionFieldRule:
    """Authority and external-mutation policy for one semantic field or namespace."""

    field: str
    ownership: ProjectionFieldOwnership
    authority: str
    external_mutation: str
    side_effect_class: str = "metadata"
    managed_regions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.field.strip() or not self.authority.strip() or not self.external_mutation.strip():
            raise ValueError("projection field rule identity and policy values must be non-empty")
        if self.ownership is ProjectionFieldOwnership.EXTERNAL_EXECUTION and self.side_effect_class == "metadata":
            raise ValueError("external_execution field must declare a work-starting side-effect class")
        if self.ownership is ProjectionFieldOwnership.SHARED_MANAGED_REGIONS and not self.managed_regions:
            raise ValueError("shared_managed_regions field requires managed regions")
        if len(set(self.managed_regions)) != len(self.managed_regions) or any(
            not region.strip() for region in self.managed_regions
        ):
            raise ValueError("managed regions must be unique and non-empty")


@dataclass(frozen=True)
class ProjectionFieldPolicy:
    """Revisioned field/namespace ownership policy for one writable projection."""

    revision: str
    fields: tuple[ProjectionFieldRule, ...]

    def __post_init__(self) -> None:
        if not self.revision.strip():
            raise ValueError("projection field policy revision must be non-empty")
        names = [rule.field for rule in self.fields]
        if len(set(names)) != len(names):
            raise ValueError("projection field policy fields must be unique")

    def rule_for(self, field: str) -> ProjectionFieldRule:
        """Resolve an explicit field rule or return conservative unknown semantics."""
        if not field.strip():
            raise ValueError("projection field name must be non-empty")
        for rule in self.fields:
            if rule.field == field:
                return rule
        return ProjectionFieldRule(
            field=field,
            ownership=ProjectionFieldOwnership.UNKNOWN,
            authority="none",
            external_mutation="fail_closed",
        )


@dataclass(frozen=True)
class ExternalAutomationGrant:
    """Least-privilege action grant for one semantic field/namespace."""

    field: str
    actions: tuple[str, ...]
    allowed_regions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.field.strip() or not self.actions:
            raise ValueError("automation grant field and actions must be non-empty")
        if len(set(self.actions)) != len(self.actions) or any(not action.strip() for action in self.actions):
            raise ValueError("automation grant actions must be unique and non-empty")
        if len(set(self.allowed_regions)) != len(self.allowed_regions) or any(
            not region.strip() for region in self.allowed_regions
        ):
            raise ValueError("automation grant regions must be unique and non-empty")


@dataclass(frozen=True)
class ExecutionBoundaryIdentity:
    """Executor plus admitted environment started by an execution-producing projection action."""

    executor: str
    environment: str

    def __post_init__(self) -> None:
        if not self.executor.strip() or not self.environment.strip():
            raise ValueError("execution boundary executor and environment must be non-empty")


@dataclass(frozen=True)
class ExternalAutomationCapability:
    """Field/action-scoped external automation capability admitted by canonical policy."""

    name: str
    grants: tuple[ExternalAutomationGrant, ...]
    allowed_side_effect_classes: tuple[str, ...] = ("metadata",)
    execution_boundary: ExecutionBoundaryIdentity | None = None

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.grants:
            raise ValueError("automation capability name and grants must be non-empty")
        grant_fields = [grant.field for grant in self.grants]
        if len(set(grant_fields)) != len(grant_fields):
            raise ValueError("automation capability must not duplicate field grants")
        if len(set(self.allowed_side_effect_classes)) != len(self.allowed_side_effect_classes) or any(
            not value.strip() for value in self.allowed_side_effect_classes
        ):
            raise ValueError("automation capability side-effect classes must be unique and non-empty")
        if "starts_work" in self.allowed_side_effect_classes and self.execution_boundary is None:
            raise ValueError("work-starting automation capability requires execution boundary identity")

    def grant_for(self, field: str) -> ExternalAutomationGrant | None:
        """Return the exact field grant; never infer a fields×actions cross-product."""
        for grant in self.grants:
            if grant.field == field:
                return grant
        return None


@dataclass(frozen=True)
class ProjectionAuditEvidence:
    """Bounded provider metadata retained only as evidence, never as transition authority."""

    actor: str
    field: str
    policy_revision: str
    reconciliation_outcome: str
    provider_confidence: str | None = None
    provider_rationale: str | None = None
    old_value_digest: str | None = None
    new_value_digest: str | None = None

    def __post_init__(self) -> None:
        for value in (self.actor, self.field, self.policy_revision, self.reconciliation_outcome):
            if not value.strip():
                raise ValueError("audit evidence identity fields must be non-empty")
        for label, value, limit in (
            ("provider confidence", self.provider_confidence, 64),
            ("provider rationale", self.provider_rationale, 256),
            ("old value digest", self.old_value_digest, 128),
            ("new value digest", self.new_value_digest, 128),
        ):
            if value is not None and (not value.strip() or len(value) > limit):
                raise ValueError(f"{label} must be non-empty and bounded when supplied")


def classify_projection_change(
    policy: ProjectionFieldPolicy,
    field: str,
    *,
    managed_region_touched: bool = False,
) -> ProjectionDriftKind:
    """Classify external drift without promoting advisory metadata to canonical authority."""
    rule = policy.rule_for(field)
    if rule.ownership is ProjectionFieldOwnership.CANONICAL_OWNED:
        return ProjectionDriftKind.CANONICAL_FIELD_DRIFT
    if rule.ownership is ProjectionFieldOwnership.EXTERNAL_ADVISORY:
        return ProjectionDriftKind.ADVISORY_METADATA_CHANGE
    if rule.ownership is ProjectionFieldOwnership.SHARED_MANAGED_REGIONS:
        return (
            ProjectionDriftKind.SHARED_REGION_CONFLICT
            if managed_region_touched
            else ProjectionDriftKind.ADVISORY_METADATA_CHANGE
        )
    if rule.ownership is ProjectionFieldOwnership.EXTERNAL_EXECUTION:
        return ProjectionDriftKind.EXTERNAL_EXECUTION_CONFLICT
    return ProjectionDriftKind.UNKNOWN_FIELD_POLICY


def admit_external_automation(
    policy: ProjectionFieldPolicy,
    capability: ExternalAutomationCapability,
    *,
    field: str,
    action: str,
    region: str | None = None,
) -> bool:
    """Admit trusted field/action/region capability; provider confidence is intentionally not an input."""
    rule = policy.rule_for(field)
    if rule.ownership in {ProjectionFieldOwnership.CANONICAL_OWNED, ProjectionFieldOwnership.UNKNOWN}:
        return False
    grant = capability.grant_for(field)
    if grant is None or action not in grant.actions or rule.side_effect_class not in capability.allowed_side_effect_classes:
        return False
    if rule.ownership is ProjectionFieldOwnership.SHARED_MANAGED_REGIONS:
        return region is not None and region in grant.allowed_regions and region not in rule.managed_regions
    return region is None


def reconcile_shared_regions(
    rule: ProjectionFieldRule,
    *,
    canonical_regions: dict[str, str],
    external_regions: dict[str, str],
) -> dict[str, str]:
    """Update canonical-managed regions while preserving admitted external enrichment."""
    if rule.ownership is not ProjectionFieldOwnership.SHARED_MANAGED_REGIONS:
        raise ValueError("shared-region reconciliation requires shared_managed_regions ownership")
    unexpected = set(canonical_regions) - set(rule.managed_regions)
    if unexpected:
        raise ValueError("canonical update attempted to own an undeclared shared-field region")
    merged = dict(external_regions)
    for region in rule.managed_regions:
        if region in canonical_regions:
            merged[region] = canonical_regions[region]
    return merged


def canonical_scheduler_may_claim(external_work_state: ExternalWorkState) -> bool:
    """Block a second canonical worker until externally started work is terminally reconciled."""
    return external_work_state in {ExternalWorkState.NONE, ExternalWorkState.TERMINAL_RECONCILED}


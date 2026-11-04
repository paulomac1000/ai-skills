"""Autonomous Delivery Policy v1 (issue #94).

Deterministic, provider-neutral policy compiler and evaluator that decides
which delivery gates are mandatory for one work item and what boundary
constitutes terminal success. The policy composes the canonical contracts and
never redefines them:

- #91 execution evidence (``contracts/execution_evidence.py``) supplies the
  receipt model, currentness, and gate evaluation consumed here;
- #92 IntegrationLease owns integration authority; this policy only decides
  whether integration is enabled and lease-gated;
- #93 ReviewReceipt owns review evidence semantics; required rubric/criteria
  are bound by reference;
- #97 runtime acceptance, #54 DeploymentLease, #113 change acceptance and the
  external-gate deviation contract remain canonical for their concerns.

Hard invariants implemented here:

- required reviewer/verifier/provider unavailable is never review PASS;
- a candidate policy change cannot self-authorize its own weakened gates
  (``resolve_effective_policy`` fails closed without a separately governed
  transition);
- risk profiles (quick/standard/deep) are consumer profiles projecting the
  existing ``RiskLevel`` taxonomy (LOW/MEDIUM/HIGH from
  ``qa-change-verifier``) — never a second risk model;
- children may consume or narrow admitted outer budgets and can never enlarge
  them;
- a successful earlier stage never compensates for a missing later required
  stage, and the terminal boundary is derived from trusted policy, not from
  worker heuristics.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Final

from contracts.execution_evidence import (
    AUTHORITY_FLOOR_FOR_KIND,
    AuthorityClass,
    CurrentIdentities,
    CurrentnessReport,
    DependencyKind,
    EvidenceGraph,
    GateDecision,
    GateRequirement,
    GateState,
    ReceiptKind,
    SubjectKind,
    authority_satisfies,
    derive_currentness,
    evaluate_gate,
)

SCHEMA_VERSION = 1

_MAX_ID = 256
_MAX_REF = 512


def _sha256_hex(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(document: Mapping[str, object]) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def policy_digest(document: Mapping[str, object]) -> str:
    body = {key: value for key, value in document.items() if key != "digest"}
    return _sha256_hex(canonical_json_bytes(body))


class WorkKind(StrEnum):
    INVESTIGATION = "INVESTIGATION"
    IMPLEMENTATION = "IMPLEMENTATION"
    OPERATOR_ACTION = "OPERATOR_ACTION"
    COORDINATION = "COORDINATION"


class RiskLevel(StrEnum):
    """Projection of the existing ``qa-change-verifier`` risk taxonomy."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RiskProfileName(StrEnum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class PlanningMode(StrEnum):
    NONE = "none"
    WORKER_PLAN = "worker_plan"
    INDEPENDENT_CHALLENGE = "independent_challenge"


class AutonomyLevel(StrEnum):
    IMPLEMENT_ONLY = "implement_only"
    INTEGRATE = "integrate"
    RELEASE = "release"


class TerminalBoundary(StrEnum):
    IMPLEMENTATION_COMPLETED = "implementation_completed"
    INTEGRATED = "integrated"
    ARTIFACT_ACCEPTED = "artifact_accepted"
    RUNTIME_ACCEPTED = "runtime_accepted"
    EVIDENCE_BACKED_FINDINGS = "evidence_backed_findings"
    DECOMPOSITION_REQUIRED = "decomposition_required"


class DeliveryDecisionKind(StrEnum):
    ADMITTED = "ADMITTED"
    WAITING_REQUIRED_EVIDENCE = "WAITING_REQUIRED_EVIDENCE"
    REQUIRED_CAPABILITY_UNAVAILABLE = "REQUIRED_CAPABILITY_UNAVAILABLE"
    POLICY_STALE = "POLICY_STALE"
    POLICY_CONFLICT = "POLICY_CONFLICT"
    PLAN_REVISE = "PLAN_REVISE"
    PLAN_STALE = "PLAN_STALE"
    REPAIR_BUDGET_EXHAUSTED = "REPAIR_BUDGET_EXHAUSTED"
    INTEGRATION_NOT_AUTHORIZED = "INTEGRATION_NOT_AUTHORIZED"
    RELEASE_NOT_AUTHORIZED = "RELEASE_NOT_AUTHORIZED"
    TERMINAL_ACCEPTED = "TERMINAL_ACCEPTED"


class IndependenceDimension(StrEnum):
    MODEL = "model"
    ORGANIZATION = "organization"
    ACCOUNT = "account"
    TRANSPORT = "transport"
    HUMAN = "human"


class ReviewerIndependence(StrEnum):
    QUALIFIED = "QUALIFIED"
    SHARED_UNATTESTED_UPSTREAM = "SHARED_UNATTESTED_UPSTREAM"
    DIMENSION_COLLISION = "DIMENSION_COLLISION"
    UNATTESTED_UPSTREAM = "UNATTESTED_UPSTREAM"


class SurfaceMode(StrEnum):
    AUTONOMOUS = "autonomous"
    SCOPED_GRANT = "scoped_grant"
    HUMAN_APPROVAL = "human_approval"
    OPERATOR_ADMIN_ONLY = "operator_admin_only"
    FORBIDDEN = "forbidden"


class MutationAuthorityDerivation(StrEnum):
    AUTONOMOUS = "AUTONOMOUS"
    GRANT_REQUIRED = "GRANT_REQUIRED"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"
    OPERATOR_ADMIN_REQUIRED = "OPERATOR_ADMIN_REQUIRED"
    FORBIDDEN = "FORBIDDEN"


_AUTONOMY_RANK: Final = {AutonomyLevel.IMPLEMENT_ONLY: 0, AutonomyLevel.INTEGRATE: 1, AutonomyLevel.RELEASE: 2}

_PROFILE_FOR_RISK: Final = {
    RiskLevel.LOW: RiskProfileName.QUICK,
    RiskLevel.MEDIUM: RiskProfileName.STANDARD,
    RiskLevel.HIGH: RiskProfileName.DEEP,
}


def _bounded(value: object, name: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError(f"{name} must be a non-empty string of at most {max_length} characters")
    return value


def _optional_bounded(value: object, name: str, max_length: int) -> str | None:
    if value is None:
        return None
    return _bounded(value, name, max_length)


def _require_digest(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{name} must be a sha256 digest")
    return value


def _envelope(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _int_field(value: object, name: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _str_list_field(value: object, name: str, max_length: int = 128) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    return tuple(_bounded(item, name, max_length) for item in value)


def _enum_field(value: object, name: str, enum_type: type[StrEnum]) -> StrEnum:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string enum value")
    return enum_type(value)


@dataclass(frozen=True)
class TrustBinding:
    source_ref: str
    source_digest: str
    established_by: str | None


@dataclass(frozen=True)
class RiskProfile:
    name: RiskProfileName
    maps_risk_level: RiskLevel
    verification_layers: tuple[str, ...]
    reviewer_count: int
    independent_verification_required: bool
    focus_areas: tuple[str, ...]


@dataclass(frozen=True)
class WorkKindRule:
    work_kind: WorkKind
    terminal_boundary: TerminalBoundary
    requires_pr: bool
    requires_release: bool
    requires_operator_grant: bool
    risk_profile: RiskProfileName | None
    planning_mode_override: PlanningMode | None
    review_required_override: bool | None
    verification_required_override: bool | None
    integration_enabled_override: bool | None
    release_enabled_override: bool | None


@dataclass(frozen=True)
class DeliveryPolicy:
    policy_id: str
    revision: str
    digest: str
    trust_binding: TrustBinding
    autonomy_maximum: AutonomyLevel
    work_kind_rules: Mapping[WorkKind, WorkKindRule]
    risk_profiles: Mapping[RiskProfileName, RiskProfile]
    planning_mode: PlanningMode
    planning_challenge_class: str | None
    planning_max_revision_rounds: int
    planning_stale_on: tuple[str, ...]
    review_required: bool
    review_count: int
    review_required_dimensions: tuple[str, ...]
    review_upstream_attestation_required: bool
    review_rubric_ref: str | None
    review_stale_on_candidate_change: bool
    review_final_exact_head_required: bool
    independent_verification_required: bool
    integration_enabled: bool
    integration_lease_required: bool
    integrated_acceptance_required: bool
    release_enabled: bool
    deployment_lease_required: bool
    rollback_required: bool
    mutation_authority: Mapping[str, str]
    review_convergence_max_repair_rounds: int
    review_convergence_final_full_review_required: bool
    budgets: Mapping[str, int]
    terminal_boundary: TerminalBoundary
    documents: Mapping[str, object] = field(default_factory=dict)


def admit_policy(document: Mapping[str, object]) -> tuple[DeliveryPolicy | None, tuple[str, ...]]:
    """Admit one policy document fail-closed.

    Digest integrity, a trust binding established outside candidate control,
    and the complete work-kind/profile vocabulary are required. The returned
    policy is still only a candidate declaration until a caller resolves it
    against the trusted source via :func:`resolve_effective_policy`.
    """
    reasons: list[str] = []
    try:
        policy_id = _bounded(document.get("policy_id"), "policy_id", _MAX_ID)
        revision = _bounded(document.get("revision"), "revision", 128)
        declared_digest = _require_digest(document.get("digest"), "digest")
        trust = _envelope(document.get("trust_binding"), "trust_binding")
        trust_binding = TrustBinding(
            source_ref=_bounded(trust.get("source_ref"), "trust_binding.source_ref", _MAX_REF),
            source_digest=_require_digest(trust.get("source_digest"), "trust_binding.source_digest"),
            established_by=_optional_bounded(trust.get("established_by"), "trust_binding.established_by", _MAX_ID),
        )
        autonomy = AutonomyLevel(
            _bounded(_envelope(document.get("autonomy"), "autonomy").get("maximum_level"), "autonomy.maximum_level", 32)
        )
        if policy_digest(document) != declared_digest:
            reasons.append("POLICY_DIGEST_MISMATCH")

        work_kinds_document = _envelope(document.get("work_kinds"), "work_kinds")
        work_kind_rules: dict[WorkKind, WorkKindRule] = {}
        for kind in WorkKind:
            rule_document = _envelope(work_kinds_document.get(kind.value), f"work_kinds.{kind.value}")
            boundary = TerminalBoundary(
                _bounded(rule_document.get("terminal_boundary"), f"work_kinds.{kind.value}.terminal_boundary", 64)
            )
            profile = rule_document.get("risk_profile")
            risk_profile_name: RiskProfileName | None = None
            if profile is not None:
                if not isinstance(profile, str):
                    raise ValueError(f"work_kinds.{kind.value}.risk_profile must be a string")
                risk_profile_name = RiskProfileName(profile)
            work_kind_rules[kind] = WorkKindRule(
                work_kind=kind,
                terminal_boundary=boundary,
                requires_pr=bool(rule_document.get("requires_pr", False)),
                requires_release=bool(rule_document.get("requires_release", False)),
                requires_operator_grant=bool(rule_document.get("requires_operator_grant", False)),
                risk_profile=risk_profile_name,
                planning_mode_override=(
                    PlanningMode(planning_override)
                    if isinstance(planning_override := rule_document.get("planning_mode_override"), str)
                    else None
                ),
                review_required_override=(
                    bool(rule_document["review_required_override"])
                    if rule_document.get("review_required_override") is not None
                    else None
                ),
                verification_required_override=(
                    bool(rule_document["verification_required_override"])
                    if rule_document.get("verification_required_override") is not None
                    else None
                ),
                integration_enabled_override=(
                    bool(rule_document["integration_enabled_override"])
                    if rule_document.get("integration_enabled_override") is not None
                    else None
                ),
                release_enabled_override=(
                    bool(rule_document["release_enabled_override"])
                    if rule_document.get("release_enabled_override") is not None
                    else None
                ),
            )

        profiles_document = _envelope(document.get("risk_profiles"), "risk_profiles")
        risk_profiles: dict[RiskProfileName, RiskProfile] = {}
        for name in RiskProfileName:
            profile_document = _envelope(profiles_document.get(name.value), f"risk_profiles.{name.value}")
            layers = profile_document.get("verification_layers")
            if not isinstance(layers, list) or not layers:
                raise ValueError(f"risk_profiles.{name.value}.verification_layers must be a non-empty array")
            risk_profiles[name] = RiskProfile(
                name=name,
                maps_risk_level=RiskLevel(
                    _bounded(profile_document.get("maps_risk_level"), f"risk_profiles.{name.value}.maps_risk_level", 16)
                ),
                verification_layers=tuple(_bounded(layer, f"risk_profiles.{name.value}.layer", 64) for layer in layers),
                reviewer_count=_int_field(
                    profile_document.get("reviewer_count"), f"risk_profiles.{name.value}.reviewer_count", 0
                ),
                independent_verification_required=bool(
                    profile_document.get("independent_verification_required", False)
                ),
                focus_areas=_str_list_field(
                    profile_document.get("focus_areas"), f"risk_profiles.{name.value}.focus_area"
                ),
            )

        planning = _envelope(document.get("planning"), "planning")
        review = _envelope(document.get("review"), "review")
        verification = _envelope(document.get("independent_verification"), "independent_verification")
        integration = _envelope(document.get("integration"), "integration")
        release = _envelope(document.get("release"), "release")
        budgets_document = _envelope(document.get("budgets"), "budgets")
        convergence = document.get("review_convergence")
        mutation = document.get("mutation_authority")

        def _int(value: object, default: int) -> int:
            return int(value) if isinstance(value, int) else default

        budgets = {
            "plan_revision_rounds": _int(budgets_document.get("plan_revision_rounds"), 0),
            "repair_rounds": _int(budgets_document.get("repair_rounds"), 0),
            "outer_retry_budget": _int(budgets_document.get("outer_retry_budget"), 0),
        }

        mutation_authority: dict[str, str] = {}
        if mutation is not None:
            parsed = _envelope(mutation, "mutation_authority")
            for key in ("persistent_repository", "external_service", "destructive"):
                mutation_authority[key] = SurfaceMode(_bounded(parsed.get(key), f"mutation_authority.{key}", 32)).value

        convergence_max_repairs = 0
        convergence_final_full_review = False
        if convergence is not None:
            parsed = _envelope(convergence, "review_convergence")
            convergence_max_repairs = _int(parsed.get("max_repair_rounds"), 0)
            convergence_final_full_review = bool(parsed.get("final_full_review_required", False))

        terminal_boundary = TerminalBoundary(_bounded(document.get("terminal_boundary"), "terminal_boundary", 64))

        policy = DeliveryPolicy(
            policy_id=policy_id,
            revision=revision,
            digest=declared_digest,
            trust_binding=trust_binding,
            autonomy_maximum=autonomy,
            work_kind_rules=work_kind_rules,
            risk_profiles=risk_profiles,
            planning_mode=PlanningMode(_bounded(planning.get("mode"), "planning.mode", 32)),
            planning_challenge_class=_optional_bounded(planning.get("challenge_class"), "planning.challenge_class", 64),
            planning_max_revision_rounds=_int(planning.get("max_revision_rounds"), 0),
            planning_stale_on=_str_list_field(planning.get("stale_on"), "planning.stale_on", 64),
            review_required=bool(review.get("required", False)),
            review_count=_int(review.get("count"), 0),
            review_required_dimensions=_str_list_field(
                review.get("required_dimensions"), "review.required_dimensions", 32
            ),
            review_upstream_attestation_required=bool(review.get("upstream_attestation_required", False)),
            review_rubric_ref=_optional_bounded(review.get("rubric_ref"), "review.rubric_ref", _MAX_REF),
            review_stale_on_candidate_change=bool(review.get("stale_on_candidate_change", True)),
            review_final_exact_head_required=bool(review.get("final_exact_head_required", True)),
            independent_verification_required=bool(verification.get("required", False)),
            integration_enabled=bool(integration.get("enabled", False)),
            integration_lease_required=bool(integration.get("integration_lease_required", True)),
            integrated_acceptance_required=bool(
                _envelope(document.get("integrated_acceptance"), "integrated_acceptance").get("required", False)
            )
            if document.get("integrated_acceptance") is not None
            else False,
            release_enabled=bool(release.get("enabled", False)),
            deployment_lease_required=bool(release.get("deployment_lease_required", True)),
            rollback_required=bool(release.get("rollback_required", False)),
            mutation_authority=mutation_authority,
            review_convergence_max_repair_rounds=convergence_max_repairs,
            review_convergence_final_full_review_required=convergence_final_full_review,
            budgets=budgets,
            terminal_boundary=terminal_boundary,
            documents=dict(document),
        )
    except (ValueError, KeyError, TypeError) as error:
        return None, (str(error),)

    if reasons:
        return None, tuple(reasons)
    return policy, ()


@dataclass(frozen=True)
class WorkSpec:
    """Provider-neutral projection of the current WorkSpec vocabulary.

    ``change_risk`` reuses the existing LOW/MEDIUM/HIGH taxonomy; criteria are
    referenced by the #113 change-acceptance contract, never redefined here.
    """

    work_kind: WorkKind
    change_risk: RiskLevel
    required_method: str | None = None
    target_profile: str | None = None
    criteria_ids: tuple[str, ...] = ()
    expected_policy_revision: str | None = None
    expected_policy_digest: str | None = None
    planning_base_sha: str | None = None
    execution_base_sha: str | None = None
    protected_surfaces_touched: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompiledGates:
    work_kind: WorkKind
    risk_profile: RiskProfile
    planning_mode: PlanningMode
    review_required: bool
    review_count: int
    validation_required: bool
    verification_required: bool
    integration_required: bool
    integration_authorized: bool
    release_required: bool
    release_authorized: bool
    integrated_acceptance_required: bool
    operator_grant_required: bool
    decomposition_required: bool
    terminal_boundary: TerminalBoundary
    verification_layers: tuple[str, ...]
    notes: tuple[str, ...] = ()


def compile_gates(policy: DeliveryPolicy, workspec: WorkSpec) -> CompiledGates:
    """Deterministically compile required gates for one admitted work item.

    Risk profiles project the existing risk taxonomy: the profile for a
    ``change_risk`` is fixed (LOW→quick, MEDIUM→standard, HIGH→deep), so a
    critical change can never compile down to a lighter profile, and profiles
    never become a second risk-scoring algorithm.
    """
    rule = policy.work_kind_rules[workspec.work_kind]
    profile_name = rule.risk_profile or _PROFILE_FOR_RISK[workspec.change_risk]
    profile = policy.risk_profiles[profile_name]
    notes: list[str] = []

    planning_mode = rule.planning_mode_override or policy.planning_mode
    review_required = (
        rule.review_required_override
        if rule.review_required_override is not None
        else (policy.review_required or profile.reviewer_count > 0)
    )
    review_count = max(policy.review_count, profile.reviewer_count) if review_required else 0
    verification_required = (
        rule.verification_required_override
        if rule.verification_required_override is not None
        else (policy.independent_verification_required or profile.independent_verification_required)
    )
    validation_required = workspec.work_kind is not WorkKind.INVESTIGATION

    autonomy_rank = _AUTONOMY_RANK[policy.autonomy_maximum]
    integration_required = workspec.work_kind is WorkKind.IMPLEMENTATION and rule.terminal_boundary in (
        TerminalBoundary.INTEGRATED,
        TerminalBoundary.ARTIFACT_ACCEPTED,
        TerminalBoundary.RUNTIME_ACCEPTED,
    )
    integration_enabled = (
        rule.integration_enabled_override
        if rule.integration_enabled_override is not None
        else policy.integration_enabled
    )
    integration_authorized = integration_enabled and autonomy_rank >= _AUTONOMY_RANK[AutonomyLevel.INTEGRATE]

    release_required = rule.requires_release or (
        rule.release_enabled_override if rule.release_enabled_override is not None else policy.release_enabled
    )
    if workspec.work_kind is not WorkKind.IMPLEMENTATION:
        release_required = rule.requires_release
    release_authorized = (
        release_required and policy.release_enabled and autonomy_rank >= _AUTONOMY_RANK[AutonomyLevel.RELEASE]
    )

    if workspec.work_kind is WorkKind.COORDINATION:
        notes.append("COORDINATION_IS_NOT_ATOMIC_IMPLEMENTATION")
    if (
        workspec.work_kind is WorkKind.OPERATOR_ACTION
        and rule.terminal_boundary is not TerminalBoundary.DECOMPOSITION_REQUIRED
    ):
        notes.append("OPERATOR_GRANT_REQUIRED_NO_PRIVILEGE_INHERITANCE")
    if integration_required and not integration_authorized:
        notes.append("INTEGRATION_NOT_AUTHORIZED_BY_POLICY")
    if release_required and not release_authorized:
        notes.append("RELEASE_NOT_AUTHORIZED_BY_POLICY")

    return CompiledGates(
        work_kind=workspec.work_kind,
        risk_profile=profile,
        planning_mode=planning_mode,
        review_required=review_required,
        review_count=review_count,
        validation_required=validation_required,
        verification_required=verification_required,
        integration_required=integration_required,
        integration_authorized=integration_authorized,
        release_required=release_required,
        release_authorized=release_authorized,
        integrated_acceptance_required=policy.integrated_acceptance_required and integration_required,
        operator_grant_required=rule.requires_operator_grant or workspec.work_kind is WorkKind.OPERATOR_ACTION,
        decomposition_required=workspec.work_kind is WorkKind.COORDINATION
        and rule.terminal_boundary is TerminalBoundary.DECOMPOSITION_REQUIRED,
        terminal_boundary=rule.terminal_boundary,
        verification_layers=profile.verification_layers,
        notes=tuple(notes),
    )


# ---------------------------------------------------------------------------
# Anti-self-approval policy boundary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyTransition:
    """A separately governed policy-change record established outside the candidate."""

    authorized_by: str
    authority_class: AuthorityClass
    transition_ref: str
    covers_policy_digest: str


def _weakening_transitions(candidate: DeliveryPolicy, trusted: DeliveryPolicy) -> tuple[str, ...]:
    weakenings: list[str] = []
    if (
        candidate.autonomy_maximum != trusted.autonomy_maximum
        and _AUTONOMY_RANK[candidate.autonomy_maximum] > _AUTONOMY_RANK[trusted.autonomy_maximum]
    ):
        weakenings.append(
            f"autonomy.maximum_level:{trusted.autonomy_maximum.value}->{candidate.autonomy_maximum.value}"
        )
    if (
        trusted.planning_mode is PlanningMode.INDEPENDENT_CHALLENGE
        and candidate.planning_mode is not PlanningMode.INDEPENDENT_CHALLENGE
    ):
        weakenings.append(f"planning.mode:{trusted.planning_mode.value}->{candidate.planning_mode.value}")
    if trusted.review_required and not candidate.review_required:
        weakenings.append("review.required:true->false")
    if candidate.review_count < trusted.review_count:
        weakenings.append(f"review.count:{trusted.review_count}->{candidate.review_count}")
    if trusted.independent_verification_required and not candidate.independent_verification_required:
        weakenings.append("independent_verification.required:true->false")
    if not trusted.integration_enabled and candidate.integration_enabled:
        weakenings.append("integration.enabled:false->true")
    if not trusted.release_enabled and candidate.release_enabled:
        weakenings.append("release.enabled:false->true")
    if trusted.rollback_required and not candidate.rollback_required:
        weakenings.append("release.rollback_required:true->false")
    if (
        trusted.terminal_boundary in (TerminalBoundary.RUNTIME_ACCEPTED, TerminalBoundary.ARTIFACT_ACCEPTED)
        and candidate.terminal_boundary != trusted.terminal_boundary
    ):
        weakenings.append(f"terminal_boundary:{trusted.terminal_boundary.value}->{candidate.terminal_boundary.value}")
    for surface in ("persistent_repository", "external_service", "destructive"):
        trusted_mode = trusted.mutation_authority.get(surface)
        candidate_mode = candidate.mutation_authority.get(surface)
        if (
            trusted_mode
            and candidate_mode
            and candidate_mode != trusted_mode
            and candidate_mode in (SurfaceMode.AUTONOMOUS.value,)
        ):
            weakenings.append(f"mutation_authority.{surface}:{trusted_mode}->{candidate_mode}")
    if (
        trusted.review_rubric_ref is not None
        and candidate.review_rubric_ref is not None
        and candidate.review_rubric_ref != trusted.review_rubric_ref
    ):
        weakenings.append(f"review.rubric_ref:{trusted.review_rubric_ref}->{candidate.review_rubric_ref}")
    return tuple(weakenings)


@dataclass(frozen=True)
class EffectivePolicyDecision:
    policy: DeliveryPolicy
    source: str
    weakenings: tuple[str, ...]
    outcome: str


def resolve_effective_policy(
    trusted: DeliveryPolicy,
    candidate: DeliveryPolicy | None,
    transition: PolicyTransition | None,
) -> EffectivePolicyDecision:
    """Resolve the policy that governs one candidate's own delivery.

    A candidate may *propose* policy changes, but it can never approve itself
    under the weaker policy it introduces. Without a separately governed
    transition established outside the candidate tree by a qualified
    authority, the trusted policy continues to govern.
    """
    if candidate is None:
        return EffectivePolicyDecision(trusted, "trusted", (), "TRUSTED_GOVERNS")
    weakenings = _weakening_transitions(candidate, trusted)
    if not weakenings:
        return EffectivePolicyDecision(trusted, "trusted", (), "CANDIDATE_COMPATIBLE")
    if transition is None:
        return EffectivePolicyDecision(trusted, "trusted", weakenings, "POLICY_SELF_MODIFICATION_BLOCKED")
    if not authority_satisfies(transition.authority_class, AuthorityClass.OPERATOR):
        return EffectivePolicyDecision(trusted, "trusted", weakenings, "TRANSITION_AUTHORITY_INSUFFICIENT")
    if transition.covers_policy_digest != candidate.digest:
        return EffectivePolicyDecision(trusted, "trusted", weakenings, "TRANSITION_DOES_NOT_COVER_CANDIDATE")
    return EffectivePolicyDecision(candidate, "governed_transition", weakenings, "GOVERNED_TRANSITION_APPLIED")


# ---------------------------------------------------------------------------
# Reviewer independence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReviewerDescriptor:
    principal: str
    model: str | None
    organization: str | None
    account: str | None
    transport: str | None
    upstream_id: str | None
    upstream_attested: bool


@dataclass(frozen=True)
class ReviewerIndependenceReport:
    per_reviewer: Mapping[str, ReviewerIndependence]
    qualified_count: int
    required_dimensions: tuple[str, ...]


def evaluate_reviewer_independence(
    reviewers: Sequence[ReviewerDescriptor],
    required_dimensions: Sequence[str],
    upstream_attestation_required: bool,
) -> ReviewerIndependenceReport:
    """Compile required evidence independence from actual reviewer provenance.

    Different provider aliases pointing at the same unattested upstream are
    never counted as independent reviewers: an unknown shared upstream stays
    UNKNOWN, and dimensions required by policy must actually differ across
    reviewers. Independence is never inferred from alias count alone.
    """
    per_reviewer: dict[str, ReviewerIndependence] = {}
    upstream_seen: dict[str, str] = {}
    dimension_values: dict[str, set[str | None]] = {dimension: set() for dimension in required_dimensions}

    for reviewer in reviewers:
        if upstream_attestation_required and not reviewer.upstream_attested:
            per_reviewer[reviewer.principal] = ReviewerIndependence.UNATTESTED_UPSTREAM
            continue
        if reviewer.upstream_id is not None and not reviewer.upstream_attested:
            first = upstream_seen.get(reviewer.upstream_id)
            if first is not None and first != reviewer.principal:
                per_reviewer[reviewer.principal] = ReviewerIndependence.SHARED_UNATTESTED_UPSTREAM
                per_reviewer.setdefault(first, ReviewerIndependence.SHARED_UNATTESTED_UPSTREAM)
                continue
            upstream_seen[reviewer.upstream_id] = reviewer.principal

        collision = False
        for dimension in required_dimensions:
            value: str | None = {
                "model": reviewer.model,
                "organization": reviewer.organization,
                "account": reviewer.account,
                "transport": reviewer.transport,
                "human": reviewer.principal if reviewer.transport == "human" else None,
            }.get(dimension)
            if value is None and dimension != "human":
                collision = True
            dimension_values[dimension].add(value)
        per_reviewer[reviewer.principal] = (
            ReviewerIndependence.DIMENSION_COLLISION if collision else ReviewerIndependence.QUALIFIED
        )

    qualified = sum(1 for state in per_reviewer.values() if state is ReviewerIndependence.QUALIFIED)
    return ReviewerIndependenceReport(
        per_reviewer=per_reviewer,
        qualified_count=qualified,
        required_dimensions=tuple(required_dimensions),
    )


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BudgetConsumption:
    plan_revision_rounds: int = 0
    repair_rounds: int = 0
    outer_retry_used: int = 0


def check_budgets(policy: DeliveryPolicy, consumed: BudgetConsumption) -> tuple[str, ...]:
    violations: list[str] = []
    if consumed.plan_revision_rounds > policy.budgets["plan_revision_rounds"]:
        violations.append("PLAN_REVISION_BUDGET_EXCEEDED")
    if consumed.repair_rounds > policy.budgets["repair_rounds"]:
        violations.append("REPAIR_BUDGET_EXCEEDED")
    if consumed.outer_retry_used > policy.budgets["outer_retry_budget"]:
        violations.append("OUTER_RETRY_BUDGET_EXCEEDED")
    return tuple(violations)


def narrow_budget(child: BudgetConsumption, parent: BudgetConsumption) -> tuple[str, ...]:
    """Child/runtime layers may consume or narrow the admitted outer budget,
    never silently expand it."""
    violations: list[str] = []
    if child.outer_retry_used > parent.outer_retry_used:
        violations.append("CHILD_ENLARGED_OUTER_RETRY_BUDGET")
    if child.repair_rounds > parent.repair_rounds:
        violations.append("CHILD_ENLARGED_REPAIR_BUDGET")
    if child.plan_revision_rounds > parent.plan_revision_rounds:
        violations.append("CHILD_ENLARGED_PLAN_REVISION_BUDGET")
    return tuple(violations)


# ---------------------------------------------------------------------------
# Delivery evaluation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CapabilityReport:
    """Declared availability of required producer classes for this evaluation.

    An entry maps an authority class to ``available`` or a typed unavailable
    reason. Missing entries mean unknown, which is non-green for gates that
    require that class.
    """

    availability: Mapping[str, str] = field(default_factory=dict)

    def status_for(self, authority: AuthorityClass) -> str:
        return self.availability.get(authority.value, "unknown")


@dataclass(frozen=True)
class DeliveryDecision:
    outcome: DeliveryDecisionKind
    gate_decisions: Mapping[str, GateDecision]
    missing_gates: tuple[str, ...]
    reasons: tuple[str, ...]
    terminal_boundary: TerminalBoundary
    terminal_reached: bool

    @property
    def is_green(self) -> bool:
        return self.outcome is DeliveryDecisionKind.TERMINAL_ACCEPTED


def _terminal_gate(policy: DeliveryPolicy, compiled: CompiledGates) -> tuple[ReceiptKind, SubjectKind, str] | None:
    boundary = compiled.terminal_boundary
    if boundary is TerminalBoundary.IMPLEMENTATION_COMPLETED:
        return ReceiptKind.WORK_COMPLETION, SubjectKind.CANDIDATE_REVISION, "implementation completion evidence"
    if boundary is TerminalBoundary.INTEGRATED:
        return ReceiptKind.INTEGRATION, SubjectKind.INTEGRATED_REVISION, "integrated revision evidence"
    if boundary is TerminalBoundary.ARTIFACT_ACCEPTED:
        return ReceiptKind.ARTIFACT_PUBLICATION, SubjectKind.PUBLICATION, "accepted artifact evidence"
    if boundary is TerminalBoundary.RUNTIME_ACCEPTED:
        return ReceiptKind.RUNTIME_ACCEPTANCE, SubjectKind.OBSERVED_RUNTIME, "runtime acceptance evidence"
    if boundary is TerminalBoundary.EVIDENCE_BACKED_FINDINGS:
        return ReceiptKind.WORK_COMPLETION, SubjectKind.TERMINAL_EVIDENCE, "evidence-backed findings"
    return None


def evaluate_delivery(
    policy: DeliveryPolicy,
    workspec: WorkSpec,
    graph: EvidenceGraph,
    current: CurrentIdentities | None = None,
    currentness: CurrentnessReport | None = None,
    capabilities: CapabilityReport | None = None,
    plan_disposition: str | None = None,
    budget_consumed: BudgetConsumption | None = None,
) -> DeliveryDecision:
    """Evaluate one delivery against the compiled policy gates.

    Every required gate is evaluated; earlier green stages never compensate
    for missing or non-green later required stages. The returned decision
    carries the typed outcome, per-gate detail, and the exact missing set.
    """
    compiled = compile_gates(policy, workspec)
    reasons: list[str] = []
    capabilities = capabilities or CapabilityReport()
    report = currentness if currentness is not None else derive_currentness(graph, current or CurrentIdentities())

    # Policy currency for this exact work item.
    if workspec.expected_policy_digest is not None and workspec.expected_policy_digest != policy.digest:
        return DeliveryDecision(
            DeliveryDecisionKind.POLICY_STALE,
            {},
            (),
            ("WORKSPEC_POLICY_DIGEST_MISMATCH",),
            compiled.terminal_boundary,
            False,
        )
    if workspec.expected_policy_revision is not None and workspec.expected_policy_revision != policy.revision:
        return DeliveryDecision(
            DeliveryDecisionKind.POLICY_STALE,
            {},
            (),
            ("WORKSPEC_POLICY_REVISION_MISMATCH",),
            compiled.terminal_boundary,
            False,
        )

    # Plan gate: evidence-driven, never a caller string alone.
    plan_gate_id = "plan"
    if compiled.planning_mode is PlanningMode.NONE:
        plan_decision = GateDecision(plan_gate_id, GateState.SATISFIED, (), ("PLANNING_NOT_REQUIRED",))
    else:
        plan_floor = (
            AuthorityClass.REVIEW_PROVIDER
            if compiled.planning_mode is PlanningMode.INDEPENDENT_CHALLENGE
            else AuthorityClass.AGENT_ATTESTATION
        )
        plan_decision = evaluate_gate(
            graph,
            GateRequirement(
                gate_id=plan_gate_id,
                required_kind=ReceiptKind.PLAN_CHALLENGE,
                authority_floor=plan_floor,
            ),
            report,
        )
        if not plan_decision.is_green and plan_decision.state is GateState.PENDING:
            plan_decision = GateDecision(plan_gate_id, GateState.PENDING, (), ("PLAN_EVIDENCE_MISSING",))
        if plan_decision.is_green and compiled.planning_mode is PlanningMode.INDEPENDENT_CHALLENGE:
            # Claimed challenger authority is caller-controlled content; the
            # policy mechanically separates challenger from implementer.
            implementer_principals = {
                receipt.producer_principal
                for receipt in graph.receipts.values()
                if receipt.receipt_kind in (ReceiptKind.IMPLEMENTATION, ReceiptKind.WORK_COMPLETION)
                and receipt.producer_principal is not None
            }
            challenger_principals = {
                graph.receipts[receipt_id].producer_principal for receipt_id in plan_decision.qualifying_receipt_ids
            }
            if implementer_principals & challenger_principals:
                plan_decision = GateDecision(plan_gate_id, GateState.BLOCKED, (), ("CHALLENGER_NOT_INDEPENDENT",))

    gate_requirements: list[GateRequirement] = []
    if compiled.review_required:
        gate_requirements.append(
            GateRequirement(
                gate_id="review",
                required_kind=ReceiptKind.REVIEW,
                distinct_producers=compiled.review_count,
            )
        )
    if compiled.validation_required:
        gate_requirements.append(
            GateRequirement(
                gate_id="validation",
                required_kind=ReceiptKind.VALIDATION,
                authority_floor=AuthorityClass.DETERMINISTIC_TOOL,
            )
        )
    if compiled.terminal_boundary in (
        TerminalBoundary.IMPLEMENTATION_COMPLETED,
        TerminalBoundary.EVIDENCE_BACKED_FINDINGS,
    ):
        gate_requirements.append(
            GateRequirement(
                gate_id="terminal",
                required_kind=ReceiptKind.WORK_COMPLETION,
                subject_kind=(
                    SubjectKind.TERMINAL_EVIDENCE
                    if compiled.terminal_boundary is TerminalBoundary.EVIDENCE_BACKED_FINDINGS
                    else SubjectKind.CANDIDATE_REVISION
                ),
            )
        )
    if compiled.verification_required:
        gate_requirements.append(
            GateRequirement(
                gate_id="independent_verification",
                required_kind=ReceiptKind.INDEPENDENT_VERIFICATION,
            )
        )
    if compiled.integration_required:
        gate_requirements.append(
            GateRequirement(
                gate_id="integration",
                required_kind=ReceiptKind.INTEGRATION,
                subject_kind=SubjectKind.INTEGRATED_REVISION,
            )
        )
    if compiled.integrated_acceptance_required:
        gate_requirements.append(
            GateRequirement(
                gate_id="integrated_acceptance",
                required_kind=ReceiptKind.VALIDATION,
                subject_kind=SubjectKind.INTEGRATED_REVISION,
            )
        )
    if compiled.release_required:
        gate_requirements.append(
            GateRequirement(
                gate_id="release",
                required_kind=ReceiptKind.ARTIFACT_PUBLICATION,
                subject_kind=SubjectKind.PUBLICATION,
            )
        )
    if compiled.terminal_boundary is TerminalBoundary.RUNTIME_ACCEPTED:
        gate_requirements.append(
            GateRequirement(
                gate_id="runtime_acceptance",
                required_kind=ReceiptKind.RUNTIME_ACCEPTANCE,
                subject_kind=SubjectKind.OBSERVED_RUNTIME,
            )
        )
    if compiled.operator_grant_required:
        gate_requirements.append(
            GateRequirement(
                gate_id="operator_grant",
                required_kind=ReceiptKind.CAPABILITY_ADMISSION,
                authority_floor=AuthorityClass.OPERATOR,
            )
        )

    gate_decisions: dict[str, GateDecision] = {plan_gate_id: plan_decision}
    missing: list[str] = []

    for requirement in gate_requirements:
        if requirement.gate_id == plan_gate_id:
            gate_decisions[plan_gate_id] = plan_decision
            if not plan_decision.is_green:
                missing.append(plan_gate_id)
            continue
        floor_authority = requirement.authority_floor or AUTHORITY_FLOOR_FOR_KIND[requirement.required_kind]
        if floor_authority is not None:
            availability = capabilities.status_for(floor_authority)
            if availability in ("outage", "quota", "auth", "unavailable"):
                gate_decisions[requirement.gate_id] = GateDecision(
                    requirement.gate_id,
                    GateState.BLOCKED,
                    (),
                    (f"CAPABILITY_UNAVAILABLE:{floor_authority.value}:{availability}",),
                )
                missing.append(requirement.gate_id)
                reasons.append(f"REQUIRED_CAPABILITY_UNAVAILABLE:{floor_authority.value}")
                continue
        decision = evaluate_gate(graph, requirement, report)
        gate_decisions[requirement.gate_id] = decision
        if not decision.is_green:
            missing.append(requirement.gate_id)

    # Authorization boundaries decided by policy, not evidence volume.
    if compiled.integration_required and not compiled.integration_authorized:
        reasons.append("INTEGRATION_NOT_AUTHORIZED")
    if compiled.release_required and not compiled.release_authorized:
        reasons.append("RELEASE_NOT_AUTHORIZED")

    # Plan-level dispositions from the actual challenge result and staleness.
    if compiled.planning_mode is not PlanningMode.NONE:
        plan_receipts = [
            receipt for receipt in graph.receipts.values() if receipt.receipt_kind is ReceiptKind.PLAN_CHALLENGE
        ]
        if plan_disposition == "PLAN_REVISE" and plan_receipts:
            reasons.append("PLAN_REVISE")
        for plan_receipt in plan_receipts:
            receipt_status = report.receipts[plan_receipt.receipt_id]
            if (
                DependencyKind.PLANNING_BASE in receipt_status.stale_dependencies
                and "planning_base_change" in policy.planning_stale_on
            ):
                reasons.append("PLAN_STALE")

    budget_violations = check_budgets(policy, budget_consumed or BudgetConsumption())
    if budget_violations:
        reasons.extend(budget_violations)

    if compiled.decomposition_required:
        return DeliveryDecision(
            DeliveryDecisionKind.WAITING_REQUIRED_EVIDENCE,
            gate_decisions,
            tuple(missing),
            tuple(reasons) + ("COORDINATION_REQUIRES_DECOMPOSITION",),
            TerminalBoundary.DECOMPOSITION_REQUIRED,
            False,
        )
    if "PLAN_REVISE" in reasons:
        return DeliveryDecision(
            DeliveryDecisionKind.PLAN_REVISE,
            gate_decisions,
            tuple(missing),
            tuple(reasons),
            compiled.terminal_boundary,
            False,
        )
    if "PLAN_STALE" in reasons:
        return DeliveryDecision(
            DeliveryDecisionKind.PLAN_STALE,
            gate_decisions,
            tuple(missing),
            tuple(reasons),
            compiled.terminal_boundary,
            False,
        )
    if any(reason.startswith("REQUIRED_CAPABILITY_UNAVAILABLE") for reason in reasons):
        return DeliveryDecision(
            DeliveryDecisionKind.REQUIRED_CAPABILITY_UNAVAILABLE,
            gate_decisions,
            tuple(missing),
            tuple(reasons),
            compiled.terminal_boundary,
            False,
        )
    if any(violation.endswith("BUDGET_EXCEEDED") for violation in budget_violations):
        return DeliveryDecision(
            DeliveryDecisionKind.REPAIR_BUDGET_EXHAUSTED,
            gate_decisions,
            tuple(missing),
            tuple(reasons),
            compiled.terminal_boundary,
            False,
        )
    if compiled.integration_required and not compiled.integration_authorized:
        return DeliveryDecision(
            DeliveryDecisionKind.INTEGRATION_NOT_AUTHORIZED,
            gate_decisions,
            tuple(missing),
            tuple(reasons),
            compiled.terminal_boundary,
            False,
        )
    if compiled.release_required and not compiled.release_authorized:
        return DeliveryDecision(
            DeliveryDecisionKind.RELEASE_NOT_AUTHORIZED,
            gate_decisions,
            tuple(missing),
            tuple(reasons),
            compiled.terminal_boundary,
            False,
        )
    if missing:
        return DeliveryDecision(
            DeliveryDecisionKind.WAITING_REQUIRED_EVIDENCE,
            gate_decisions,
            tuple(missing),
            tuple(reasons),
            compiled.terminal_boundary,
            False,
        )
    return DeliveryDecision(
        DeliveryDecisionKind.TERMINAL_ACCEPTED,
        gate_decisions,
        (),
        tuple(reasons),
        compiled.terminal_boundary,
        True,
    )


def _schema_error(document: object, schema: Mapping[str, object]) -> str | None:
    """Validate against the published schema; returns None when unavailable or valid."""
    try:
        import jsonschema
    except ModuleNotFoundError:  # pragma: no cover - schema validation is optional at runtime
        return None
    try:
        jsonschema.validate(document, schema)
    except jsonschema.ValidationError as error:
        return str(error.message)
    return None


def _run(argv: Sequence[str]) -> int:
    if len(argv) != 1:
        print("usage: python contracts/autonomous_delivery_policy.py <policy.json>", file=sys.stderr)
        return 2
    path = Path(argv[0])
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        print("input must be a JSON policy document", file=sys.stderr)
        return 2
    schema_path = Path(__file__).with_name("autonomous-delivery-policy.schema.json")
    schema: Mapping[str, object] = json.loads(schema_path.read_text(encoding="utf-8"))
    error = _schema_error(raw, schema)
    if error is not None:
        print(f"schema: {error}")
        return 1
    policy, reasons = admit_policy(raw)
    if policy is None:
        print(f"rejected: {', '.join(reasons)}")
        return 1
    print(f"admitted policy {policy.policy_id} revision {policy.revision}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return _run(list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

#!/usr/bin/env python3
"""Provider-neutral ReviewReceipt v1 composition, evaluation, and currentness (#93).

One receipt is the semantic-review evidence for exactly one candidate. The
receipt binds exact subject identity, reviewer provenance, a separately
attested independence declaration, the review policy/rubric/plan identity,
predeclared criterion outcomes, review-input coverage, the provider operation
lifecycle, and durable finding state. Provider completion is lifecycle
terminality only and never becomes semantic approval; required unknown,
missing, or failing criteria, incomplete input coverage, and unattested or
self-declared independence can never yield a policy-green review. Exact
candidate freshness is mechanical: ``review(C1)`` does not approve ``C2``,
and tree equality is never an automatic reuse exception.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

RECEIPT_FORMAT = "ai-skills-review"
RECEIPT_KIND = "review"

_MAX_REF = 2048
_MAX_REFS = 64
_MAX_IDS = 256
_MAX_CRITERIA = 64
_MAX_FINDINGS = 200
_MAX_INPUT_BYTES = 1024 * 1024

_SHA256_DIGEST = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
_SOURCE_REVISION = re.compile(r"^[0-9a-fA-F]{40}$")

_TERMINAL_BLOCKED_STATES = frozenset(
    {"blocked_quota", "blocked_billing", "blocked_auth", "provider_unavailable", "provider_failed", "cancelled"}
)
_NON_TERMINAL_STATES = frozenset({"requested", "accepted", "running", "ack_unknown"})
_FULL_ACCESS_MODES = frozenset({"connected_repo", "exact_bundle"})
_WAIVER_AUTHORITIES = frozenset({"implementer", "policy", "independent"})
_EVIDENCE_SELECTION_AUTHORITIES = frozenset({"parent", "reviewer", "implementer", "independent", "unknown"})


class ReviewerKind(StrEnum):
    HUMAN = "human"
    MODEL = "model"
    BOT = "bot"
    SERVICE = "service"


class IndependenceClass(StrEnum):
    INDEPENDENT = "independent"
    SAME_IMPLEMENTER = "same_implementer"
    SAME_EVIDENCE_PRODUCER = "same_evidence_producer"
    UNKNOWN = "unknown"


class AttestationAuthority(StrEnum):
    """Authority classes for the independence attestation, ordered by strength.

    The reviewer's own declaration never attests itself: ``self_declared``
    satisfies only a self-declared floor and can never satisfy an
    orchestrator- or independent-authority floor. Callers cannot upgrade an
    attestation by composition; only the trusted policy holder lowers floors.
    """

    NONE = "none"
    SELF_DECLARED = "self_declared"
    ORCHESTRATOR_ATTESTED = "orchestrator_attested"
    INDEPENDENT_AUTHORITY = "independent_authority"


_ATTESTATION_SUBSTITUTIONS: dict[AttestationAuthority, frozenset[AttestationAuthority]] = {
    AttestationAuthority.NONE: frozenset(AttestationAuthority),
    AttestationAuthority.SELF_DECLARED: frozenset(
        {
            AttestationAuthority.SELF_DECLARED,
            AttestationAuthority.ORCHESTRATOR_ATTESTED,
            AttestationAuthority.INDEPENDENT_AUTHORITY,
        }
    ),
    AttestationAuthority.ORCHESTRATOR_ATTESTED: frozenset(
        {AttestationAuthority.ORCHESTRATOR_ATTESTED, AttestationAuthority.INDEPENDENT_AUTHORITY}
    ),
    AttestationAuthority.INDEPENDENT_AUTHORITY: frozenset({AttestationAuthority.INDEPENDENT_AUTHORITY}),
}


def attestation_satisfies(observed: AttestationAuthority, floor: AttestationAuthority) -> bool:
    """Return whether the observed attestation authority may satisfy the declared floor."""
    return observed in _ATTESTATION_SUBSTITUTIONS[floor]


class CriterionVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class AccessMode(StrEnum):
    CONNECTED_REPO = "connected_repo"
    EXACT_BUNDLE = "exact_bundle"
    SUMMARY_ONLY = "summary_only"
    UNKNOWN = "unknown"


class CoverageState(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class ProviderState(StrEnum):
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED_WITH_REVIEW = "completed_with_review"
    COMPLETED_NO_FINDINGS = "completed_no_findings"
    BLOCKED_QUOTA = "blocked_quota"
    BLOCKED_BILLING = "blocked_billing"
    BLOCKED_AUTH = "blocked_auth"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_FAILED = "provider_failed"
    CANCELLED = "cancelled"
    ACK_UNKNOWN = "ack_unknown"


class FindingSeverity(StrEnum):
    BLOCKER = "blocker"
    MAJOR = "major"
    MINOR = "minor"
    ADVISORY = "advisory"


class FindingState(StrEnum):
    OPEN = "open"
    RESOLVED_BY_CANDIDATE = "resolved_by_candidate"
    WAIVED_BY_AUTHORITY = "waived_by_authority"
    SUPERSEDED = "superseded"
    NON_BLOCKING = "non_blocking"


class ReviewVerdict(StrEnum):
    APPROVE = "approve"
    NEEDS_FIXES = "needs_fixes"
    INCONCLUSIVE = "inconclusive"
    BLOCKED = "blocked"


# The reviewer's issued verdict can only lower the derived gate, never raise it.
_ISSUED_RANK: dict[ReviewVerdict, int] = {
    ReviewVerdict.APPROVE: 0,
    ReviewVerdict.INCONCLUSIVE: 1,
    ReviewVerdict.NEEDS_FIXES: 2,
    ReviewVerdict.BLOCKED: 3,
}


class Currentness(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class AdmissionOutcome(StrEnum):
    """Typed admission outcomes for a load-bearing review gate.

    ``NON_GREEN`` means the receipt itself is not policy-green;
    ``NOT_CURRENT`` means a demonstrably changed subject invalidated it;
    ``NOT_PROVEN`` means currentness cannot be established from the
    available identity values.
    """

    GREEN = "green"
    NON_GREEN = "non_green"
    NOT_CURRENT = "not_current"
    NOT_PROVEN = "not_proven"


def _require_bounded(value: str, name: str, max_length: int) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError(f"{name} must be a non-empty string of at most {max_length} characters")


def _optional_bounded(value: str | None, name: str, max_length: int) -> None:
    if value is not None:
        _require_bounded(value, name, max_length)


def _require_digest(value: str, name: str) -> None:
    _require_bounded(value, name, 71)
    if not _SHA256_DIGEST.match(value):
        raise ValueError(f"{name} must match sha256:<64 hex characters>")


def _optional_digest(value: str | None, name: str) -> None:
    if value is not None:
        _require_digest(value, name)


def _require_source_revision(value: str, name: str) -> None:
    _require_bounded(value, name, 40)
    if not _SOURCE_REVISION.match(value):
        raise ValueError(f"{name} must be a 40-character hex source revision")


def _optional_source_revision(value: str | None, name: str) -> None:
    if value is not None:
        _require_source_revision(value, name)


def _require_ref(value: str, name: str) -> None:
    _require_bounded(value, name, _MAX_REF)


def _parse_utc(value: str) -> datetime:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"timestamp must be a valid ISO 8601 value: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must include a timezone offset: {value!r}")
    return parsed


@dataclass(frozen=True)
class ReviewSubject:
    repository: str
    candidate_sha: str
    candidate_tree: str | None = None
    base_sha: str | None = None
    input_manifest_digest: str | None = None

    def __post_init__(self) -> None:
        _require_bounded(self.repository, "subject repository", 512)
        _require_source_revision(self.candidate_sha, "subject candidate sha")
        _optional_digest(self.candidate_tree, "subject candidate tree")
        _optional_source_revision(self.base_sha, "subject base sha")
        _optional_digest(self.input_manifest_digest, "subject input manifest digest")


@dataclass(frozen=True)
class ReviewProducer:
    reviewer_kind: ReviewerKind
    reviewer_identity: str
    provider: str | None = None
    model_or_engine: str | None = None
    configuration_revision: str | None = None
    principal: str | None = None

    def __post_init__(self) -> None:
        _require_bounded(self.reviewer_identity, "producer reviewer identity", _MAX_IDS)
        _optional_bounded(self.provider, "producer provider", _MAX_IDS)
        _optional_bounded(self.model_or_engine, "producer model or engine", _MAX_IDS)
        _optional_bounded(self.configuration_revision, "producer configuration revision", _MAX_IDS)
        _optional_bounded(self.principal, "producer principal", _MAX_IDS)


@dataclass(frozen=True)
class IndependenceAttestation:
    authority: AttestationAuthority
    evidence_ref: str | None = None

    def __post_init__(self) -> None:
        _optional_bounded(self.evidence_ref, "attestation evidence ref", _MAX_REF)


@dataclass(frozen=True)
class IndependenceDeclaration:
    declared_class: IndependenceClass
    attestation: IndependenceAttestation


@dataclass(frozen=True)
class ReviewPolicyBinding:
    policy_revision: str
    rubric_id: str | None = None
    rubric_revision: str | None = None
    rubric_digest: str | None = None
    plan_ref: str | None = None
    plan_digest: str | None = None
    required_scope: str | None = None

    def __post_init__(self) -> None:
        _require_bounded(self.policy_revision, "policy revision", _MAX_IDS)
        _optional_bounded(self.rubric_id, "rubric id", _MAX_IDS)
        _optional_bounded(self.rubric_revision, "rubric revision", _MAX_IDS)
        _optional_digest(self.rubric_digest, "rubric digest")
        _optional_bounded(self.plan_ref, "plan ref", _MAX_REF)
        _optional_digest(self.plan_digest, "plan digest")
        _optional_bounded(self.required_scope, "required scope", 512)


@dataclass(frozen=True)
class CriterionOutcome:
    id: str
    required: bool
    verdict: CriterionVerdict
    applicability_basis: str | None = None
    finding_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_bounded(self.id, "criterion id", 128)
        _optional_bounded(self.applicability_basis, "criterion applicability basis", _MAX_REF)
        if len(set(self.finding_refs)) != len(self.finding_refs) or len(self.finding_refs) > _MAX_REFS:
            raise ValueError(f"criterion {self.id} finding refs must be unique and bounded")
        for ref in self.finding_refs:
            _require_bounded(ref, "criterion finding ref", _MAX_IDS)
        if len(set(self.evidence_refs)) != len(self.evidence_refs) or len(self.evidence_refs) > _MAX_REFS:
            raise ValueError(f"criterion {self.id} evidence refs must be unique and bounded")
        for ref in self.evidence_refs:
            _require_ref(ref, "criterion evidence ref")
        if self.verdict is CriterionVerdict.NOT_APPLICABLE and not self.applicability_basis:
            raise ValueError(f"criterion {self.id} marked not_applicable requires an applicability basis")


@dataclass(frozen=True)
class ReviewCoverage:
    access_mode: AccessMode
    reviewed_through_sha: str | None
    required_context_complete: CoverageState
    changed_files: tuple[str, ...] = ()
    changed_surface_digest: str | None = None
    omitted_areas: tuple[str, ...] = ()
    evidence_selection_authority: str = "unknown"

    def __post_init__(self) -> None:
        _optional_source_revision(self.reviewed_through_sha, "coverage reviewed-through sha")
        _optional_digest(self.changed_surface_digest, "coverage changed-surface digest")
        if len(set(self.changed_files)) != len(self.changed_files) or len(self.changed_files) > 512:
            raise ValueError("coverage changed files must be unique and bounded to 512 entries")
        for path in self.changed_files:
            _require_ref(path, "coverage changed file")
        if len(set(self.omitted_areas)) != len(self.omitted_areas) or len(self.omitted_areas) > _MAX_REFS:
            raise ValueError("coverage omitted areas must be unique and bounded")
        for area in self.omitted_areas:
            _require_ref(area, "coverage omitted area")
        if self.evidence_selection_authority not in _EVIDENCE_SELECTION_AUTHORITIES:
            raise ValueError(
                f"coverage evidence-selection authority {self.evidence_selection_authority!r} is unsupported"
            )


@dataclass(frozen=True)
class ProviderOperation:
    state: ProviderState
    operation_ref: str | None = None
    submitted_at: str | None = None
    completed_at: str | None = None
    observation_coverage: CoverageState = CoverageState.UNKNOWN

    def __post_init__(self) -> None:
        _optional_bounded(self.operation_ref, "provider operation ref", 512)
        if self.submitted_at is not None:
            _parse_utc(self.submitted_at)
        if self.completed_at is not None:
            _parse_utc(self.completed_at)


@dataclass(frozen=True)
class FindingRecord:
    finding_id: str
    severity: FindingSeverity
    state: FindingState
    generation: int
    criterion_ref: str | None = None
    first_seen_generation: int | None = None
    resolved_by_revision: str | None = None
    waiver_ref: str | None = None
    waiver_authority: str | None = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_bounded(self.finding_id, "finding id", _MAX_IDS)
        _optional_bounded(self.criterion_ref, "finding criterion ref", 128)
        if not isinstance(self.generation, int) or isinstance(self.generation, bool) or self.generation < 1:
            raise ValueError("finding generation must be a positive integer")
        if self.first_seen_generation is not None and (
            not isinstance(self.first_seen_generation, int)
            or isinstance(self.first_seen_generation, bool)
            or self.first_seen_generation < 1
        ):
            raise ValueError("finding first-seen generation must be a positive integer")
        _optional_source_revision(self.resolved_by_revision, "finding resolved-by revision")
        _optional_bounded(self.waiver_ref, "finding waiver ref", _MAX_REF)
        _optional_bounded(self.waiver_authority, "finding waiver authority", 64)
        if self.waiver_authority is not None and self.waiver_authority not in _WAIVER_AUTHORITIES:
            raise ValueError(f"finding {self.finding_id} has unsupported waiver authority {self.waiver_authority!r}")
        if len(set(self.evidence_refs)) != len(self.evidence_refs) or len(self.evidence_refs) > _MAX_REFS:
            raise ValueError(f"finding {self.finding_id} evidence refs must be unique and bounded")
        for ref in self.evidence_refs:
            _require_ref(ref, "finding evidence ref")
        if self.state is FindingState.RESOLVED_BY_CANDIDATE and self.resolved_by_revision is None:
            raise ValueError(f"finding {self.finding_id} resolved_by_candidate requires resolved_by_revision")
        if self.state is FindingState.WAIVED_BY_AUTHORITY:
            if not self.waiver_ref:
                raise ValueError(f"finding {self.finding_id} waived_by_authority requires a waiver reference")
            if self.waiver_authority not in ("policy", "independent"):
                raise ValueError(f"finding {self.finding_id} requires policy or independent waiver authority")


@dataclass(frozen=True)
class FindingLedger:
    items: tuple[FindingRecord, ...]

    def __post_init__(self) -> None:
        if len(self.items) > _MAX_FINDINGS:
            raise ValueError(f"finding ledger must contain at most {_MAX_FINDINGS} items")
        seen: set[str] = set()
        for item in self.items:
            if item.finding_id in seen:
                raise ValueError(f"duplicate finding id: {item.finding_id}")
            seen.add(item.finding_id)


def finding_ledger_digest(items: Iterable[FindingRecord]) -> str:
    """Canonical digest of the complete finding ledger; the receipt never embeds transcripts."""
    body = [
        {
            "finding_id": item.finding_id,
            "criterion_ref": item.criterion_ref,
            "severity": item.severity.value,
            "state": item.state.value,
            "first_seen_generation": item.first_seen_generation,
            "generation": item.generation,
            "resolved_by_revision": item.resolved_by_revision,
            "waiver_ref": item.waiver_ref,
            "waiver_authority": item.waiver_authority,
            "evidence_refs": list(item.evidence_refs),
        }
        for item in items
    ]
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def payload_digest(document: Mapping[str, object]) -> str:
    """Recompute the structural integrity digest of a receipt body without its own digest."""
    body = {key: value for key, value in document.items() if key != "payload_digest"}
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ReviewPolicy:
    """Trusted consumer-side gate policy; floors come from the policy holder, never the receipt."""

    policy_id: str
    policy_revision: str
    required_criteria: tuple[str, ...] = ()
    required_changed_files: tuple[str, ...] = ()
    require_independence: bool = True
    minimum_independence_authority: AttestationAuthority = AttestationAuthority.ORCHESTRATOR_ATTESTED
    require_full_input: bool = True
    require_terminal_operation: bool = True
    require_review_content: bool = True
    require_resolved_findings: bool = True
    allow_required_not_applicable: bool = False
    require_plan_binding: bool = False
    expected_rubric_digest: str | None = None
    expected_plan_digest: str | None = None

    def __post_init__(self) -> None:
        _require_bounded(self.policy_id, "policy id", _MAX_IDS)
        _require_bounded(self.policy_revision, "policy revision", _MAX_IDS)
        if len(set(self.required_criteria)) != len(self.required_criteria):
            raise ValueError("required criteria must be unique")
        for criterion in self.required_criteria:
            _require_bounded(criterion, "required criterion id", 128)
        if len(set(self.required_changed_files)) != len(self.required_changed_files):
            raise ValueError("required changed files must be unique")
        for path in self.required_changed_files:
            _require_ref(path, "required changed file")
        _optional_digest(self.expected_rubric_digest, "expected rubric digest")
        _optional_digest(self.expected_plan_digest, "expected plan digest")


def policy_digest(policy: ReviewPolicy) -> str:
    body = {
        "id": policy.policy_id,
        "revision": policy.policy_revision,
        "required_criteria": list(policy.required_criteria),
        "required_changed_files": list(policy.required_changed_files),
        "require_independence": policy.require_independence,
        "minimum_independence_authority": policy.minimum_independence_authority.value,
        "require_full_input": policy.require_full_input,
        "require_terminal_operation": policy.require_terminal_operation,
        "require_review_content": policy.require_review_content,
        "require_resolved_findings": policy.require_resolved_findings,
        "allow_required_not_applicable": policy.allow_required_not_applicable,
        "require_plan_binding": policy.require_plan_binding,
        "expected_rubric_digest": policy.expected_rubric_digest,
        "expected_plan_digest": policy.expected_plan_digest,
    }
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class IndependenceAuthorityQualification:
    """Trusted-side evidence that the reviewer's independence was attested by an
    authority outside the receipt bytes.

    The receipt's own attestation fields are caller-controlled content: a
    payload digest binds that content without identifying its issuer. A
    floor above ``self_declared`` is therefore satisfiable only when the
    trusted policy holder supplies this qualification from its own boundary
    (dispatch records, provider operation logs) — a caller-constructed
    qualification is exactly as untrusted as the receipt itself and cannot
    upgrade admission. Admission binds the qualification to the receipt by
    reviewer identity, candidate SHA, attestation authority, and provider
    operation reference.
    """

    reviewer_identity: str
    authority: AttestationAuthority
    candidate_sha: str
    source_ref: str
    provider_operation_ref: str | None = None

    def __post_init__(self) -> None:
        _require_bounded(self.reviewer_identity, "qualification reviewer identity", _MAX_IDS)
        if self.authority not in (
            AttestationAuthority.ORCHESTRATOR_ATTESTED,
            AttestationAuthority.INDEPENDENT_AUTHORITY,
        ):
            raise ValueError("qualification authority must be orchestrator_attested or independent_authority")
        _require_source_revision(self.candidate_sha, "qualification candidate sha")
        _require_ref(self.source_ref, "qualification source ref")
        _optional_bounded(self.provider_operation_ref, "qualification provider operation ref", 512)


@dataclass(frozen=True)
class GateDecision:
    """Policy-derived verdict; the receipt's issued verdict is never authoritative alone."""

    verdict: ReviewVerdict
    reason_codes: tuple[str, ...]
    blocking_open: tuple[str, ...]


def evaluate_review(
    policy: ReviewPolicy,
    subject: ReviewSubject,
    producer: ReviewProducer,
    independence: IndependenceDeclaration,
    policy_binding: ReviewPolicyBinding,
    criteria: Sequence[CriterionOutcome],
    coverage: ReviewCoverage,
    provider_operation: ProviderOperation,
    findings: FindingLedger,
    issued_verdict: ReviewVerdict,
) -> GateDecision:
    """Derive the gate verdict from required criterion/finding/coverage/independence state.

    Typed reasons make every non-green outcome explicit. A definitive
    contradiction between an issued ``approve`` and the receipt's own required
    state is ``blocked``, not silently downgraded. Evidence gaps (unknown
    criteria, partial coverage, non-terminal provider operations,
    unattested independence) are ``inconclusive``. The reviewer's issued
    verdict can only lower the derived gate, never raise it: components are
    stronger evidence than the reviewer's aggregate claim.
    """
    definitive: list[str] = []
    gaps: list[str] = []

    if len(criteria) > _MAX_CRITERIA:
        raise ValueError(f"receipts must contain at most {_MAX_CRITERIA} criteria")
    by_id: dict[str, CriterionOutcome] = {}
    for criterion in criteria:
        if criterion.id in by_id:
            raise ValueError(f"duplicate criterion id: {criterion.id}")
        by_id[criterion.id] = criterion

    blocking_open: list[str] = []
    open_majors: list[str] = []
    for finding in findings.items:
        if finding.severity is FindingSeverity.BLOCKER and finding.state is FindingState.OPEN:
            blocking_open.append(finding.finding_id)
        if (
            policy.require_resolved_findings
            and finding.severity is FindingSeverity.MAJOR
            and finding.state is FindingState.OPEN
        ):
            open_majors.append(finding.finding_id)
        if (
            finding.state is FindingState.RESOLVED_BY_CANDIDATE
            and finding.resolved_by_revision != subject.candidate_sha
        ):
            definitive.append(f"finding-{finding.finding_id}-resolved-by-foreign-revision")
        if finding.state is FindingState.WAIVED_BY_AUTHORITY and finding.waiver_authority == "implementer":
            definitive.append(f"finding-{finding.finding_id}-waiver-authority-implementer")
    if open_majors:
        gaps.extend(f"unresolved-major-finding:{finding_id}" for finding_id in open_majors)

    for criterion_id in policy.required_criteria:
        outcome = by_id.get(criterion_id)
        if outcome is None:
            gaps.append(f"required-criterion-{criterion_id}-missing")
            continue
        if not outcome.required:
            definitive.append(f"required-criterion-{criterion_id}-downgraded")
        elif outcome.verdict is CriterionVerdict.FAIL:
            definitive.append(f"required-criterion-{criterion_id}-failed")
        elif outcome.verdict is CriterionVerdict.UNKNOWN:
            gaps.append(f"required-criterion-{criterion_id}-unknown")
        elif outcome.verdict is CriterionVerdict.NOT_APPLICABLE and not policy.allow_required_not_applicable:
            gaps.append(f"required-criterion-{criterion_id}-not-applicable-disallowed")

    # The policy-required list is a minimum: criteria the receipt itself declares
    # required are evaluated on their own outcomes and can never be lowered away,
    # while only the trusted policy can authorize a required NOT_APPLICABLE.
    for criterion in criteria:
        if not criterion.required or criterion.id in policy.required_criteria:
            continue
        if criterion.verdict is CriterionVerdict.FAIL:
            definitive.append(f"required-criterion-{criterion.id}-failed")
        elif criterion.verdict is CriterionVerdict.UNKNOWN:
            gaps.append(f"required-criterion-{criterion.id}-unknown")
        elif criterion.verdict is CriterionVerdict.NOT_APPLICABLE and not policy.allow_required_not_applicable:
            gaps.append(f"required-criterion-{criterion.id}-not-applicable-disallowed")

    if policy.require_full_input:
        if coverage.access_mode not in _FULL_ACCESS_MODES:
            gaps.append(f"coverage-access-mode-{coverage.access_mode.value}")
        if coverage.required_context_complete is not CoverageState.COMPLETE:
            gaps.append(f"coverage-context-{coverage.required_context_complete.value}")
        if coverage.evidence_selection_authority == "implementer":
            gaps.append("coverage-selection-authority-implementer")
        if coverage.reviewed_through_sha is None:
            gaps.append("coverage-reviewed-through-missing")
        elif coverage.reviewed_through_sha != subject.candidate_sha:
            definitive.append("coverage-reviewed-through-mismatch")
    for path in policy.required_changed_files:
        if path not in coverage.changed_files:
            gaps.append(f"coverage-changed-file-missing:{path}")

    if policy.require_terminal_operation:
        state = provider_operation.state
        if state in _NON_TERMINAL_STATES:
            gaps.append(f"provider-operation-{state.value}-non-terminal")
        elif state in _TERMINAL_BLOCKED_STATES:
            definitive.append(f"provider-operation-{state.value}")
        elif state is ProviderState.COMPLETED_NO_FINDINGS and policy.require_review_content:
            gaps.append("provider-operation-completed-no-findings-content-missing")
        if (
            state
            in (
                ProviderState.COMPLETED_WITH_REVIEW,
                ProviderState.COMPLETED_NO_FINDINGS,
            )
            and provider_operation.observation_coverage is not CoverageState.COMPLETE
        ):
            gaps.append(f"provider-observation-coverage-{provider_operation.observation_coverage.value}")

    if policy.require_independence:
        if independence.declared_class is not IndependenceClass.INDEPENDENT:
            gaps.append(f"independence-class-{independence.declared_class.value}")
        if not attestation_satisfies(independence.attestation.authority, policy.minimum_independence_authority):
            gaps.append(
                f"independence-attestation-insufficient:{independence.attestation.authority.value}"
                f"-below-{policy.minimum_independence_authority.value}"
            )
        if (
            independence.attestation.authority is not AttestationAuthority.NONE
            and independence.attestation.evidence_ref is None
        ):
            gaps.append("independence-attestation-evidence-missing")

    if policy.require_plan_binding and policy_binding.plan_digest is None:
        gaps.append("review-plan-binding-missing")
    if policy.expected_rubric_digest is not None and policy_binding.rubric_digest != policy.expected_rubric_digest:
        definitive.append("rubric-digest-mismatch")
    if policy.expected_plan_digest is not None and policy_binding.plan_digest != policy.expected_plan_digest:
        definitive.append("review-plan-digest-mismatch")

    if definitive:
        derived = ReviewVerdict.BLOCKED
        merged = tuple(sorted({*gaps, *definitive}))
    elif blocking_open:
        derived = ReviewVerdict.NEEDS_FIXES
        merged = tuple(sorted({*gaps, *(f"blocking-finding-open:{fid}" for fid in blocking_open)}))
    elif gaps:
        derived = ReviewVerdict.INCONCLUSIVE
        merged = tuple(sorted(gaps))
    else:
        derived = ReviewVerdict.APPROVE
        merged = ()
    if _ISSUED_RANK[issued_verdict] > _ISSUED_RANK[derived]:
        return GateDecision(
            issued_verdict, tuple(sorted((*merged, f"issued-verdict-{issued_verdict.value}"))), tuple(blocking_open)
        )
    return GateDecision(derived, merged, tuple(blocking_open))


@dataclass(frozen=True)
class ReviewDependencies:
    """Load-bearing subject and policy identity used for mechanical currentness."""

    repository: str
    candidate_sha: str
    policy_revision: str
    rubric_digest: str | None
    plan_digest: str | None
    input_manifest_digest: str | None
    base_sha: str | None = None

    def __post_init__(self) -> None:
        _require_bounded(self.repository, "dependency repository", 512)
        _require_source_revision(self.candidate_sha, "dependency candidate sha")
        _require_bounded(self.policy_revision, "dependency policy revision", _MAX_IDS)
        _optional_digest(self.rubric_digest, "dependency rubric digest")
        _optional_digest(self.plan_digest, "dependency plan digest")
        _optional_digest(self.input_manifest_digest, "dependency input manifest digest")
        _optional_source_revision(self.base_sha, "dependency base sha")


def dependencies_from_parts(subject: ReviewSubject, policy_binding: ReviewPolicyBinding) -> ReviewDependencies:
    return ReviewDependencies(
        repository=subject.repository,
        candidate_sha=subject.candidate_sha,
        policy_revision=policy_binding.policy_revision,
        rubric_digest=policy_binding.rubric_digest,
        plan_digest=policy_binding.plan_digest,
        input_manifest_digest=subject.input_manifest_digest,
        base_sha=subject.base_sha,
    )


def derive_currentness(receipt: ReviewDependencies, current: ReviewDependencies) -> Currentness:
    """Return STALE for changed known dependencies and UNKNOWN for missing current values.

    Every dependency field is examined before deciding: a demonstrable change
    is STALE even when another current value is unavailable, because UNKNOWN
    must never mask a known invalidation. A receipt that omits a binding its
    current counterpart supplies can never be CURRENT: the approval never
    covered that identity axis, so the receipt is stale rather than silently
    transferring across it. Candidate tree identity is not a dependency:
    equal trees never transfer an approval across commit SHAs.
    """
    if receipt.candidate_sha != current.candidate_sha or receipt.repository != current.repository:
        return Currentness.STALE
    if receipt.policy_revision != current.policy_revision:
        return Currentness.STALE
    saw_unknown = False
    for field_name in ("rubric_digest", "plan_digest", "input_manifest_digest", "base_sha"):
        prior = getattr(receipt, field_name)
        now = getattr(current, field_name)
        if prior is None:
            if now is not None:
                return Currentness.STALE
            continue
        if now is None:
            saw_unknown = True
        elif prior != now:
            return Currentness.STALE
    if saw_unknown:
        return Currentness.UNKNOWN
    return Currentness.CURRENT


@dataclass(frozen=True)
class AdmissionDecision:
    outcome: AdmissionOutcome
    gate_verdict: ReviewVerdict
    currentness: Currentness
    reason_codes: tuple[str, ...]


_BUNDLED_SCHEMA_PATH = Path(__file__).with_name("review-receipt.schema.json")


def review_admission(
    document: Mapping[str, object],
    *,
    policy: ReviewPolicy,
    current_dependencies: ReviewDependencies,
    now: datetime,
    independence_authority: IndependenceAuthorityQualification | None = None,
) -> AdmissionDecision:
    """Authoritative admission path: schema verification, gate, authority, currentness.

    The authoritative entrypoint always validates against the published
    schema; structural-only interpretation never admits a receipt. Requires
    timezone-aware ``now``. Any structural, integrity, semantic, or
    policy-verification finding yields ``NON_GREEN`` before currentness is
    even considered, so a forged or stale-but-consistent receipt can never
    become green through a currentness shortcut. When the trusted policy
    floors independence above ``self_declared``, the receipt's own attested
    declaration is necessary but never sufficient: the trusted caller must
    inject an :class:`IndependenceAuthorityQualification` from outside the
    receipt bytes or admission stays non-green.
    """
    if now.tzinfo is None:
        raise ValueError("review admission now must be timezone-aware")
    structural_findings = verify_receipt(document, schema_path=_BUNDLED_SCHEMA_PATH, policy=None)
    parts = _parts_from_document(document)
    gate: GateDecision | None = None
    if parts is not None:
        (
            receipt_subject,
            receipt_producer,
            receipt_independence,
            receipt_policy,
            criteria,
            coverage,
            operation,
            ledger,
            issued,
        ) = parts
        try:
            gate = evaluate_review(
                policy,
                receipt_subject,
                receipt_producer,
                receipt_independence,
                receipt_policy,
                criteria,
                coverage,
                operation,
                ledger,
                issued,
            )
        except ValueError:
            gate = None
    policy_findings: list[str] = []
    if not structural_findings:
        if parts is None:
            return AdmissionDecision(
                AdmissionOutcome.NON_GREEN,
                ReviewVerdict.BLOCKED,
                Currentness.UNKNOWN,
                ("receipt-re-derivation-failed",),
            )
        policy_findings = verify_receipt(document, schema_path=None, policy=policy)
    if structural_findings or policy_findings or gate is None or gate.verdict is not ReviewVerdict.APPROVE:
        gate_reasons = gate.reason_codes if gate is not None else ()
        gate_verdict = gate.verdict if gate is not None else ReviewVerdict.BLOCKED
        reasons = tuple(dict.fromkeys((*structural_findings, *policy_findings, *gate_reasons)))
        return AdmissionDecision(AdmissionOutcome.NON_GREEN, gate_verdict, Currentness.UNKNOWN, reasons)
    if document.get("verdict") != ReviewVerdict.APPROVE.value:
        return AdmissionDecision(
            AdmissionOutcome.NON_GREEN,
            gate.verdict,
            Currentness.CURRENT,
            (f"issued-verdict-{document.get('verdict')!r}-not-green",),
        )
    # Independent-authority qualification: the receipt's attested declaration is
    # caller-controlled content; a floor above self_declared requires trusted
    # evidence from outside the receipt, bound to this receipt's identities.
    if policy.require_independence and policy.minimum_independence_authority in (
        AttestationAuthority.ORCHESTRATOR_ATTESTED,
        AttestationAuthority.INDEPENDENT_AUTHORITY,
    ):
        if independence_authority is None:
            return AdmissionDecision(
                AdmissionOutcome.NON_GREEN,
                gate.verdict,
                Currentness.CURRENT,
                ("independence-authority-unqualified",),
            )
        authority_reasons: list[str] = []
        if independence_authority.reviewer_identity != receipt_producer.reviewer_identity:
            authority_reasons.append("independence-authority-reviewer-mismatch")
        if independence_authority.candidate_sha != receipt_subject.candidate_sha:
            authority_reasons.append("independence-authority-candidate-mismatch")
        if not attestation_satisfies(independence_authority.authority, policy.minimum_independence_authority):
            authority_reasons.append("independence-authority-insufficient")
        if receipt_independence.attestation.authority is AttestationAuthority.SELF_DECLARED or (
            receipt_independence.attestation.authority is AttestationAuthority.NONE
        ):
            authority_reasons.append("independence-attestation-contradicts-qualification")
        if (
            independence_authority.provider_operation_ref is not None
            and independence_authority.provider_operation_ref != operation.operation_ref
        ):
            # A qualification issued for one provider job can only back a
            # receipt that names that same job; an erased receipt reference is
            # a mismatch, not a bypass.
            authority_reasons.append("independence-authority-operation-mismatch")
        if authority_reasons:
            return AdmissionDecision(
                AdmissionOutcome.NON_GREEN, gate.verdict, Currentness.CURRENT, tuple(authority_reasons)
            )
    expires_at = document.get("expires_at")
    try:
        expired = isinstance(expires_at, str) and now >= _parse_utc(expires_at)
    except ValueError:
        return AdmissionDecision(
            AdmissionOutcome.NON_GREEN,
            gate.verdict,
            Currentness.UNKNOWN,
            ("receipt-expires-at-invalid",),
        )
    if expired:
        return AdmissionDecision(AdmissionOutcome.NOT_CURRENT, gate.verdict, Currentness.STALE, ("receipt-expired",))
    if operation.completed_at is not None and _parse_utc(operation.completed_at) > now:
        return AdmissionDecision(
            AdmissionOutcome.NON_GREEN,
            gate.verdict,
            Currentness.CURRENT,
            ("provider-completed-at-future",),
        )
    receipt_dependencies = dependencies_from_parts(receipt_subject, receipt_policy)
    currentness = derive_currentness(receipt_dependencies, current_dependencies)
    if currentness is Currentness.STALE:
        return AdmissionDecision(AdmissionOutcome.NOT_CURRENT, gate.verdict, currentness, ("subject-not-current",))
    if currentness is Currentness.UNKNOWN:
        return AdmissionDecision(
            AdmissionOutcome.NOT_PROVEN, gate.verdict, currentness, ("subject-currentness-unknown",)
        )
    return AdmissionDecision(AdmissionOutcome.GREEN, gate.verdict, currentness, ())


def compose_receipt(
    *,
    review_id: str,
    review_generation: int,
    subject: ReviewSubject,
    producer: ReviewProducer,
    independence: IndependenceDeclaration,
    policy_binding: ReviewPolicyBinding,
    criteria: Sequence[CriterionOutcome],
    coverage: ReviewCoverage,
    provider_operation: ProviderOperation,
    findings: FindingLedger,
    issued_verdict: ReviewVerdict,
    evidence_refs: Sequence[str],
    reviewed_at: str,
    expires_at: str | None = None,
    confidence: float | None = None,
) -> dict[str, object]:
    """Compose a schema-conformant receipt; composition refuses internally contradictory approvals.

    Composition is producer-side and diagnostic: it validates structure,
    bounds, and universal consistency (an issued approval with open blocking
    findings or failing required criteria is refused) but never grants
    independence or admission authority. Consumers must re-derive the gate
    under their trusted :class:`ReviewPolicy`.
    """
    _require_bounded(review_id, "review id", _MAX_IDS)
    if not isinstance(review_generation, int) or isinstance(review_generation, bool) or review_generation < 1:
        raise ValueError("review generation must be a positive integer")
    _parse_utc(reviewed_at)
    if expires_at is not None:
        _parse_utc(expires_at)
    if len(criteria) > _MAX_CRITERIA:
        raise ValueError(f"receipts must contain at most {_MAX_CRITERIA} criteria")
    if len(evidence_refs) > _MAX_REFS:
        raise ValueError(f"receipts must contain at most {_MAX_REFS} evidence references")
    for ref in evidence_refs:
        _require_ref(ref, "evidence reference")
    if confidence is not None and (not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0):
        raise ValueError("confidence must be a number between 0 and 1")
    blocking_open = [
        item.finding_id
        for item in findings.items
        if item.severity is FindingSeverity.BLOCKER and item.state is FindingState.OPEN
    ]
    required_failed = [item.id for item in criteria if item.required and item.verdict is CriterionVerdict.FAIL]
    if issued_verdict is ReviewVerdict.APPROVE and (blocking_open or required_failed):
        raise ValueError(
            "issued approve contradicts the receipt's own required state: "
            f"open blockers {blocking_open}, failed required criteria {required_failed}"
        )
    document: dict[str, object] = {
        "format": RECEIPT_FORMAT,
        "schema_version": 1,
        "receipt_kind": RECEIPT_KIND,
        "review_id": review_id,
        "review_generation": review_generation,
        "subject": {
            "repository": subject.repository,
            "candidate_sha": subject.candidate_sha,
            "candidate_tree": subject.candidate_tree,
            "base_sha": subject.base_sha,
            "input_manifest_digest": subject.input_manifest_digest,
        },
        "producer": {
            "reviewer_kind": producer.reviewer_kind.value,
            "reviewer_identity": producer.reviewer_identity,
            "provider": producer.provider,
            "model_or_engine": producer.model_or_engine,
            "configuration_revision": producer.configuration_revision,
            "principal": producer.principal,
        },
        "independence": {
            "declared_class": independence.declared_class.value,
            "attestation": {
                "authority": independence.attestation.authority.value,
                "evidence_ref": independence.attestation.evidence_ref,
            },
        },
        "policy": {
            "policy_revision": policy_binding.policy_revision,
            "rubric_id": policy_binding.rubric_id,
            "rubric_revision": policy_binding.rubric_revision,
            "rubric_digest": policy_binding.rubric_digest,
            "plan_ref": policy_binding.plan_ref,
            "plan_digest": policy_binding.plan_digest,
            "required_scope": policy_binding.required_scope,
        },
        "criteria": [
            {
                "id": item.id,
                "required": item.required,
                "verdict": item.verdict.value,
                "applicability_basis": item.applicability_basis,
                "finding_refs": list(item.finding_refs),
                "evidence_refs": list(item.evidence_refs),
            }
            for item in criteria
        ],
        "coverage": {
            "access_mode": coverage.access_mode.value,
            "reviewed_through_sha": coverage.reviewed_through_sha,
            "changed_files": list(coverage.changed_files),
            "changed_surface_digest": coverage.changed_surface_digest,
            "required_context_complete": coverage.required_context_complete.value,
            "omitted_areas": list(coverage.omitted_areas),
            "evidence_selection_authority": coverage.evidence_selection_authority,
        },
        "provider_operation": {
            "operation_ref": provider_operation.operation_ref,
            "state": provider_operation.state.value,
            "submitted_at": provider_operation.submitted_at,
            "completed_at": provider_operation.completed_at,
            "observation_coverage": provider_operation.observation_coverage.value,
        },
        "findings": {
            "ledger_digest": finding_ledger_digest(findings.items),
            "items": [
                {
                    "finding_id": item.finding_id,
                    "criterion_ref": item.criterion_ref,
                    "severity": item.severity.value,
                    "state": item.state.value,
                    "first_seen_generation": item.first_seen_generation,
                    "generation": item.generation,
                    "resolved_by_revision": item.resolved_by_revision,
                    "waiver_ref": item.waiver_ref,
                    "waiver_authority": item.waiver_authority,
                    "evidence_refs": list(item.evidence_refs),
                }
                for item in findings.items
            ],
        },
        "verdict": issued_verdict.value,
        "confidence": confidence,
        "evidence_refs": list(dict.fromkeys(evidence_refs)),
        "reviewed_at": reviewed_at,
        "expires_at": expires_at,
    }
    document["payload_digest"] = payload_digest(document)
    # Composition must never emit a document the canonical reader refuses to
    # load: the serialized size shares the reader's bounded input limit.
    serialized_size = len(json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if serialized_size > _MAX_INPUT_BYTES:
        raise ValueError(f"serialized receipt exceeds the {_MAX_INPUT_BYTES}-byte reader limit: {serialized_size}")
    integrity = verify_receipt(document, schema_path=Path(__file__).with_name("review-receipt.schema.json"))
    if integrity:
        raise ValueError(f"composed receipt failed schema or integrity verification: {'; '.join(integrity)}")
    return document


def _opt_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _parts_from_document(
    document: Mapping[str, object],
) -> (
    tuple[
        ReviewSubject,
        ReviewProducer,
        IndependenceDeclaration,
        ReviewPolicyBinding,
        tuple[CriterionOutcome, ...],
        ReviewCoverage,
        ProviderOperation,
        FindingLedger,
        ReviewVerdict,
    ]
    | None
):
    """Re-derive typed receipt parts; malformed shapes return ``None`` (fail closed)."""
    try:
        subject_block = document["subject"]
        producer_block = document["producer"]
        independence_block = document["independence"]
        policy_block = document["policy"]
        coverage_block = document["coverage"]
        operation_block = document["provider_operation"]
        findings_block = document["findings"]
        if not all(
            isinstance(block, Mapping)
            for block in (
                subject_block,
                producer_block,
                independence_block,
                policy_block,
                coverage_block,
                operation_block,
                findings_block,
            )
        ):
            return None
        assert isinstance(subject_block, Mapping)
        assert isinstance(producer_block, Mapping)
        assert isinstance(independence_block, Mapping)
        assert isinstance(policy_block, Mapping)
        assert isinstance(coverage_block, Mapping)
        assert isinstance(operation_block, Mapping)
        assert isinstance(findings_block, Mapping)
        subject = ReviewSubject(
            repository=str(subject_block["repository"]),
            candidate_sha=str(subject_block["candidate_sha"]),
            candidate_tree=_opt_str(subject_block.get("candidate_tree")),
            base_sha=_opt_str(subject_block.get("base_sha")),
            input_manifest_digest=_opt_str(subject_block.get("input_manifest_digest")),
        )
        producer = ReviewProducer(
            reviewer_kind=ReviewerKind(producer_block["reviewer_kind"]),
            reviewer_identity=str(producer_block["reviewer_identity"]),
            provider=_opt_str(producer_block.get("provider")),
            model_or_engine=_opt_str(producer_block.get("model_or_engine")),
            configuration_revision=_opt_str(producer_block.get("configuration_revision")),
            principal=_opt_str(producer_block.get("principal")),
        )
        attestation_block = independence_block.get("attestation")
        if not isinstance(attestation_block, Mapping):
            return None
        assert isinstance(attestation_block, Mapping)
        independence = IndependenceDeclaration(
            declared_class=IndependenceClass(independence_block["declared_class"]),
            attestation=IndependenceAttestation(
                authority=AttestationAuthority(attestation_block["authority"]),
                evidence_ref=_opt_str(attestation_block.get("evidence_ref")),
            ),
        )
        policy_binding = ReviewPolicyBinding(
            policy_revision=str(policy_block["policy_revision"]),
            rubric_id=_opt_str(policy_block.get("rubric_id")),
            rubric_revision=_opt_str(policy_block.get("rubric_revision")),
            rubric_digest=_opt_str(policy_block.get("rubric_digest")),
            plan_ref=_opt_str(policy_block.get("plan_ref")),
            plan_digest=_opt_str(policy_block.get("plan_digest")),
            required_scope=_opt_str(policy_block.get("required_scope")),
        )
        criteria: list[CriterionOutcome] = []
        raw_criteria = document.get("criteria")
        if not isinstance(raw_criteria, list):
            return None
        for raw in raw_criteria:
            if not isinstance(raw, Mapping):
                return None
            assert isinstance(raw, Mapping)
            verdict = CriterionVerdict(raw["verdict"])
            raw_finding_refs = raw.get("finding_refs", [])
            raw_criterion_evidence = raw.get("evidence_refs", [])
            if not isinstance(raw_finding_refs, list) or not isinstance(raw_criterion_evidence, list):
                return None
            criteria.append(
                CriterionOutcome(
                    id=str(raw["id"]),
                    required=bool(raw["required"]),
                    verdict=verdict,
                    applicability_basis=_opt_str(raw.get("applicability_basis")),
                    finding_refs=tuple(str(ref) for ref in raw_finding_refs),
                    evidence_refs=tuple(str(ref) for ref in raw_criterion_evidence),
                )
            )
        raw_changed = coverage_block.get("changed_files", [])
        raw_omitted = coverage_block.get("omitted_areas", [])
        if not isinstance(raw_changed, list) or not isinstance(raw_omitted, list):
            return None
        coverage = ReviewCoverage(
            access_mode=AccessMode(coverage_block["access_mode"]),
            reviewed_through_sha=_opt_str(coverage_block.get("reviewed_through_sha")),
            changed_files=tuple(str(path) for path in raw_changed),
            changed_surface_digest=_opt_str(coverage_block.get("changed_surface_digest")),
            required_context_complete=CoverageState(coverage_block["required_context_complete"]),
            omitted_areas=tuple(str(area) for area in raw_omitted),
            evidence_selection_authority=str(coverage_block.get("evidence_selection_authority", "unknown")),
        )
        operation = ProviderOperation(
            state=ProviderState(operation_block["state"]),
            operation_ref=_opt_str(operation_block.get("operation_ref")),
            submitted_at=_opt_str(operation_block.get("submitted_at")),
            completed_at=_opt_str(operation_block.get("completed_at")),
            observation_coverage=CoverageState(
                operation_block.get("observation_coverage", CoverageState.UNKNOWN.value)
            ),
        )
        records: list[FindingRecord] = []
        raw_items = findings_block.get("items", [])
        if not isinstance(raw_items, list):
            return None
        for raw in raw_items:
            if not isinstance(raw, Mapping):
                return None
            assert isinstance(raw, Mapping)
            generation = raw.get("generation")
            first_seen = raw.get("first_seen_generation")
            raw_evidence = raw.get("evidence_refs", [])
            if not isinstance(raw_evidence, list):
                return None
            records.append(
                FindingRecord(
                    finding_id=str(raw["finding_id"]),
                    criterion_ref=_opt_str(raw.get("criterion_ref")),
                    severity=FindingSeverity(raw["severity"]),
                    state=FindingState(raw["state"]),
                    first_seen_generation=first_seen
                    if isinstance(first_seen, int) and not isinstance(first_seen, bool)
                    else None,
                    generation=generation if isinstance(generation, int) and not isinstance(generation, bool) else 0,
                    resolved_by_revision=_opt_str(raw.get("resolved_by_revision")),
                    waiver_ref=_opt_str(raw.get("waiver_ref")),
                    waiver_authority=_opt_str(raw.get("waiver_authority")),
                    evidence_refs=tuple(str(ref) for ref in raw_evidence),
                )
            )
        ledger = FindingLedger(items=tuple(records))
        verdict_value = document["verdict"]
        if not isinstance(verdict_value, str):
            return None
        issued = ReviewVerdict(verdict_value)
    except (KeyError, ValueError, TypeError):
        return None
    return subject, producer, independence, policy_binding, tuple(criteria), coverage, operation, ledger, issued


def verify_receipt(
    document: object,
    *,
    schema_path: Path | None = None,
    policy: ReviewPolicy | None = None,
) -> list[str]:
    """Validate one receipt structurally and semantically; return bounded typed findings.

    Without a trusted policy this is structural and universal-consistency
    verification only and never constitutes admission evidence. With a
    trusted policy, the issued verdict is re-derived from the receipt's own
    state under that policy and any disagreement is a finding: the payload
    digest binds content but never authenticates the review decision.
    """
    findings: list[str] = []
    if schema_path is not None:
        from jsonschema import Draft202012Validator, FormatChecker

        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return [f"cannot load receipt schema: {exc}"]
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        findings.extend(
            f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in sorted(
                validator.iter_errors(document),
                key=lambda item: tuple(str(part) for part in item.absolute_path),
            )[:_MAX_REFS]
        )
        if len(findings) >= _MAX_REFS:
            findings.append(f"schema findings truncated at {_MAX_REFS}")
        if findings:
            return findings
    if not isinstance(document, Mapping):
        return ["receipt root must be an object"]
    schema_version = document.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != 1:
        findings.append("unsupported receipt schema version")
    if document.get("format") != RECEIPT_FORMAT:
        findings.append("unsupported receipt format")

    declared_payload = document.get("payload_digest")
    if not isinstance(declared_payload, str):
        findings.append("payload_digest missing or not a string")
    else:
        recomputed_payload = payload_digest(dict(document))
        if recomputed_payload != declared_payload:
            findings.append(f"payload_digest mismatch: declared {declared_payload}, recomputed {recomputed_payload}")

    for timestamp_field in ("reviewed_at", "expires_at"):
        timestamp_value = document.get(timestamp_field)
        if timestamp_value is not None and not isinstance(timestamp_value, str):
            findings.append(f"{timestamp_field} must be a string or null")
        elif isinstance(timestamp_value, str):
            try:
                _parse_utc(timestamp_value)
            except ValueError as exc:
                findings.append(f"{timestamp_field}: {exc}")

    parts = _parts_from_document(document)
    if parts is None:
        findings.append("receipt semantic re-derivation failed: malformed receipt shape")
        return findings
    subject, _producer, _independence, _policy_binding, criteria, coverage, operation, ledger, issued = parts

    declared_ledger_digest = document.get("findings")
    declared_ledger = (
        declared_ledger_digest.get("ledger_digest") if isinstance(declared_ledger_digest, Mapping) else None
    )
    recomputed_ledger = finding_ledger_digest(ledger.items)
    if declared_ledger != recomputed_ledger:
        findings.append(
            f"findings.ledger_digest does not match the finding items: declared {declared_ledger!r}, "
            f"recomputed {recomputed_ledger}"
        )
    for operation_field in ("submitted_at", "completed_at"):
        operation_value = getattr(operation, operation_field)
        if operation_value is not None:
            try:
                _parse_utc(operation_value)
            except ValueError as exc:
                findings.append(f"provider_operation.{operation_field}: {exc}")

    criterion_ids = [item.id for item in criteria]
    if len(set(criterion_ids)) != len(criterion_ids):
        findings.append("duplicate criterion ids present")
    finding_ids = [item.finding_id for item in ledger.items]
    if len(set(finding_ids)) != len(finding_ids):
        findings.append("duplicate finding ids present")
    declared_finding_ids = set(finding_ids)
    for criterion in criteria:
        unknown_refs = [ref for ref in criterion.finding_refs if ref not in declared_finding_ids]
        if unknown_refs:
            findings.append(f"criterion {criterion.id} references unknown findings: {', '.join(sorted(unknown_refs))}")

    for item in ledger.items:
        if item.state is FindingState.RESOLVED_BY_CANDIDATE and item.resolved_by_revision != subject.candidate_sha:
            findings.append(
                f"finding {item.finding_id} resolved_by_revision {item.resolved_by_revision!r} does not bind the "
                f"reviewed candidate {subject.candidate_sha!r}"
            )
        if item.state is FindingState.WAIVED_BY_AUTHORITY and item.waiver_authority == "implementer":
            findings.append(f"finding {item.finding_id} claims implementer waiver authority")

    if coverage.reviewed_through_sha is not None and coverage.reviewed_through_sha != subject.candidate_sha:
        findings.append(
            f"coverage.reviewed_through_sha {coverage.reviewed_through_sha!r} does not cover the reviewed candidate "
            f"{subject.candidate_sha!r}"
        )
    if coverage.omitted_areas and coverage.required_context_complete is CoverageState.COMPLETE:
        findings.append(
            "coverage declares omitted areas while claiming complete required context: "
            f"{', '.join(sorted(coverage.omitted_areas))}"
        )

    review_generation = document.get("review_generation")
    if isinstance(review_generation, int) and not isinstance(review_generation, bool):
        for item in ledger.items:
            if item.generation > review_generation:
                findings.append(
                    f"finding {item.finding_id} generation {item.generation} exceeds receipt generation "
                    f"{review_generation}"
                )

    if issued is ReviewVerdict.APPROVE:
        if operation.state in _TERMINAL_BLOCKED_STATES:
            findings.append(f"issued approve with terminal provider state {operation.state.value} is a contradiction")
        if operation.state is ProviderState.ACK_UNKNOWN:
            findings.append("issued approve with ack_unknown provider state is a contradiction")
        if operation.state is ProviderState.COMPLETED_NO_FINDINGS:
            findings.append("issued approve with completed_no_findings provider state lacks review content")
        open_blockers = [
            item.finding_id
            for item in ledger.items
            if item.severity is FindingSeverity.BLOCKER and item.state is FindingState.OPEN
        ]
        if open_blockers:
            findings.append(f"issued approve with open blocking findings: {', '.join(sorted(open_blockers))}")
        failed_required = [item.id for item in criteria if item.required and item.verdict is CriterionVerdict.FAIL]
        if failed_required:
            findings.append(f"issued approve with failing required criteria: {', '.join(sorted(failed_required))}")

    if policy is not None:
        declared_policy = document.get("policy")
        policy_revision = declared_policy.get("policy_revision") if isinstance(declared_policy, Mapping) else None
        rubric_digest = declared_policy.get("rubric_digest") if isinstance(declared_policy, Mapping) else None
        plan_digest = declared_policy.get("plan_digest") if isinstance(declared_policy, Mapping) else None
        if policy_revision != policy.policy_revision:
            findings.append(
                f"policy_revision mismatch: declared {policy_revision!r}, trusted {policy.policy_revision!r}"
            )
        if policy.expected_rubric_digest is not None and rubric_digest != policy.expected_rubric_digest:
            findings.append(
                f"rubric digest mismatch: declared {rubric_digest!r}, trusted {policy.expected_rubric_digest!r}"
            )
        if policy.expected_plan_digest is not None and plan_digest != policy.expected_plan_digest:
            findings.append(
                f"review plan digest mismatch: declared {plan_digest!r}, trusted {policy.expected_plan_digest!r}"
            )
        if policy.require_plan_binding and not isinstance(plan_digest, str):
            findings.append("trusted policy requires a review plan binding")
        try:
            gate = evaluate_review(
                policy,
                subject,
                _producer,
                _independence,
                _policy_binding,
                criteria,
                coverage,
                operation,
                ledger,
                issued,
            )
        except ValueError as exc:
            findings.append(f"verdict re-evaluation failed: {exc}")
            return findings
        if gate.verdict is not issued:
            findings.append(
                f"verdict mismatch: issued {issued.value}, trusted policy re-evaluation {gate.verdict.value} "
                f"({'; '.join(gate.reason_codes) if gate.reason_codes else 'no reasons'})"
            )
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    """Validate one receipt file: structural, integrity, and full schema verification.

    The CLI always verifies against the published schema. Structural-only
    library use (``schema_path=None``) never constitutes admission evidence;
    authoritative admission requires a trusted :class:`ReviewPolicy`.
    """
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--schema", type=Path, default=Path(__file__).with_name("review-receipt.schema.json"))
    args = parser.parse_args(argv)
    try:
        if args.receipt.stat().st_size > _MAX_INPUT_BYTES:
            print(f"ERROR: receipt exceeds {_MAX_INPUT_BYTES} bytes")
            return 1
        document = json.loads(args.receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot load receipt: {exc}")
        return 1
    findings = verify_receipt(document, schema_path=args.schema)
    for finding in findings:
        print(f"ERROR: {finding}")
    print(f"review receipt findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

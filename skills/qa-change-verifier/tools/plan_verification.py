"""Deterministic risk, acceptance, and semantic-review planning helpers."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
LAYERS = (
    "static",
    "unit",
    "integration",
    "exact_artifact",
    "real_transport",
    "external_e2e",
    "security_review",
    "post_deploy",
)
PROOF_CLASSES = (*LAYERS, "semantic_review")
OBLIGATION_KINDS = (
    "functional",
    "contract",
    "data",
    "security",
    "performance",
    "observability",
    "migration",
    "operational",
)
DEFAULT_PROOFS = {
    "functional": ("integration",),
    "contract": ("exact_artifact",),
    "data": ("integration",),
    "security": ("security_review",),
    "performance": ("external_e2e",),
    "observability": ("integration",),
    "migration": ("integration", "exact_artifact"),
    "operational": ("post_deploy",),
}
REVIEW_RISK_REASONS = frozenset(
    {
        "authority_boundary",
        "state_transition",
        "persistence_or_migration",
        "external_side_effect",
        "retry_or_idempotency",
        "concurrency",
        "security_boundary",
        "public_contract",
        "cross_component_invariant",
        "rollback_or_recovery",
        "analogue_drift",
        "diagnostic_egress",
    }
)
INVARIANT_DIMENSIONS = frozenset(
    {
        "present_valid",
        "missing",
        "explicit_null",
        "empty_container",
        "wrong_type",
        "malformed_value",
        "unknown",
        "stale",
        "conflicting_identity",
        "conflicting_generation",
        "conflicting_digest",
        "alias_or_duplicate_equal",
        "conflicting_aliases",
        "unexpected_extra_source",
        "ambiguous_fallback",
        "known_provider_wording",
        "alternate_provider_wording",
        "internal_apostrophe_or_nested_quote",
        "multiline_payload",
        "unicode_or_control_characters",
        "nested_wrapper_error",
        "very_long_error",
        "unknown_wording",
        "source_payload_embedded",
    }
)
_CHANGE_ROOT = frozenset({"schema_version", "change_id", "revision", "digest", "obligations", "criteria"})
_OBLIGATION_FIELDS = frozenset({"id", "kind", "statement", "source_ref", "required"})
_CRITERION_FIELDS = frozenset(
    {
        "id",
        "obligation_refs",
        "expected_outcome",
        "rejection_condition",
        "required",
        "proof_classes",
        "proof_of_exercise_required",
        "fixture_fidelity",
    }
)
_REVIEW_ROOT = frozenset(
    {
        "schema_version",
        "plan_id",
        "revision",
        "digest",
        "candidate_revision",
        "base_revision",
        "policy_revision",
        "acceptance_contract_digest",
        "flows",
        "focus_areas",
        "invariant_matrices",
    }
)
_REVIEW_FIELDS = {
    "flows": frozenset({"id", "entry_point", "terminal_outcome", "criterion_refs"}),
    "focus_areas": frozenset({"id", "path_refs", "risk_reasons", "criterion_refs", "invariants", "analogue_refs"}),
    "invariant_matrices": frozenset({"id", "invariant_ref", "dimensions", "criterion_refs", "analogue_refs"}),
}


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class FailureClass(StrEnum):
    NONE = "NONE"
    HARNESS_FAILURE = "HARNESS_FAILURE"
    PRODUCT_FAILURE = "PRODUCT_FAILURE"
    MIXED_FAILURE = "MIXED_FAILURE"


class EvidenceStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class AcceptanceStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCOMPLETE = "INCOMPLETE"


class FixtureSource(StrEnum):
    CAPTURED_PROVIDER = "captured_provider"
    OFFICIAL_CONTRACT = "official_contract"
    SYNTHETIC = "synthetic"


@dataclass(frozen=True)
class ChangeRisk:
    change_surface: str
    blast_radius: str
    stateful: bool = False
    security_sensitive: bool = False
    external_dependency: bool = False
    post_deploy_observable: bool = False
    simulator_revision: str | None = None
    candidate_revision: str = ""
    harness_failure: bool = False
    product_failure: bool = False


@dataclass(frozen=True)
class ExactEvidenceBinding:
    candidate_revision: str
    evidence_revision: str
    artifact_digest: str | None


@dataclass(frozen=True)
class CriterionProofPlan:
    criterion_id: str
    required: bool
    proof_classes: tuple[str, ...]


@dataclass(frozen=True)
class VerificationPlan:
    risk: RiskLevel
    required_layers: tuple[str, ...]
    simulator_valid: bool
    failure_class: FailureClass
    acceptance_contract_digest: str | None = None
    criterion_proofs: tuple[CriterionProofPlan, ...] = ()
    semantic_review_required: bool = False
    contract_findings: tuple[str, ...] = ()


@dataclass(frozen=True)
class CriterionEvidence:
    criterion_id: str
    proof_class: str
    status: EvidenceStatus
    candidate_revision: str
    contract_digest: str
    discriminating_observations: int = 1
    exercise_discriminant: str | None = None
    coverage_complete: bool = True
    deferred_count: int = 0
    fixture_source: FixtureSource | None = None


@dataclass(frozen=True)
class KnownGap:
    gap_id: str
    affected_criterion_refs: tuple[str, ...]
    load_bearing: bool | None
    disposition: str = "unresolved"
    waiver_authorized: bool = False
    waiver_ref: str | None = None
    candidate_revision: str | None = None
    contract_digest: str | None = None


@dataclass(frozen=True)
class AcceptanceAssessment:
    status: AcceptanceStatus
    findings: tuple[str, ...]
    satisfied_criteria: tuple[str, ...]
    waived_criteria: tuple[str, ...] = ()


def _strings(value: object) -> list[str] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None
    items = list(value)
    return items if all(isinstance(item, str) and item.strip() for item in items) else None


def _digest(value: Mapping[str, Any]) -> str:
    data = {key: item for key, item in value.items() if key != "digest"}
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def compute_change_contract_digest(contract: Mapping[str, Any]) -> str:
    return _digest(contract)


def compute_semantic_review_plan_digest(plan: Mapping[str, Any]) -> str:
    return _digest(plan)


def classify_failure(*, harness_failure: bool, product_failure: bool) -> FailureClass:
    if harness_failure and product_failure:
        return FailureClass.MIXED_FAILURE
    if product_failure:
        return FailureClass.PRODUCT_FAILURE
    if harness_failure:
        return FailureClass.HARNESS_FAILURE
    return FailureClass.NONE


def validate_exact_evidence(binding: ExactEvidenceBinding, *, artifact_required: bool) -> bool:
    if not binding.candidate_revision or binding.evidence_revision != binding.candidate_revision:
        return False
    if artifact_required:
        return bool(binding.artifact_digest and _DIGEST.fullmatch(binding.artifact_digest))
    return binding.artifact_digest is None or bool(_DIGEST.fullmatch(binding.artifact_digest))


def _risk(change: ChangeRisk) -> RiskLevel:
    score = (
        {"docs": 0, "internal": 1, "public_contract": 3}.get(change.change_surface, 2)
        + {"local": 0, "component": 1, "multi_component": 2, "external": 3}.get(change.blast_radius, 2)
        + int(change.stateful)
        + 2 * int(change.security_sensitive)
        + int(change.external_dependency)
        + int(change.post_deploy_observable)
    )
    if change.security_sensitive or change.change_surface == "public_contract" or score >= 6:
        return RiskLevel.HIGH
    return RiskLevel.MEDIUM if score >= 2 else RiskLevel.LOW


def _indexes(contract: Mapping[str, Any]) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    obligations = {
        str(item["id"]): item
        for item in contract.get("obligations", [])
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }
    criteria = {
        str(item["id"]): item
        for item in contract.get("criteria", [])
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }
    return obligations, criteria


def _proofs(criterion: Mapping[str, Any], obligations: Mapping[str, Mapping[str, Any]]) -> tuple[str, ...]:
    declared = _strings(criterion.get("proof_classes"))
    if declared:
        return tuple(dict.fromkeys(declared))
    result: list[str] = []
    for ref in _strings(criterion.get("obligation_refs")) or []:
        obligation = obligations.get(ref)
        if obligation:
            result.extend(DEFAULT_PROOFS.get(str(obligation.get("kind")), ()))
    return tuple(dict.fromkeys(result))


def validate_change_acceptance_contract(contract: Mapping[str, Any]) -> tuple[str, ...]:
    findings: list[str] = []
    extra = sorted(set(contract) - _CHANGE_ROOT)
    if extra:
        findings.append("unknown change-acceptance fields: " + ", ".join(extra))
    if contract.get("schema_version") != 1:
        findings.append("schema_version must be 1")
    for field in ("change_id", "revision"):
        if not isinstance(contract.get(field), str) or not str(contract[field]).strip():
            findings.append(f"{field} must be a non-empty string")
    digest = contract.get("digest")
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        findings.append("digest must be sha256:<64 lowercase hex>")
    elif digest != _digest(contract):
        findings.append("digest does not match immutable obligation/criterion semantics")
    raw_obligations, raw_criteria = contract.get("obligations"), contract.get("criteria")
    if not isinstance(raw_obligations, list):
        findings.append("obligations must be an array")
        return tuple(sorted(set(findings)))
    if not isinstance(raw_criteria, list):
        findings.append("criteria must be an array")
        return tuple(sorted(set(findings)))
    if not raw_obligations:
        findings.append("obligations must contain at least one entry")
    if not raw_criteria:
        findings.append("criteria must contain at least one entry")

    obligations: dict[str, Mapping[str, Any]] = {}
    for item in raw_obligations:
        if not isinstance(item, Mapping):
            findings.append("obligation entries must be objects")
            continue
        extra = sorted(set(item) - _OBLIGATION_FIELDS)
        if extra:
            findings.append("unknown obligation fields: " + ", ".join(extra))
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            findings.append("obligation id must be a non-empty string")
            continue
        if identifier in obligations:
            findings.append(f"duplicate obligation id: {identifier}")
            continue
        obligations[identifier] = item
        if item.get("kind") not in OBLIGATION_KINDS:
            findings.append(f"unknown obligation kind for {identifier}: {item.get('kind')!r}")
        if not isinstance(item.get("required"), bool):
            findings.append(f"obligation {identifier} required must be boolean")
        if not isinstance(item.get("statement"), str) or not str(item["statement"]).strip():
            findings.append(f"obligation {identifier} statement must be a non-empty string")

    criteria: dict[str, Mapping[str, Any]] = {}
    required_coverage: set[str] = set()
    for item in raw_criteria:
        if not isinstance(item, Mapping):
            findings.append("criterion entries must be objects")
            continue
        extra = sorted(set(item) - _CRITERION_FIELDS)
        if extra:
            findings.append("unknown criterion fields: " + ", ".join(extra))
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            findings.append("criterion id must be a non-empty string")
            continue
        if identifier in criteria:
            findings.append(f"duplicate criterion id: {identifier}")
            continue
        criteria[identifier] = item
        required = item.get("required")
        if not isinstance(required, bool):
            findings.append(f"criterion {identifier} required must be boolean")
            required = False
        refs = _strings(item.get("obligation_refs")) or []
        if not refs:
            findings.append(f"criterion {identifier} must reference at least one obligation")
        for ref in refs:
            if ref not in obligations:
                findings.append(f"criterion {identifier} references unknown obligation: {ref}")
            elif required:
                required_coverage.add(ref)
        for field in ("expected_outcome", "rejection_condition"):
            if not isinstance(item.get(field), str) or not str(item[field]).strip():
                findings.append(f"criterion {identifier} {field} must be a non-empty string")
        proofs = _proofs(item, obligations)
        unknown = sorted(set(proofs) - set(PROOF_CLASSES))
        if unknown:
            findings.append(f"criterion {identifier} has unknown proof classes: {', '.join(unknown)}")
        if required and not proofs:
            findings.append(f"required criterion {identifier} has no deterministic proof mapping")
        if item.get("fixture_fidelity", "synthetic_allowed") not in {"synthetic_allowed", "provider_faithful"}:
            findings.append(f"criterion {identifier} has invalid fixture_fidelity")
    for identifier, item in obligations.items():
        if item.get("required") is True and identifier not in required_coverage:
            findings.append(f"required obligation {identifier} has no required acceptance criterion")
    return tuple(sorted(set(findings)))


def _criterion_plans(contract: Mapping[str, Any]) -> tuple[CriterionProofPlan, ...]:
    obligations, _ = _indexes(contract)
    return tuple(
        CriterionProofPlan(str(item["id"]), item.get("required") is True, _proofs(item, obligations))
        for item in contract.get("criteria", [])
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    )


def plan_verification(change: ChangeRisk, acceptance_contract: Mapping[str, Any] | None = None) -> VerificationPlan:
    risk = _risk(change)
    layers: tuple[str, ...] = (
        LAYERS[:2] if risk is RiskLevel.LOW else LAYERS[:4] if risk is RiskLevel.MEDIUM else LAYERS
    )
    findings: tuple[str, ...] = ()
    digest: str | None = None
    criterion_plans: tuple[CriterionProofPlan, ...] = ()
    semantic_review = False
    if acceptance_contract is not None:
        findings = validate_change_acceptance_contract(acceptance_contract)
        if not findings:
            digest = str(acceptance_contract["digest"])
            criterion_plans = _criterion_plans(acceptance_contract)
            semantic_review = any(x.required and "semantic_review" in x.proof_classes for x in criterion_plans)
            added = {p for x in criterion_plans if x.required for p in x.proof_classes if p in LAYERS}
            layers = tuple(layer for layer in LAYERS if layer in set(layers) | added)
    simulator_valid = change.simulator_revision is None or (
        bool(change.candidate_revision) and change.simulator_revision == change.candidate_revision
    )
    return VerificationPlan(
        risk,
        layers,
        simulator_valid,
        classify_failure(harness_failure=change.harness_failure, product_failure=change.product_failure),
        digest,
        criterion_plans,
        semantic_review,
        findings,
    )


def validate_semantic_review_plan(
    plan: Mapping[str, Any],
    *,
    acceptance_contract: Mapping[str, Any] | None = None,
    current_candidate_revision: str | None = None,
    current_base_revision: str | None = None,
    known_path_refs: set[str] | None = None,
) -> tuple[str, ...]:
    findings: list[str] = []
    extra = sorted(set(plan) - _REVIEW_ROOT)
    if extra:
        findings.append("unknown semantic-review-plan fields: " + ", ".join(extra))
    if plan.get("schema_version") != 1:
        findings.append("schema_version must be 1")
    for field in ("plan_id", "revision", "candidate_revision"):
        if not isinstance(plan.get(field), str) or not str(plan[field]).strip():
            findings.append(f"{field} must be a non-empty string")
    digest = plan.get("digest")
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        findings.append("digest must be sha256:<64 lowercase hex>")
    elif digest != _digest(plan):
        findings.append("digest does not match semantic review plan content")
    if current_candidate_revision is not None and plan.get("candidate_revision") != current_candidate_revision:
        findings.append("semantic review plan is stale for the current candidate")
    if current_base_revision is not None and plan.get("base_revision") not in {None, current_base_revision}:
        findings.append("semantic review plan is stale for the current base")

    known: set[str] = set()
    required_review: set[str] = set()
    if acceptance_contract is not None:
        if validate_change_acceptance_contract(acceptance_contract):
            findings.append("acceptance contract is invalid")
        else:
            if plan.get("acceptance_contract_digest") != acceptance_contract.get("digest"):
                findings.append("semantic review plan is bound to a different acceptance contract")
            for item in _criterion_plans(acceptance_contract):
                known.add(item.criterion_id)
                if item.required and "semantic_review" in item.proof_classes:
                    required_review.add(item.criterion_id)

    covered: set[str] = set()
    for collection_name in ("flows", "focus_areas", "invariant_matrices"):
        collection = plan.get(collection_name, [])
        if not isinstance(collection, list):
            findings.append(f"{collection_name} must be an array")
            continue
        seen: set[str] = set()
        for item in collection:
            if not isinstance(item, Mapping):
                findings.append(f"{collection_name} entries must be objects")
                continue
            extra = sorted(set(item) - _REVIEW_FIELDS[collection_name])
            if extra:
                findings.append(f"unknown {collection_name} fields: " + ", ".join(extra))
            identifier = item.get("id")
            if not isinstance(identifier, str) or not identifier.strip():
                findings.append(f"{collection_name} id must be a non-empty string")
                continue
            if identifier in seen:
                findings.append(f"duplicate {collection_name} id: {identifier}")
            seen.add(identifier)
            refs = _strings(item.get("criterion_refs")) or []
            if not refs:
                findings.append(f"{collection_name} {identifier} must reference at least one criterion")
            covered.update(refs)
            for ref in refs:
                if known and ref not in known:
                    findings.append(f"{collection_name} {identifier} references unknown criterion: {ref}")
            if collection_name == "flows":
                entry = item.get("entry_point")
                terminal = item.get("terminal_outcome")
                invalid_flow = (
                    not isinstance(entry, str)
                    or not entry.strip()
                    or not isinstance(terminal, str)
                    or not terminal.strip()
                )
                if invalid_flow:
                    findings.append(f"flow {identifier} must identify an entry point and terminal outcome")
            elif collection_name == "focus_areas":
                risks = _strings(item.get("risk_reasons")) or []
                if not risks:
                    findings.append(f"focus area {identifier} must identify at least one risk reason")
                unknown = sorted(set(risks) - REVIEW_RISK_REASONS)
                if unknown:
                    findings.append(f"focus area {identifier} has unknown risk reasons: {', '.join(unknown)}")
                path_refs = _strings(item.get("path_refs"))
                if not (path_refs and _strings(item.get("invariants"))):
                    findings.append(f"focus area {identifier} must identify concrete paths and invariants")
                elif known_path_refs is not None:
                    unresolved = sorted(set(path_refs) - known_path_refs)
                    if unresolved:
                        findings.append(f"focus area {identifier} references unresolved paths: {', '.join(unresolved)}")
            elif collection_name == "invariant_matrices":
                dimensions = _strings(item.get("dimensions")) or []
                unknown = sorted(set(dimensions) - INVARIANT_DIMENSIONS)
                if unknown:
                    findings.append(f"invariant matrix {identifier} has unknown dimensions: {', '.join(unknown)}")
                if len(set(dimensions)) != len(dimensions):
                    findings.append(f"invariant matrix {identifier} dimensions must be unique")
                invariant_ref = item.get("invariant_ref")
                if not isinstance(invariant_ref, str) or not invariant_ref.strip():
                    findings.append(f"invariant matrix {identifier} must identify an invariant")
    missing = sorted(required_review - covered)
    if missing:
        findings.append("required semantic-review criteria lack plan coverage: " + ", ".join(missing))
    return tuple(sorted(set(findings)))


def evaluate_acceptance(
    contract: Mapping[str, Any],
    *,
    candidate_revision: str,
    evidence: Sequence[CriterionEvidence],
    known_gaps: Sequence[KnownGap] = (),
) -> AcceptanceAssessment:
    findings = list(validate_change_acceptance_contract(contract))
    if findings:
        return AcceptanceAssessment(AcceptanceStatus.INCOMPLETE, tuple(sorted(set(findings))), ())

    digest = str(contract["digest"])
    obligations, criteria = _indexes(contract)
    satisfied: set[str] = set()
    waived: set[str] = set()
    blocked: set[str] = set()
    hard_fail = False

    for gap in known_gaps:
        affected = {
            ref for ref in gap.affected_criterion_refs if ref in criteria and criteria[ref].get("required") is True
        }
        if not affected:
            continue
        if gap.disposition == "waived_by_policy":
            authorized_waiver = gap.waiver_authorized and bool(gap.waiver_ref and gap.waiver_ref.strip())
            if authorized_waiver:
                waived.update(affected)
            else:
                findings.append(f"known gap {gap.gap_id} claims policy waiver without trusted authorization/reference")
                blocked.update(affected)
        elif gap.disposition == "not_applicable":
            findings.append(f"known gap {gap.gap_id} cannot self-declare required criteria not applicable")
            blocked.update(affected)
        elif gap.disposition == "resolved":
            if gap.candidate_revision != candidate_revision or gap.contract_digest != digest:
                findings.append(f"known gap {gap.gap_id} resolution is stale for current candidate/contract")
                blocked.update(affected)
        elif gap.load_bearing is not False:
            findings.append(f"known gap {gap.gap_id} remains load-bearing or impact-unknown")
            blocked.update(affected)

    for criterion_id, criterion in criteria.items():
        if criterion.get("required") is not True or criterion_id in waived:
            continue
        required = set(_proofs(criterion, obligations))
        current = [
            item
            for item in evidence
            if item.criterion_id == criterion_id
            and item.candidate_revision == candidate_revision
            and item.contract_digest == digest
        ]
        if any(item.status is EvidenceStatus.FAIL for item in current):
            findings.append(f"required criterion {criterion_id} has current FAIL evidence")
            hard_fail = True
            continue
        passed: set[str] = set()
        for item in current:
            if item.status is not EvidenceStatus.PASS or item.proof_class not in required:
                continue
            if item.discriminating_observations <= 0:
                findings.append(f"criterion {criterion_id} has vacuous PASS with zero discriminating observations")
                continue
            if not item.coverage_complete or item.deferred_count > 0:
                findings.append(f"criterion {criterion_id} has incomplete/deferred semantic coverage")
                continue
            if criterion.get("proof_of_exercise_required") is True and not (
                item.exercise_discriminant and item.exercise_discriminant.strip()
            ):
                findings.append(f"criterion {criterion_id} lacks required proof-of-exercise discriminant")
                continue
            provider_faithful = criterion.get("fixture_fidelity") == "provider_faithful"
            valid_fixture = item.fixture_source in {FixtureSource.CAPTURED_PROVIDER, FixtureSource.OFFICIAL_CONTRACT}
            if provider_faithful and not valid_fixture:
                findings.append(f"criterion {criterion_id} lacks provider-faithful fixture evidence")
                continue
            passed.add(item.proof_class)
        missing = sorted(required - passed)
        if missing:
            findings.append(f"required criterion {criterion_id} lacks current proof: {', '.join(missing)}")
        else:
            satisfied.add(criterion_id)

    satisfied -= blocked
    waived -= blocked
    required_ids = {key for key, item in criteria.items() if item.get("required") is True}
    if hard_fail:
        status = AcceptanceStatus.FAIL
    elif findings or not required_ids.issubset(satisfied | waived):
        status = AcceptanceStatus.INCOMPLETE
    else:
        status = AcceptanceStatus.PASS
    return AcceptanceAssessment(
        status,
        tuple(sorted(set(findings))),
        tuple(sorted(satisfied)),
        tuple(sorted(waived)),
    )

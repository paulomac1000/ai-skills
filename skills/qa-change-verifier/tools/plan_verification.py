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
        "invalid",
        "missing",
        "explicit_null",
        "empty_container",
        "wrong_type",
        "malformed_value",
        "unknown",
        "stale",
        "concurrent",
        "recovery",
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
    exact_evidence_binding: ExactEvidenceBinding | None = None
    semantic_review_plan_digest: str | None = None


@dataclass(frozen=True)
class KnownGap:
    gap_id: str
    affected_criterion_refs: tuple[str, ...]
    load_bearing: bool | None
    disposition: str = "unresolved"
    candidate_revision: str | None = None
    contract_digest: str | None = None


@dataclass(frozen=True)
class KnownGapRegistrySnapshot:
    snapshot_ref: str
    candidate_revision: str
    contract_digest: str
    gaps: tuple[KnownGap, ...]
    complete: bool = True


@dataclass(frozen=True)
class PolicyWaiverAuthorization:
    waiver_ref: str
    gap_id: str
    criterion_refs: tuple[str, ...]
    candidate_revision: str
    contract_digest: str


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
    raw_contract: object = contract
    if not isinstance(raw_contract, Mapping):
        return ("acceptance contract must be an object",)

    findings: list[str] = []
    extra = sorted(set(contract) - _CHANGE_ROOT)
    if extra:
        findings.append("unknown change-acceptance fields: " + ", ".join(extra))
    schema_version = contract.get("schema_version")
    if type(schema_version) is not int or schema_version != 1:
        findings.append("schema_version must be integer 1")
    for field in ("change_id", "revision"):
        value = contract.get(field)
        if not isinstance(value, str) or not value.strip():
            findings.append(f"{field} must be a non-empty string")
        elif len(value) > 256:
            findings.append(f"{field} must be at most 256 characters")
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
        if len(identifier) > 128:
            findings.append(f"obligation id must be at most 128 characters: {identifier[:32]}...")
            continue
        if identifier in obligations:
            findings.append(f"duplicate obligation id: {identifier}")
            continue
        obligations[identifier] = item
        if item.get("kind") not in OBLIGATION_KINDS:
            findings.append(f"unknown obligation kind for {identifier}: {item.get('kind')!r}")
        if not isinstance(item.get("required"), bool):
            findings.append(f"obligation {identifier} required must be boolean")
        statement = item.get("statement")
        if not isinstance(statement, str) or not statement.strip():
            findings.append(f"obligation {identifier} statement must be a non-empty string")
        elif len(statement) > 4096:
            findings.append(f"obligation {identifier} statement must be at most 4096 characters")
        source_ref = item.get("source_ref")
        if source_ref is not None and not isinstance(source_ref, str):
            findings.append(f"obligation {identifier} source_ref must be a string or null")
        elif isinstance(source_ref, str) and len(source_ref) > 2048:
            findings.append(f"obligation {identifier} source_ref must be at most 2048 characters")

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
        if len(identifier) > 128:
            findings.append(f"criterion id must be at most 128 characters: {identifier[:32]}...")
            continue
        if identifier in criteria:
            findings.append(f"duplicate criterion id: {identifier}")
            continue
        criteria[identifier] = item
        required = item.get("required")
        if not isinstance(required, bool):
            findings.append(f"criterion {identifier} required must be boolean")
            required = False
        raw_refs = item.get("obligation_refs")
        refs = _strings(raw_refs)
        if refs is None:
            findings.append(f"criterion {identifier} obligation_refs must be an array of non-empty strings")
            refs = []
        elif not refs:
            findings.append(f"criterion {identifier} must reference at least one obligation")
        elif len(set(refs)) != len(refs):
            findings.append(f"criterion {identifier} obligation_refs must be unique")
        too_long_refs = [ref for ref in refs if len(ref) > 128]
        if too_long_refs:
            findings.append(f"criterion {identifier} obligation_refs must be at most 128 characters")
        for ref in refs:
            if ref not in obligations:
                findings.append(f"criterion {identifier} references unknown obligation: {ref}")
            elif required:
                required_coverage.add(ref)
        for field in ("expected_outcome", "rejection_condition"):
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                findings.append(f"criterion {identifier} {field} must be a non-empty string")
            elif len(value) > 4096:
                findings.append(f"criterion {identifier} {field} must be at most 4096 characters")
        declared_proofs = item.get("proof_classes")
        if "proof_classes" in item:
            parsed_proofs = _strings(declared_proofs)
            if parsed_proofs is None or not parsed_proofs:
                findings.append(f"criterion {identifier} proof_classes must be a non-empty array of strings")
            elif len(set(parsed_proofs)) != len(parsed_proofs):
                findings.append(f"criterion {identifier} proof_classes must be unique")
        proofs = _proofs(item, obligations)
        unknown = sorted(set(proofs) - set(PROOF_CLASSES))
        if unknown:
            findings.append(f"criterion {identifier} has unknown proof classes: {', '.join(unknown)}")
        if required and not proofs:
            findings.append(f"required criterion {identifier} has no deterministic proof mapping")
        proof_of_exercise = item.get("proof_of_exercise_required")
        if "proof_of_exercise_required" in item and not isinstance(proof_of_exercise, bool):
            findings.append(f"criterion {identifier} proof_of_exercise_required must be boolean")
        fixture_fidelity = item.get("fixture_fidelity", "synthetic_allowed")
        if not isinstance(fixture_fidelity, str) or fixture_fidelity not in {
            "synthetic_allowed",
            "provider_faithful",
        }:
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
    raw_plan: object = plan
    if not isinstance(raw_plan, Mapping):
        return ("semantic review plan must be an object",)

    findings: list[str] = []
    raw_known_path_refs: object = known_path_refs
    if raw_known_path_refs is not None and (
        not isinstance(raw_known_path_refs, (set, frozenset))
        or not all(isinstance(ref, str) and ref.strip() for ref in raw_known_path_refs)
    ):
        findings.append("known_path_refs must be a set of non-empty strings")
        known_path_refs = None

    extra = sorted(set(plan) - _REVIEW_ROOT)
    if extra:
        findings.append("unknown semantic-review-plan fields: " + ", ".join(extra))
    schema_version = plan.get("schema_version")
    if type(schema_version) is not int or schema_version != 1:
        findings.append("schema_version must be integer 1")
    for field in ("plan_id", "revision", "candidate_revision"):
        value = plan.get(field)
        if not isinstance(value, str) or not value.strip():
            findings.append(f"{field} must be a non-empty string")
        elif len(value) > 256:
            findings.append(f"{field} must be at most 256 characters")

    for field in ("base_revision", "policy_revision"):
        value = plan.get(field)
        if value is not None and not isinstance(value, str):
            findings.append(f"{field} must be a string or null")
        elif isinstance(value, str) and len(value) > 256:
            findings.append(f"{field} must be at most 256 characters")
    acceptance_digest = plan.get("acceptance_contract_digest")
    if acceptance_digest is not None and (
        not isinstance(acceptance_digest, str) or not _DIGEST.fullmatch(acceptance_digest)
    ):
        findings.append("acceptance_contract_digest must be null or sha256:<64 lowercase hex>")

    digest = plan.get("digest")
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        findings.append("digest must be sha256:<64 lowercase hex>")
    elif digest != _digest(plan):
        findings.append("digest does not match semantic review plan content")
    if current_candidate_revision is not None and plan.get("candidate_revision") != current_candidate_revision:
        findings.append("semantic review plan is stale for the current candidate")
    base_revision = plan.get("base_revision")
    if current_base_revision is not None and base_revision != current_base_revision:
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

    focus_covered: set[str] = set()
    for collection_name in ("flows", "focus_areas", "invariant_matrices"):
        if collection_name not in plan:
            findings.append(f"{collection_name} is required")
            continue
        collection = plan.get(collection_name)
        if not isinstance(collection, list):
            findings.append(f"{collection_name} must be an array")
            continue

        seen: set[str] = set()
        for item in collection:
            if not isinstance(item, Mapping):
                findings.append(f"{collection_name} entries must be objects")
                continue

            item_valid = True
            extra = sorted(set(item) - _REVIEW_FIELDS[collection_name])
            if extra:
                findings.append(f"unknown {collection_name} fields: " + ", ".join(extra))
                item_valid = False

            identifier = item.get("id")
            if not isinstance(identifier, str) or not identifier.strip():
                findings.append(f"{collection_name} id must be a non-empty string")
                continue
            if len(identifier) > 128:
                findings.append(f"{collection_name} id must be at most 128 characters")
                item_valid = False
            if identifier in seen:
                findings.append(f"duplicate {collection_name} id: {identifier}")
                item_valid = False
            seen.add(identifier)

            refs = _strings(item.get("criterion_refs"))
            if not refs:
                findings.append(f"{collection_name} {identifier} must reference at least one criterion")
                refs = []
                item_valid = False
            elif len(set(refs)) != len(refs):
                findings.append(f"{collection_name} {identifier} criterion_refs must be unique")
                item_valid = False
            if any(len(ref) > 128 for ref in refs):
                findings.append(f"{collection_name} {identifier} criterion_refs must be at most 128 characters")
                item_valid = False

            unknown_refs = sorted(ref for ref in refs if known and ref not in known)
            if unknown_refs:
                for ref in unknown_refs:
                    findings.append(f"{collection_name} {identifier} references unknown criterion: {ref}")
                item_valid = False

            if collection_name == "flows":
                entry = item.get("entry_point")
                terminal = item.get("terminal_outcome")
                if (
                    not isinstance(entry, str)
                    or not entry.strip()
                    or not isinstance(terminal, str)
                    or not terminal.strip()
                ):
                    findings.append(f"flow {identifier} must identify an entry point and terminal outcome")
                    item_valid = False
                else:
                    if len(entry) > 2048:
                        findings.append(f"flow {identifier} entry_point must be at most 2048 characters")
                        item_valid = False
                    if len(terminal) > 2048:
                        findings.append(f"flow {identifier} terminal_outcome must be at most 2048 characters")
                        item_valid = False

            elif collection_name == "focus_areas":
                risks = _strings(item.get("risk_reasons"))
                if not risks:
                    findings.append(f"focus area {identifier} must identify at least one risk reason")
                    risks = []
                    item_valid = False
                elif len(set(risks)) != len(risks):
                    findings.append(f"focus area {identifier} risk_reasons must be unique")
                    item_valid = False
                unknown_risks = sorted(set(risks) - REVIEW_RISK_REASONS)
                if unknown_risks:
                    findings.append(f"focus area {identifier} has unknown risk reasons: {', '.join(unknown_risks)}")
                    item_valid = False

                path_refs = _strings(item.get("path_refs"))
                invariants = _strings(item.get("invariants"))
                if not path_refs or not invariants:
                    findings.append(f"focus area {identifier} must identify concrete paths and invariants")
                    item_valid = False
                else:
                    if len(set(path_refs)) != len(path_refs):
                        findings.append(f"focus area {identifier} path_refs must be unique")
                        item_valid = False
                    if len(set(invariants)) != len(invariants):
                        findings.append(f"focus area {identifier} invariants must be unique")
                        item_valid = False
                    if any(len(ref) > 2048 for ref in path_refs):
                        findings.append(f"focus area {identifier} path_refs must be at most 2048 characters")
                        item_valid = False
                    if any(len(invariant) > 2048 for invariant in invariants):
                        findings.append(f"focus area {identifier} invariants must be at most 2048 characters")
                        item_valid = False
                    if known_path_refs is not None:
                        unresolved = sorted(set(path_refs) - known_path_refs)
                        if unresolved:
                            findings.append(
                                f"focus area {identifier} references unresolved paths: {', '.join(unresolved)}"
                            )
                            item_valid = False

                if "analogue_refs" in item:
                    analogue_refs = _strings(item.get("analogue_refs"))
                    if analogue_refs is None:
                        findings.append(f"focus area {identifier} analogue_refs must be an array of strings")
                        item_valid = False
                    else:
                        if len(set(analogue_refs)) != len(analogue_refs):
                            findings.append(f"focus area {identifier} analogue_refs must be unique")
                            item_valid = False
                        if any(len(ref) > 2048 for ref in analogue_refs):
                            findings.append(f"focus area {identifier} analogue_refs must be at most 2048 characters")
                            item_valid = False
                        if known_path_refs is not None:
                            unresolved_analogues = sorted(set(analogue_refs) - known_path_refs)
                            if unresolved_analogues:
                                findings.append(
                                    f"focus area {identifier} references unresolved analogue paths: "
                                    + ", ".join(unresolved_analogues)
                                )
                                item_valid = False

                if item_valid:
                    focus_covered.update(refs)

            elif collection_name == "invariant_matrices":
                dimensions = _strings(item.get("dimensions"))
                if not dimensions:
                    findings.append(f"invariant matrix {identifier} must identify at least one dimension")
                    dimensions = []
                    item_valid = False
                unknown_dimensions = sorted(set(dimensions) - INVARIANT_DIMENSIONS)
                if unknown_dimensions:
                    findings.append(
                        f"invariant matrix {identifier} has unknown dimensions: {', '.join(unknown_dimensions)}"
                    )
                    item_valid = False
                if len(set(dimensions)) != len(dimensions):
                    findings.append(f"invariant matrix {identifier} dimensions must be unique")
                    item_valid = False

                invariant_ref = item.get("invariant_ref")
                if not isinstance(invariant_ref, str) or not invariant_ref.strip():
                    findings.append(f"invariant matrix {identifier} must identify an invariant")
                    item_valid = False
                elif len(invariant_ref) > 2048:
                    findings.append(f"invariant matrix {identifier} invariant_ref must be at most 2048 characters")
                    item_valid = False

                if "analogue_refs" in item:
                    analogue_refs = _strings(item.get("analogue_refs"))
                    if analogue_refs is None:
                        findings.append(f"invariant matrix {identifier} analogue_refs must be an array of strings")
                        item_valid = False
                    else:
                        if len(set(analogue_refs)) != len(analogue_refs):
                            findings.append(f"invariant matrix {identifier} analogue_refs must be unique")
                            item_valid = False
                        if any(len(ref) > 2048 for ref in analogue_refs):
                            findings.append(
                                f"invariant matrix {identifier} analogue_refs must be at most 2048 characters"
                            )
                            item_valid = False
                        if known_path_refs is not None:
                            unresolved_analogues = sorted(set(analogue_refs) - known_path_refs)
                            if unresolved_analogues:
                                findings.append(
                                    f"invariant matrix {identifier} references unresolved analogue paths: "
                                    + ", ".join(unresolved_analogues)
                                )
                                item_valid = False

    missing = sorted(required_review - focus_covered)
    if missing:
        findings.append("required semantic-review criteria lack valid focus-area coverage: " + ", ".join(missing))
    return tuple(sorted(set(findings)))


def evaluate_acceptance(
    contract: Mapping[str, Any],
    *,
    candidate_revision: str,
    evidence: Sequence[CriterionEvidence],
    known_gaps: Sequence[KnownGap] = (),
    trusted_known_gap_snapshot: KnownGapRegistrySnapshot | None = None,
    trusted_policy_waivers: Sequence[PolicyWaiverAuthorization] = (),
    semantic_review_plan: Mapping[str, Any] | None = None,
    current_base_revision: str | None = None,
    known_path_refs: set[str] | None = None,
) -> AcceptanceAssessment:
    raw_contract: object = contract
    if not isinstance(raw_contract, Mapping):
        return AcceptanceAssessment(
            AcceptanceStatus.INCOMPLETE,
            ("acceptance contract must be an object",),
            (),
        )

    findings = list(validate_change_acceptance_contract(contract))
    if not isinstance(candidate_revision, str) or not candidate_revision.strip():
        findings.append("candidate_revision must be a non-empty string")
    if findings:
        return AcceptanceAssessment(AcceptanceStatus.INCOMPLETE, tuple(sorted(set(findings))), ())

    digest = str(contract["digest"])
    obligations, criteria = _indexes(contract)
    satisfied: set[str] = set()
    waived: set[str] = set()
    blocked: set[str] = set()
    hard_fail = False

    validated_evidence: list[CriterionEvidence] = []
    raw_evidence: object = evidence
    if not isinstance(raw_evidence, Sequence) or isinstance(raw_evidence, (str, bytes, bytearray)):
        findings.append("evidence must be an array of CriterionEvidence records")
    else:
        for raw_item in raw_evidence:
            if not isinstance(raw_item, CriterionEvidence):
                findings.append("evidence entries must be CriterionEvidence records")
                continue
            item = raw_item

            criterion_id: object = item.criterion_id
            if not isinstance(criterion_id, str) or not criterion_id.strip() or criterion_id not in criteria:
                findings.append("evidence criterion_id must identify a known criterion")
                continue

            proof_class: object = item.proof_class
            if not isinstance(proof_class, str) or proof_class not in PROOF_CLASSES:
                findings.append(f"evidence for {criterion_id} has invalid proof_class")
                continue

            status: object = item.status
            if not isinstance(status, EvidenceStatus):
                findings.append(f"evidence for {criterion_id} has invalid status")
                continue

            evidence_revision: object = item.candidate_revision
            if not isinstance(evidence_revision, str) or not evidence_revision.strip():
                findings.append(f"evidence for {criterion_id} candidate_revision must be a non-empty string")
                continue

            evidence_contract_digest: object = item.contract_digest
            if not isinstance(evidence_contract_digest, str) or not _DIGEST.fullmatch(evidence_contract_digest):
                findings.append(f"evidence for {criterion_id} contract_digest must be a sha256 digest")
                continue

            observations: object = item.discriminating_observations
            if type(observations) is not int:
                findings.append(f"evidence for {criterion_id} discriminating_observations must be an integer")
                continue

            exercise_discriminant: object = item.exercise_discriminant
            if exercise_discriminant is not None and not isinstance(exercise_discriminant, str):
                findings.append(f"evidence for {criterion_id} exercise_discriminant must be a string or null")
                continue

            coverage_complete: object = item.coverage_complete
            if not isinstance(coverage_complete, bool):
                findings.append(f"evidence for {criterion_id} coverage_complete must be boolean")
                continue

            deferred_count: object = item.deferred_count
            if type(deferred_count) is not int:
                findings.append(f"evidence for {criterion_id} deferred_count must be an integer")
                continue

            fixture_source: object = item.fixture_source
            if fixture_source is not None and not isinstance(fixture_source, FixtureSource):
                findings.append(f"evidence for {criterion_id} has invalid fixture_source")
                continue

            semantic_digest: object = item.semantic_review_plan_digest
            if semantic_digest is not None and (
                not isinstance(semantic_digest, str) or not _DIGEST.fullmatch(semantic_digest)
            ):
                findings.append(
                    f"evidence for {criterion_id} semantic_review_plan_digest must be null or sha256 digest"
                )
                continue

            raw_binding: object = item.exact_evidence_binding
            if raw_binding is not None:
                if not isinstance(raw_binding, ExactEvidenceBinding):
                    findings.append(f"evidence for {criterion_id} exact_evidence_binding has invalid record type")
                    continue

                binding_candidate: object = raw_binding.candidate_revision
                binding_revision: object = raw_binding.evidence_revision
                binding_digest: object = raw_binding.artifact_digest
                if not isinstance(binding_candidate, str) or not binding_candidate.strip():
                    findings.append(
                        f"evidence for {criterion_id} exact binding candidate_revision must be a non-empty string"
                    )
                    continue
                if not isinstance(binding_revision, str) or not binding_revision.strip():
                    findings.append(
                        f"evidence for {criterion_id} exact binding evidence_revision must be a non-empty string"
                    )
                    continue
                if binding_digest is not None and (
                    not isinstance(binding_digest, str) or not _DIGEST.fullmatch(binding_digest)
                ):
                    findings.append(
                        f"evidence for {criterion_id} exact binding artifact_digest must be null or sha256 digest"
                    )
                    continue

            validated_evidence.append(item)

    raw_known_path_refs: object = known_path_refs
    if raw_known_path_refs is not None:
        if not isinstance(raw_known_path_refs, (set, frozenset)) or not all(
            isinstance(ref, str) and ref.strip() for ref in raw_known_path_refs
        ):
            findings.append("known_path_refs must be a set of non-empty strings")
            known_path_refs = None

    raw_semantic_review_plan: object = semantic_review_plan
    if raw_semantic_review_plan is not None and not isinstance(raw_semantic_review_plan, Mapping):
        findings.append("semantic_review_plan must be an object or null")
        semantic_review_plan = None

    effective_gaps: tuple[KnownGap, ...] = ()
    snapshot_by_id: dict[str, KnownGap] = {}
    raw_trusted_snapshot: object = trusted_known_gap_snapshot
    if raw_trusted_snapshot is not None and not isinstance(raw_trusted_snapshot, KnownGapRegistrySnapshot):
        findings.append("trusted known-gap registry snapshot must be a KnownGapRegistrySnapshot record")
        trusted_known_gap_snapshot = None

    if trusted_known_gap_snapshot is None:
        findings.append("trusted complete known-gap registry snapshot is required")
    else:
        snapshot_identity_valid = isinstance(trusted_known_gap_snapshot.snapshot_ref, str) and bool(
            trusted_known_gap_snapshot.snapshot_ref.strip()
        )
        if not snapshot_identity_valid:
            findings.append("known-gap registry snapshot_ref must be a non-empty string")
        if trusted_known_gap_snapshot.complete is not True:
            findings.append("known-gap registry snapshot must be complete")
        if trusted_known_gap_snapshot.candidate_revision != candidate_revision:
            findings.append("known-gap registry snapshot is stale for the current candidate")
        if trusted_known_gap_snapshot.contract_digest != digest:
            findings.append("known-gap registry snapshot is bound to a different acceptance contract")

        raw_snapshot_gaps: object = trusted_known_gap_snapshot.gaps
        if not isinstance(raw_snapshot_gaps, Sequence) or isinstance(raw_snapshot_gaps, (str, bytes, bytearray)):
            findings.append("known-gap registry snapshot gaps must be an array")
        else:
            for raw_gap in raw_snapshot_gaps:
                if not isinstance(raw_gap, KnownGap):
                    findings.append("known-gap registry snapshot entries must be KnownGap records")
                    continue
                gap = raw_gap

                gap_id: object = gap.gap_id
                if not isinstance(gap_id, str) or not gap_id.strip():
                    findings.append("known gap id must be a non-empty string")
                    continue
                if gap_id in snapshot_by_id:
                    findings.append(f"duplicate known gap id in registry snapshot: {gap_id}")
                    continue

                raw_refs: object = gap.affected_criterion_refs
                refs = _strings(raw_refs)
                if refs is None:
                    findings.append(f"known gap {gap_id} affected_criterion_refs must be an array of non-empty strings")
                    continue
                if len(set(refs)) != len(refs):
                    findings.append(f"known gap {gap_id} affected_criterion_refs must be unique")
                    continue

                raw_load_bearing: object = gap.load_bearing
                if raw_load_bearing is not None and not isinstance(raw_load_bearing, bool):
                    findings.append(f"known gap {gap_id} load_bearing must be boolean or null")
                    continue

                raw_disposition: object = gap.disposition
                if not isinstance(raw_disposition, str) or raw_disposition not in {
                    "unresolved",
                    "resolved",
                    "not_applicable",
                    "waived_by_policy",
                }:
                    findings.append(f"known gap {gap_id} has invalid disposition")
                    continue

                if not refs and raw_load_bearing is not False:
                    findings.append(
                        f"known gap {gap_id} with load-bearing or unknown impact must reference at least one criterion"
                    )
                    continue

                unknown_refs = sorted(set(refs) - set(criteria))
                if unknown_refs:
                    findings.append(f"known gap {gap_id} references unknown criteria: {', '.join(unknown_refs)}")
                    continue

                raw_candidate_revision: object = gap.candidate_revision
                if raw_candidate_revision is not None and (
                    not isinstance(raw_candidate_revision, str) or not raw_candidate_revision.strip()
                ):
                    findings.append(f"known gap {gap_id} candidate_revision must be a non-empty string or null")
                    continue

                raw_contract_digest: object = gap.contract_digest
                if raw_contract_digest is not None and (
                    not isinstance(raw_contract_digest, str) or not _DIGEST.fullmatch(raw_contract_digest)
                ):
                    findings.append(f"known gap {gap_id} contract_digest must be null or sha256 digest")
                    continue

                snapshot_by_id[gap_id] = gap

            if len(snapshot_by_id) == len(raw_snapshot_gaps):
                effective_gaps = tuple(snapshot_by_id.values())

    supplied_by_id: dict[str, KnownGap] = {}
    raw_known_gaps: object = known_gaps
    supplied_items: list[object] = []
    if not isinstance(raw_known_gaps, Sequence) or isinstance(raw_known_gaps, (str, bytes, bytearray)):
        findings.append("known_gaps must be an array of KnownGap records")
    else:
        supplied_items = list(raw_known_gaps)
        for raw_gap in supplied_items:
            if not isinstance(raw_gap, KnownGap):
                findings.append("supplied known gaps must contain KnownGap records")
                continue
            supplied_gap_id: object = raw_gap.gap_id
            if not isinstance(supplied_gap_id, str) or not supplied_gap_id.strip():
                findings.append("supplied known gaps must contain identified KnownGap records")
                continue
            if supplied_gap_id in supplied_by_id:
                findings.append(f"duplicate supplied known gap id: {supplied_gap_id}")
                continue
            supplied_by_id[supplied_gap_id] = raw_gap

    if supplied_items and supplied_by_id != snapshot_by_id:
        findings.append("supplied known gaps do not match trusted registry records")

    trusted_waiver_scope: dict[str, set[str]] = {}
    validated_waivers: list[PolicyWaiverAuthorization] = []
    raw_waivers: object = trusted_policy_waivers
    if not isinstance(raw_waivers, Sequence) or isinstance(raw_waivers, (str, bytes, bytearray)):
        findings.append("trusted_policy_waivers must be an array of PolicyWaiverAuthorization records")
    else:
        for raw_authorization in raw_waivers:
            if not isinstance(raw_authorization, PolicyWaiverAuthorization):
                findings.append("trusted policy waiver entries must be PolicyWaiverAuthorization records")
                continue
            authorization = raw_authorization

            waiver_ref: object = authorization.waiver_ref
            waiver_gap_id: object = authorization.gap_id
            if not isinstance(waiver_ref, str) or not waiver_ref.strip():
                findings.append("trusted policy waiver_ref must be a non-empty string")
                continue
            if not isinstance(waiver_gap_id, str) or not waiver_gap_id.strip():
                findings.append("trusted policy gap_id must be a non-empty string")
                continue

            waiver_raw_refs: object = authorization.criterion_refs
            waiver_refs = _strings(waiver_raw_refs)
            if not waiver_refs:
                findings.append(f"trusted policy waiver {waiver_ref} must scope at least one criterion")
                continue
            if len(set(waiver_refs)) != len(waiver_refs):
                findings.append(f"trusted policy waiver {waiver_ref} criterion_refs must be unique")
                continue
            invalid_refs = sorted(
                ref for ref in waiver_refs if ref not in criteria or criteria[ref].get("required") is not True
            )
            if invalid_refs:
                findings.append(
                    f"trusted policy waiver {waiver_ref} references non-required or unknown criteria: "
                    + ", ".join(invalid_refs)
                )
                continue

            waiver_candidate: object = authorization.candidate_revision
            waiver_digest: object = authorization.contract_digest
            if not isinstance(waiver_candidate, str) or not waiver_candidate.strip():
                findings.append(f"trusted policy waiver {waiver_ref} candidate_revision must be a non-empty string")
                continue
            if not isinstance(waiver_digest, str) or not _DIGEST.fullmatch(waiver_digest):
                findings.append(f"trusted policy waiver {waiver_ref} contract_digest must be a sha256 digest")
                continue

            validated_waivers.append(authorization)

    for authorization in validated_waivers:
        if authorization.candidate_revision != candidate_revision or authorization.contract_digest != digest:
            continue
        trusted_waiver_scope.setdefault(authorization.gap_id, set()).update(authorization.criterion_refs)

    for gap in effective_gaps:
        affected = {
            ref for ref in gap.affected_criterion_refs if ref in criteria and criteria[ref].get("required") is True
        }
        if not affected:
            continue
        if gap.disposition == "waived_by_policy":
            authorized = affected & trusted_waiver_scope.get(gap.gap_id, set())
            waived.update(authorized)
            unauthorized = affected - authorized
            if unauthorized:
                findings.append(
                    f"known gap {gap.gap_id} lacks matching trusted policy authorization for: "
                    + ", ".join(sorted(unauthorized))
                )
                blocked.update(unauthorized)
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

    semantic_review_plan_digest: str | None = None
    semantic_review_required = any(
        criterion.get("required") is True
        and criterion_id not in waived
        and "semantic_review" in _proofs(criterion, obligations)
        for criterion_id, criterion in criteria.items()
    )
    if semantic_review_required:
        if semantic_review_plan is None:
            findings.append("required semantic-review proof lacks a validated semantic review plan")
        elif semantic_review_plan.get("base_revision") is not None and (
            not isinstance(current_base_revision, str) or not current_base_revision.strip()
        ):
            findings.append("base-bound semantic review plan requires the current base revision")
        else:
            plan_findings = validate_semantic_review_plan(
                semantic_review_plan,
                acceptance_contract=contract,
                current_candidate_revision=candidate_revision,
                current_base_revision=current_base_revision,
                known_path_refs=known_path_refs,
            )
            if plan_findings:
                findings.extend(f"semantic review plan invalid: {finding}" for finding in plan_findings)
            else:
                semantic_review_plan_digest = str(semantic_review_plan["digest"])

    for criterion_id, criterion in criteria.items():
        if criterion.get("required") is not True or criterion_id in waived:
            continue
        required = set(_proofs(criterion, obligations))
        current = [
            item
            for item in validated_evidence
            if item.criterion_id == criterion_id
            and item.candidate_revision == candidate_revision
            and item.contract_digest == digest
        ]
        authoritative_fail = False
        for item in current:
            if item.status is not EvidenceStatus.FAIL:
                continue
            if item.proof_class not in required:
                findings.append(
                    f"criterion {criterion_id} FAIL evidence uses non-required proof class: {item.proof_class}"
                )
                continue

            if criterion.get("proof_of_exercise_required") is True:
                if item.discriminating_observations <= 0:
                    findings.append(
                        f"criterion {criterion_id} FAIL lacks discriminating proof-of-exercise observations"
                    )
                    continue
                valid_fail_discriminant = isinstance(item.exercise_discriminant, str) and bool(
                    item.exercise_discriminant.strip()
                )
                if not valid_fail_discriminant:
                    findings.append(f"criterion {criterion_id} FAIL lacks required proof-of-exercise discriminant")
                    continue

            if criterion.get("fixture_fidelity") == "provider_faithful" and item.fixture_source not in {
                FixtureSource.CAPTURED_PROVIDER,
                FixtureSource.OFFICIAL_CONTRACT,
            }:
                findings.append(f"criterion {criterion_id} provider-faithful FAIL lacks provider-faithful fixture evidence")
                continue

            if item.proof_class == "exact_artifact":
                binding = item.exact_evidence_binding
                if (
                    binding is None
                    or binding.candidate_revision != candidate_revision
                    or not validate_exact_evidence(binding, artifact_required=True)
                ):
                    findings.append(f"criterion {criterion_id} exact-artifact FAIL lacks valid exact evidence binding")
                    continue

            if item.proof_class == "semantic_review":
                if (
                    semantic_review_plan_digest is None
                    or item.semantic_review_plan_digest != semantic_review_plan_digest
                ):
                    findings.append(
                        f"criterion {criterion_id} semantic-review FAIL is not bound to the current validated plan"
                    )
                    continue

            findings.append(f"required criterion {criterion_id} has current FAIL evidence")
            hard_fail = True
            authoritative_fail = True
            break

        if authoritative_fail:
            continue

        passed: set[str] = set()
        provider_fixture_seen = False
        for item in current:
            if item.status is not EvidenceStatus.PASS or item.proof_class not in required:
                continue
            if item.discriminating_observations <= 0:
                findings.append(f"criterion {criterion_id} has vacuous PASS with zero discriminating observations")
                continue
            if item.coverage_complete is not True or item.deferred_count != 0:
                findings.append(f"criterion {criterion_id} has incomplete/deferred semantic coverage")
                continue
            valid_discriminant = isinstance(item.exercise_discriminant, str) and bool(
                item.exercise_discriminant.strip()
            )
            if criterion.get("proof_of_exercise_required") is True and not valid_discriminant:
                findings.append(f"criterion {criterion_id} lacks required proof-of-exercise discriminant")
                continue

            if item.proof_class == "exact_artifact":
                binding = item.exact_evidence_binding
                if (
                    binding is None
                    or binding.candidate_revision != candidate_revision
                    or not validate_exact_evidence(binding, artifact_required=True)
                ):
                    findings.append(f"criterion {criterion_id} exact-artifact proof lacks valid exact evidence binding")
                    continue

            if item.proof_class == "semantic_review":
                if semantic_review_plan_digest is None:
                    continue
                if item.semantic_review_plan_digest != semantic_review_plan_digest:
                    findings.append(
                        f"criterion {criterion_id} semantic-review proof is not bound to the current validated plan"
                    )
                    continue

            passed.add(item.proof_class)
            if item.fixture_source in {FixtureSource.CAPTURED_PROVIDER, FixtureSource.OFFICIAL_CONTRACT}:
                provider_fixture_seen = True

        if criterion.get("fixture_fidelity") == "provider_faithful" and not provider_fixture_seen:
            findings.append(f"criterion {criterion_id} lacks provider-faithful fixture evidence")

        missing = sorted(required - passed)
        if missing:
            findings.append(f"required criterion {criterion_id} lacks current proof: {', '.join(missing)}")
        elif criterion.get("fixture_fidelity") != "provider_faithful" or provider_fixture_seen:
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

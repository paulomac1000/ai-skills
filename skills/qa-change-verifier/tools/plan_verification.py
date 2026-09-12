"""Deterministic risk-based verification planning and exact-evidence checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class FailureClass(StrEnum):
    NONE = "NONE"
    HARNESS_FAILURE = "HARNESS_FAILURE"
    PRODUCT_FAILURE = "PRODUCT_FAILURE"
    MIXED_FAILURE = "MIXED_FAILURE"


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
class VerificationPlan:
    risk: RiskLevel
    required_layers: tuple[str, ...]
    simulator_valid: bool
    failure_class: FailureClass


def _risk_level(change: ChangeRisk) -> RiskLevel:
    surface_weight = {"docs": 0, "internal": 1, "public_contract": 3}.get(change.change_surface, 2)
    blast_weight = {"local": 0, "component": 1, "multi_component": 2, "external": 3}.get(change.blast_radius, 2)
    score = (
        surface_weight
        + blast_weight
        + int(change.stateful)
        + 2 * int(change.security_sensitive)
        + int(change.external_dependency)
        + int(change.post_deploy_observable)
    )
    if change.security_sensitive or change.change_surface == "public_contract" or score >= 6:
        return RiskLevel.HIGH
    if score >= 2:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def classify_failure(*, harness_failure: bool, product_failure: bool) -> FailureClass:
    if harness_failure and product_failure:
        return FailureClass.MIXED_FAILURE
    if product_failure:
        return FailureClass.PRODUCT_FAILURE
    if harness_failure:
        return FailureClass.HARNESS_FAILURE
    return FailureClass.NONE


def validate_exact_evidence(binding: ExactEvidenceBinding, *, artifact_required: bool) -> bool:
    """Exact evidence is valid only for the candidate revision and required artifact digest."""
    if not binding.candidate_revision or binding.evidence_revision != binding.candidate_revision:
        return False
    if artifact_required:
        return bool(binding.artifact_digest and _DIGEST.fullmatch(binding.artifact_digest))
    return binding.artifact_digest is None or bool(_DIGEST.fullmatch(binding.artifact_digest))


def plan_verification(change: ChangeRisk) -> VerificationPlan:
    """Return deterministic low/medium/high verification layers for one change."""
    risk = _risk_level(change)
    layers: tuple[str, ...]
    if risk is RiskLevel.LOW:
        layers = LAYERS[:2]
    elif risk is RiskLevel.MEDIUM:
        layers = LAYERS[:4]
    else:
        layers = LAYERS
    simulator_valid = (
        change.simulator_revision is None
        or bool(change.candidate_revision)
        and change.simulator_revision == change.candidate_revision
    )
    return VerificationPlan(
        risk=risk,
        required_layers=layers,
        simulator_valid=simulator_valid,
        failure_class=classify_failure(
            harness_failure=change.harness_failure,
            product_failure=change.product_failure,
        ),
    )

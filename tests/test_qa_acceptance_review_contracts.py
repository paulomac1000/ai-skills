"""Acceptance-contract and semantic-review planning regressions for qa-change-verifier."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/qa-change-verifier"
TOOL = SKILL / "tools/plan_verification.py"
CHANGE_SCHEMA = ROOT / "contracts/change-acceptance.schema.json"
REVIEW_SCHEMA = ROOT / "contracts/semantic-review-plan.schema.json"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _contract(module: ModuleType) -> dict[str, object]:
    contract: dict[str, object] = {
        "schema_version": 1,
        "change_id": "change-42",
        "revision": "r1",
        "obligations": [
            {"id": "O1", "kind": "functional", "statement": "preserve behavior", "required": True},
            {"id": "O2", "kind": "security", "statement": "protect diagnostics", "required": True},
            {"id": "O3", "kind": "observability", "statement": "keep optional telemetry", "required": False},
        ],
        "criteria": [
            {
                "id": "C1",
                "obligation_refs": ["O1"],
                "expected_outcome": "state changes once",
                "rejection_condition": "state is duplicated",
                "required": True,
                "proof_classes": ["integration"],
                "proof_of_exercise_required": True,
            },
            {
                "id": "C2",
                "obligation_refs": ["O2"],
                "expected_outcome": "unsafe input is never emitted",
                "rejection_condition": "source payload reaches diagnostics",
                "required": True,
                "proof_classes": ["security_review", "semantic_review"],
                "fixture_fidelity": "provider_faithful",
            },
            {
                "id": "C3",
                "obligation_refs": ["O3"],
                "expected_outcome": "telemetry remains useful",
                "rejection_condition": "telemetry is absent",
                "required": False,
                "proof_classes": ["integration"],
            },
        ],
    }
    contract["digest"] = module.compute_change_contract_digest(contract)
    return contract


def _review_plan(module: ModuleType, contract: dict[str, object]) -> dict[str, object]:
    plan: dict[str, object] = {
        "schema_version": 1,
        "plan_id": "review-42",
        "revision": "r1",
        "candidate_revision": "candidate-1",
        "base_revision": "base-1",
        "acceptance_contract_digest": contract["digest"],
        "flows": [
            {
                "id": "F1",
                "entry_point": "validator input",
                "terminal_outcome": "bounded diagnostic",
                "criterion_refs": ["C2"],
            }
        ],
        "focus_areas": [
            {
                "id": "R1",
                "path_refs": ["src/diagnostics.py"],
                "risk_reasons": ["diagnostic_egress", "security_boundary"],
                "criterion_refs": ["C2"],
                "invariants": ["raw source payload never reaches protected sinks"],
                "analogue_refs": ["src/provider_errors.py"],
            }
        ],
        "invariant_matrices": [
            {
                "id": "M1",
                "invariant_ref": "diagnostic-egress",
                "dimensions": [
                    "known_provider_wording",
                    "alternate_provider_wording",
                    "internal_apostrophe_or_nested_quote",
                    "unknown_wording",
                    "source_payload_embedded",
                ],
                "criterion_refs": ["C2"],
            }
        ],
    }
    plan["digest"] = module.compute_semantic_review_plan_digest(plan)
    return plan


def test_change_acceptance_contract_has_stable_semantic_digest_and_no_mutable_state() -> None:
    module = _load("qa_contract_digest", TOOL)
    contract = _contract(module)
    assert module.validate_change_acceptance_contract(contract) == ()
    changed = json.loads(json.dumps(contract))
    changed["criteria"][0]["expected_outcome"] = "different behavior"
    assert module.compute_change_contract_digest(changed) != contract["digest"]

    reordered = {key: contract[key] for key in reversed(contract)}
    assert module.compute_change_contract_digest(reordered) == contract["digest"]
    schema = json.loads(CHANGE_SCHEMA.read_text(encoding="utf-8"))
    criterion_properties = schema["properties"]["criteria"]["items"]["properties"]
    assert "status" not in criterion_properties
    assert schema["additionalProperties"] is False


def test_required_obligation_and_malformed_references_fail_closed() -> None:
    module = _load("qa_contract_refs", TOOL)
    contract = _contract(module)
    contract["criteria"] = [contract["criteria"][2]]
    contract["digest"] = module.compute_change_contract_digest(contract)
    findings = module.validate_change_acceptance_contract(contract)
    assert "required obligation O1 has no required acceptance criterion" in findings
    assert "required obligation O2 has no required acceptance criterion" in findings

    contract = _contract(module)
    contract["criteria"][0]["obligation_refs"] = ["missing"]
    contract["digest"] = module.compute_change_contract_digest(contract)
    assert "criterion C1 references unknown obligation: missing" in module.validate_change_acceptance_contract(contract)

    empty = {
        "schema_version": 1,
        "change_id": "empty",
        "revision": "r1",
        "obligations": [],
        "criteria": [],
    }
    empty["digest"] = module.compute_change_contract_digest(empty)
    empty_findings = module.validate_change_acceptance_contract(empty)
    assert "obligations must contain at least one entry" in empty_findings
    assert "criteria must contain at least one entry" in empty_findings

    duplicate = _contract(module)
    duplicate["obligations"].append(dict(duplicate["obligations"][0]))
    duplicate["criteria"].append(dict(duplicate["criteria"][0]))
    duplicate["digest"] = module.compute_change_contract_digest(duplicate)
    duplicate_findings = module.validate_change_acceptance_contract(duplicate)
    assert "duplicate obligation id: O1" in duplicate_findings
    assert "duplicate criterion id: C1" in duplicate_findings

    malformed = _contract(module)
    malformed["criteria"][0]["proof_classes"] = "integration"
    malformed["criteria"][0]["proof_of_exercise_required"] = "yes"
    malformed["digest"] = module.compute_change_contract_digest(malformed)
    malformed_findings = module.validate_change_acceptance_contract(malformed)
    assert "criterion C1 proof_classes must be a non-empty array of strings" in malformed_findings
    assert "criterion C1 proof_of_exercise_required must be boolean" in malformed_findings


def test_risk_only_planning_is_backward_compatible_and_criteria_add_specific_proofs() -> None:
    module = _load("qa_contract_plan", TOOL)
    change = module.ChangeRisk(change_surface="docs", blast_radius="local", candidate_revision="candidate-1")
    risk_only = module.plan_verification(change)
    assert risk_only.required_layers == ("static", "unit")
    assert risk_only.acceptance_contract_digest is None

    contract = _contract(module)
    planned = module.plan_verification(change, contract)
    assert planned.required_layers == ("static", "unit", "integration", "security_review")
    assert planned.semantic_review_required is True
    assert {item.criterion_id: item.proof_classes for item in planned.criterion_proofs} == {
        "C1": ("integration",),
        "C2": ("security_review", "semantic_review"),
        "C3": ("integration",),
    }


def test_acceptance_is_incomplete_when_one_required_criterion_is_uncovered_or_stale() -> None:
    module = _load("qa_contract_missing", TOOL)
    contract = _contract(module)
    evidence = [
        module.CriterionEvidence(
            "C1",
            "integration",
            module.EvidenceStatus.PASS,
            "candidate-1",
            contract["digest"],
            exercise_discriminant="guard-hit",
        )
    ]
    assessment = module.evaluate_acceptance(contract, candidate_revision="candidate-1", evidence=evidence)
    assert assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert any("required criterion C2 lacks current proof" in finding for finding in assessment.findings)

    stale = [
        module.CriterionEvidence(
            "C1",
            "integration",
            module.EvidenceStatus.PASS,
            "candidate-0",
            contract["digest"],
            exercise_discriminant="guard-hit",
        )
    ]
    assessment = module.evaluate_acceptance(contract, candidate_revision="candidate-1", evidence=stale)
    assert assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert "C1" not in assessment.satisfied_criteria

    previous_digest = contract["digest"]
    changed = json.loads(json.dumps(contract))
    changed["criteria"][0]["expected_outcome"] = "changed admitted behavior"
    changed["digest"] = module.compute_change_contract_digest(changed)
    old_contract_evidence = [
        module.CriterionEvidence(
            "C1",
            "integration",
            module.EvidenceStatus.PASS,
            "candidate-1",
            previous_digest,
            exercise_discriminant="guard-hit",
        )
    ]
    changed_assessment = module.evaluate_acceptance(
        changed, candidate_revision="candidate-1", evidence=old_contract_evidence
    )
    assert changed_assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert "C1" not in changed_assessment.satisfied_criteria


def test_vacuous_deferred_wrong_fixture_and_missing_exercise_are_non_green() -> None:
    module = _load("qa_contract_integrity", TOOL)
    contract = _contract(module)
    digest = contract["digest"]
    plan = _review_plan(module, contract)
    evidence = [
        module.CriterionEvidence(
            "C1", "integration", module.EvidenceStatus.PASS, "candidate-1", digest, discriminating_observations=0
        ),
        module.CriterionEvidence(
            "C2",
            "security_review",
            module.EvidenceStatus.PASS,
            "candidate-1",
            digest,
            coverage_complete=False,
            deferred_count=1,
            fixture_source=module.FixtureSource.SYNTHETIC,
        ),
        module.CriterionEvidence(
            "C2",
            "semantic_review",
            module.EvidenceStatus.PASS,
            "candidate-1",
            digest,
            fixture_source=module.FixtureSource.SYNTHETIC,
            semantic_review_plan_digest=plan["digest"],
        ),
    ]
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        semantic_review_plan=plan,
        current_base_revision="base-1",
    )
    assert assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert any("vacuous PASS" in finding for finding in assessment.findings)
    assert any("incomplete/deferred semantic coverage" in finding for finding in assessment.findings)
    assert any("provider-faithful" in finding for finding in assessment.findings)

    evidence[0] = module.CriterionEvidence(
        "C1", "integration", module.EvidenceStatus.PASS, "candidate-1", digest, exercise_discriminant=None
    )
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        semantic_review_plan=plan,
        current_base_revision="base-1",
    )
    assert any("proof-of-exercise" in finding for finding in assessment.findings)

    evidence[0] = module.CriterionEvidence(
        "C1",
        "integration",
        module.EvidenceStatus.PASS,
        "candidate-1",
        digest,
        exercise_discriminant="guard-hit",
        deferred_count=-1,
    )
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        semantic_review_plan=plan,
        current_base_revision="base-1",
    )
    assert any("incomplete/deferred semantic coverage" in finding for finding in assessment.findings)


def test_current_complete_evidence_passes_but_known_gap_cannot_self_waive() -> None:
    module = _load("qa_contract_gap", TOOL)
    contract = _contract(module)
    digest = contract["digest"]
    plan = _review_plan(module, contract)
    evidence = [
        module.CriterionEvidence(
            "C1",
            "integration",
            module.EvidenceStatus.PASS,
            "candidate-1",
            digest,
            exercise_discriminant="guard-hit",
        ),
        module.CriterionEvidence(
            "C2",
            "security_review",
            module.EvidenceStatus.PASS,
            "candidate-1",
            digest,
            fixture_source=module.FixtureSource.CAPTURED_PROVIDER,
        ),
        module.CriterionEvidence(
            "C2",
            "semantic_review",
            module.EvidenceStatus.PASS,
            "candidate-1",
            digest,
            fixture_source=module.FixtureSource.OFFICIAL_CONTRACT,
            semantic_review_plan_digest=plan["digest"],
        ),
    ]
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        semantic_review_plan=plan,
        current_base_revision="base-1",
    )
    assert assessment.status == module.AcceptanceStatus.PASS

    reported_waiver = module.KnownGap(
        "G1", ("C1",), True, disposition="waived_by_policy"
    )
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        known_gaps=[reported_waiver],
        semantic_review_plan=plan,
        current_base_revision="base-1",
    )
    assert assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert any(
        "lacks matching trusted policy authorization" in finding
        for finding in assessment.findings
    )

    stale_authorization = module.PolicyWaiverAuthorization(
        waiver_ref="policy-waiver:G1",
        gap_id="G1",
        criterion_refs=("C1",),
        candidate_revision="candidate-0",
        contract_digest=digest,
    )
    assert module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        known_gaps=[reported_waiver],
        trusted_policy_waivers=[stale_authorization],
        semantic_review_plan=plan,
        current_base_revision="base-1",
    ).status == module.AcceptanceStatus.INCOMPLETE

    wrong_scope = module.PolicyWaiverAuthorization(
        waiver_ref="policy-waiver:G1",
        gap_id="G1",
        criterion_refs=("C2",),
        candidate_revision="candidate-1",
        contract_digest=digest,
    )
    assert module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        known_gaps=[reported_waiver],
        trusted_policy_waivers=[wrong_scope],
        semantic_review_plan=plan,
        current_base_revision="base-1",
    ).status == module.AcceptanceStatus.INCOMPLETE

    authorized = module.PolicyWaiverAuthorization(
        waiver_ref="policy-waiver:G1",
        gap_id="G1",
        criterion_refs=("C1",),
        candidate_revision="candidate-1",
        contract_digest=digest,
    )
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        known_gaps=[reported_waiver],
        trusted_policy_waivers=[authorized],
        semantic_review_plan=plan,
        current_base_revision="base-1",
    )
    assert assessment.status == module.AcceptanceStatus.PASS
    assert assessment.waived_criteria == ("C1",)


def test_resolved_gap_must_be_current_but_current_resolution_does_not_block() -> None:
    module = _load("qa_contract_resolved_gap", TOOL)
    contract = _contract(module)
    digest = contract["digest"]
    plan = _review_plan(module, contract)
    evidence = [
        module.CriterionEvidence(
            "C1",
            "integration",
            module.EvidenceStatus.PASS,
            "candidate-1",
            digest,
            exercise_discriminant="guard-hit",
        ),
        module.CriterionEvidence(
            "C2",
            "security_review",
            module.EvidenceStatus.PASS,
            "candidate-1",
            digest,
            fixture_source=module.FixtureSource.CAPTURED_PROVIDER,
        ),
        module.CriterionEvidence(
            "C2",
            "semantic_review",
            module.EvidenceStatus.PASS,
            "candidate-1",
            digest,
            fixture_source=module.FixtureSource.CAPTURED_PROVIDER,
            semantic_review_plan_digest=plan["digest"],
        ),
    ]
    current = module.KnownGap(
        "G1",
        ("C1",),
        True,
        disposition="resolved",
        candidate_revision="candidate-1",
        contract_digest=digest,
    )
    current_assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        known_gaps=[current],
        semantic_review_plan=plan,
        current_base_revision="base-1",
    )
    assert current_assessment.status == module.AcceptanceStatus.PASS
    stale = module.KnownGap(
        "G1",
        ("C1",),
        True,
        disposition="resolved",
        candidate_revision="candidate-0",
        contract_digest=digest,
    )
    stale_assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        known_gaps=[stale],
        semantic_review_plan=plan,
        current_base_revision="base-1",
    )
    assert stale_assessment.status == module.AcceptanceStatus.INCOMPLETE


def test_semantic_review_plan_is_exact_candidate_bound_and_covers_required_review_criteria() -> None:
    module = _load("qa_review_plan", TOOL)
    contract = _contract(module)
    plan = _review_plan(module, contract)
    assert module.validate_semantic_review_plan(
        plan,
        acceptance_contract=contract,
        current_candidate_revision="candidate-1",
        current_base_revision="base-1",
    ) == ()
    stale_findings = module.validate_semantic_review_plan(
        plan, acceptance_contract=contract, current_candidate_revision="candidate-2"
    )
    assert "semantic review plan is stale for the current candidate" in stale_findings
    stale_base = module.validate_semantic_review_plan(
        plan, acceptance_contract=contract, current_base_revision="base-2"
    )
    assert "semantic review plan is stale for the current base" in stale_base

    plan = _review_plan(module, contract)
    plan["focus_areas"] = []
    plan["invariant_matrices"] = []
    plan["digest"] = module.compute_semantic_review_plan_digest(plan)
    findings = module.validate_semantic_review_plan(plan, acceptance_contract=contract)
    assert "required semantic-review criteria lack valid focus-area coverage: C2" in findings

    unresolved = module.validate_semantic_review_plan(
        _review_plan(module, contract),
        acceptance_contract=contract,
        known_path_refs={"src/other.py"},
    )
    assert "focus area R1 references unresolved paths: src/diagnostics.py" in unresolved


def test_review_plan_rejects_missing_required_scope_collections_without_contract() -> None:
    module = _load("qa_review_required_collections", TOOL)
    contract = _contract(module)
    plan = _review_plan(module, contract)
    del plan["flows"]
    del plan["focus_areas"]
    del plan["invariant_matrices"]
    plan["digest"] = module.compute_semantic_review_plan_digest(plan)

    findings = module.validate_semantic_review_plan(plan)
    assert "flows is required" in findings
    assert "focus_areas is required" in findings
    assert "invariant_matrices is required" in findings


def test_provider_fidelity_is_criterion_scoped_not_per_proof_class() -> None:
    module = _load("qa_provider_fidelity_scope", TOOL)
    contract = _contract(module)
    digest = contract["digest"]
    plan = _review_plan(module, contract)
    evidence = [
        module.CriterionEvidence(
            "C1",
            "integration",
            module.EvidenceStatus.PASS,
            "candidate-1",
            digest,
            exercise_discriminant="guard-hit",
        ),
        module.CriterionEvidence(
            "C2",
            "security_review",
            module.EvidenceStatus.PASS,
            "candidate-1",
            digest,
            fixture_source=module.FixtureSource.CAPTURED_PROVIDER,
        ),
        module.CriterionEvidence(
            "C2",
            "semantic_review",
            module.EvidenceStatus.PASS,
            "candidate-1",
            digest,
            fixture_source=module.FixtureSource.SYNTHETIC,
            semantic_review_plan_digest=plan["digest"],
        ),
    ]

    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        semantic_review_plan=plan,
        current_base_revision="base-1",
    )
    assert assessment.status == module.AcceptanceStatus.PASS
    assert assessment.satisfied_criteria == ("C1", "C2")


def test_review_plan_rejects_unknown_refs_and_accepts_boundary_and_diagnostic_negative_space() -> None:
    module = _load("qa_review_negative_space", TOOL)
    contract = _contract(module)
    plan = _review_plan(module, contract)
    plan["focus_areas"][0]["criterion_refs"] = ["missing"]
    plan["invariant_matrices"][0]["dimensions"] = [
        "invalid",
        "missing",
        "explicit_null",
        "wrong_type",
        "concurrent",
        "recovery",
        "conflicting_aliases",
        "alternate_provider_wording",
        "source_payload_embedded",
    ]
    plan["digest"] = module.compute_semantic_review_plan_digest(plan)
    findings = module.validate_semantic_review_plan(plan, acceptance_contract=contract)
    assert "focus_areas R1 references unknown criterion: missing" in findings
    assert not any("unknown dimensions" in finding for finding in findings)


def test_semantic_review_evidence_requires_current_validated_plan_digest() -> None:
    module = _load("qa_semantic_evidence_binding", TOOL)
    contract = _contract(module)
    digest = contract["digest"]
    plan = _review_plan(module, contract)
    base_evidence = [
        module.CriterionEvidence(
            "C1",
            "integration",
            module.EvidenceStatus.PASS,
            "candidate-1",
            digest,
            exercise_discriminant="guard-hit",
        ),
        module.CriterionEvidence(
            "C2",
            "security_review",
            module.EvidenceStatus.PASS,
            "candidate-1",
            digest,
            fixture_source=module.FixtureSource.CAPTURED_PROVIDER,
        ),
    ]

    missing_binding = base_evidence + [
        module.CriterionEvidence(
            "C2",
            "semantic_review",
            module.EvidenceStatus.PASS,
            "candidate-1",
            digest,
            fixture_source=module.FixtureSource.SYNTHETIC,
        )
    ]
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=missing_binding,
        semantic_review_plan=plan,
        current_base_revision="base-1",
    )
    assert assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert any("not bound to the current validated plan" in finding for finding in assessment.findings)

    old_digest = plan["digest"]
    widened = json.loads(json.dumps(plan))
    widened["revision"] = "r2"
    widened["focus_areas"][0]["invariants"].append("unknown provider wording remains bounded")
    widened["digest"] = module.compute_semantic_review_plan_digest(widened)
    stale_binding = base_evidence + [
        module.CriterionEvidence(
            "C2",
            "semantic_review",
            module.EvidenceStatus.PASS,
            "candidate-1",
            digest,
            fixture_source=module.FixtureSource.SYNTHETIC,
            semantic_review_plan_digest=old_digest,
        )
    ]
    stale_assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=stale_binding,
        semantic_review_plan=widened,
        current_base_revision="base-1",
    )
    assert stale_assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert any("not bound to the current validated plan" in finding for finding in stale_assessment.findings)

    current_evidence = base_evidence + [
        module.CriterionEvidence(
            "C2",
            "semantic_review",
            module.EvidenceStatus.PASS,
            "candidate-1",
            digest,
            fixture_source=module.FixtureSource.SYNTHETIC,
            semantic_review_plan_digest=widened["digest"],
        )
    ]
    assert module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=current_evidence,
        semantic_review_plan=widened,
        current_base_revision="base-1",
    ).status == module.AcceptanceStatus.PASS


def test_base_bound_semantic_review_requires_current_base_revision() -> None:
    module = _load("qa_semantic_base_binding", TOOL)
    contract = _contract(module)
    digest = contract["digest"]
    plan = _review_plan(module, contract)
    evidence = [
        module.CriterionEvidence(
            "C1",
            "integration",
            module.EvidenceStatus.PASS,
            "candidate-1",
            digest,
            exercise_discriminant="guard-hit",
        ),
        module.CriterionEvidence(
            "C2",
            "security_review",
            module.EvidenceStatus.PASS,
            "candidate-1",
            digest,
            fixture_source=module.FixtureSource.CAPTURED_PROVIDER,
        ),
        module.CriterionEvidence(
            "C2",
            "semantic_review",
            module.EvidenceStatus.PASS,
            "candidate-1",
            digest,
            fixture_source=module.FixtureSource.SYNTHETIC,
            semantic_review_plan_digest=plan["digest"],
        ),
    ]

    missing_base = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        semantic_review_plan=plan,
    )
    assert missing_base.status == module.AcceptanceStatus.INCOMPLETE
    assert "base-bound semantic review plan requires the current base revision" in missing_base.findings

    stale_base = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        semantic_review_plan=plan,
        current_base_revision="base-0",
    )
    assert stale_base.status == module.AcceptanceStatus.INCOMPLETE
    assert any("stale for the current base" in finding for finding in stale_base.findings)

    current = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        semantic_review_plan=plan,
        current_base_revision="base-1",
    )
    assert current.status == module.AcceptanceStatus.PASS


def test_exact_artifact_proof_requires_exact_candidate_artifact_binding() -> None:
    module = _load("qa_exact_artifact_binding", TOOL)
    contract: dict[str, object] = {
        "schema_version": 1,
        "change_id": "artifact-change",
        "revision": "r1",
        "obligations": [
            {
                "id": "O1",
                "kind": "contract",
                "statement": "published artifact matches candidate",
                "required": True,
            }
        ],
        "criteria": [
            {
                "id": "C1",
                "obligation_refs": ["O1"],
                "expected_outcome": "candidate artifact is exercised",
                "rejection_condition": "proof comes from another revision or lacks artifact identity",
                "required": True,
                "proof_classes": ["exact_artifact"],
            }
        ],
    }
    contract["digest"] = module.compute_change_contract_digest(contract)
    digest = contract["digest"]

    missing = [
        module.CriterionEvidence(
            "C1", "exact_artifact", module.EvidenceStatus.PASS, "candidate-1", digest
        )
    ]
    assessment = module.evaluate_acceptance(
        contract, candidate_revision="candidate-1", evidence=missing
    )
    assert assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert any("lacks valid exact evidence binding" in finding for finding in assessment.findings)

    stale_binding = module.ExactEvidenceBinding(
        candidate_revision="candidate-0",
        evidence_revision="candidate-0",
        artifact_digest="sha256:" + "a" * 64,
    )
    stale = [
        module.CriterionEvidence(
            "C1",
            "exact_artifact",
            module.EvidenceStatus.PASS,
            "candidate-1",
            digest,
            exact_evidence_binding=stale_binding,
        )
    ]
    assert module.evaluate_acceptance(
        contract, candidate_revision="candidate-1", evidence=stale
    ).status == module.AcceptanceStatus.INCOMPLETE

    current_binding = module.ExactEvidenceBinding(
        candidate_revision="candidate-1",
        evidence_revision="candidate-1",
        artifact_digest="sha256:" + "b" * 64,
    )
    current = [
        module.CriterionEvidence(
            "C1",
            "exact_artifact",
            module.EvidenceStatus.PASS,
            "candidate-1",
            digest,
            exact_evidence_binding=current_binding,
        )
    ]
    assessment = module.evaluate_acceptance(
        contract, candidate_revision="candidate-1", evidence=current
    )
    assert assessment.status == module.AcceptanceStatus.PASS


def test_acceptance_rejects_blank_candidate_revision_before_evidence_matching() -> None:
    module = _load("qa_blank_candidate", TOOL)
    contract: dict[str, object] = {
        "schema_version": 1,
        "change_id": "blank-candidate",
        "revision": "r1",
        "obligations": [
            {"id": "O1", "kind": "functional", "statement": "prove behavior", "required": True}
        ],
        "criteria": [
            {
                "id": "C1",
                "obligation_refs": ["O1"],
                "expected_outcome": "behavior is proven",
                "rejection_condition": "behavior is not proven",
                "required": True,
                "proof_classes": ["integration"],
            }
        ],
    }
    contract["digest"] = module.compute_change_contract_digest(contract)
    evidence = [
        module.CriterionEvidence(
            "C1",
            "integration",
            module.EvidenceStatus.PASS,
            "",
            contract["digest"],
        )
    ]
    assessment = module.evaluate_acceptance(contract, candidate_revision="", evidence=evidence)
    assert assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert "candidate_revision must be a non-empty string" in assessment.findings


def test_contract_schemas_are_closed_and_machine_readable() -> None:
    for path in (CHANGE_SCHEMA, REVIEW_SCHEMA):
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["$schema"].endswith("2020-12/schema")
        assert schema["additionalProperties"] is False


def test_authorized_policy_waiver_is_alternate_satisfaction_not_pass_evidence() -> None:
    module = _load("qa_contract_waiver_alt", TOOL)
    contract = _contract(module)
    digest = contract["digest"]
    evidence = [
        module.CriterionEvidence(
            "C1",
            "integration",
            module.EvidenceStatus.PASS,
            "candidate-1",
            digest,
            exercise_discriminant="guard-hit",
        )
    ]
    gap = module.KnownGap(
        "G2",
        ("C2",),
        True,
        disposition="waived_by_policy",
    )
    authorization = module.PolicyWaiverAuthorization(
        waiver_ref="policy-waiver:G2",
        gap_id="G2",
        criterion_refs=("C2",),
        candidate_revision="candidate-1",
        contract_digest=digest,
    )
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        known_gaps=[gap],
        trusted_policy_waivers=[authorization],
    )
    assert assessment.status == module.AcceptanceStatus.PASS
    assert assessment.satisfied_criteria == ("C1",)
    assert assessment.waived_criteria == ("C2",)

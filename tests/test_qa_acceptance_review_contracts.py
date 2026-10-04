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
        ),
    ]
    assessment = module.evaluate_acceptance(contract, candidate_revision="candidate-1", evidence=evidence)
    assert assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert any("vacuous PASS" in finding for finding in assessment.findings)
    assert any("incomplete/deferred semantic coverage" in finding for finding in assessment.findings)
    assert any("provider-faithful" in finding for finding in assessment.findings)

    evidence[0] = module.CriterionEvidence(
        "C1", "integration", module.EvidenceStatus.PASS, "candidate-1", digest, exercise_discriminant=None
    )
    assessment = module.evaluate_acceptance(contract, candidate_revision="candidate-1", evidence=evidence)
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
    assessment = module.evaluate_acceptance(contract, candidate_revision="candidate-1", evidence=evidence)
    assert any("incomplete/deferred semantic coverage" in finding for finding in assessment.findings)


def test_current_complete_evidence_passes_but_known_gap_cannot_self_waive() -> None:
    module = _load("qa_contract_gap", TOOL)
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
        ),
    ]
    assessment = module.evaluate_acceptance(
        contract, candidate_revision="candidate-1", evidence=evidence
    )
    assert assessment.status == module.AcceptanceStatus.PASS

    self_waived = module.KnownGap(
        "G1", ("C1",), True, disposition="waived_by_policy", waiver_authorized=False
    )
    assessment = module.evaluate_acceptance(
        contract, candidate_revision="candidate-1", evidence=evidence, known_gaps=[self_waived]
    )
    assert assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert any("without trusted authorization" in finding for finding in assessment.findings)

    authorized_without_ref = module.KnownGap(
        "G1", ("C1",), True, disposition="waived_by_policy", waiver_authorized=True
    )
    assert module.evaluate_acceptance(
        contract, candidate_revision="candidate-1", evidence=evidence, known_gaps=[authorized_without_ref]
    ).status == module.AcceptanceStatus.INCOMPLETE

    authorized = module.KnownGap(
        "G1",
        ("C1",),
        True,
        disposition="waived_by_policy",
        waiver_authorized=True,
        waiver_ref="policy-waiver:G1",
    )
    assert module.evaluate_acceptance(
        contract, candidate_revision="candidate-1", evidence=evidence, known_gaps=[authorized]
    ).status == module.AcceptanceStatus.PASS


def test_resolved_gap_must_be_current_but_current_resolution_does_not_block() -> None:
    module = _load("qa_contract_resolved_gap", TOOL)
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
        contract, candidate_revision="candidate-1", evidence=evidence, known_gaps=[current]
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
        contract, candidate_revision="candidate-1", evidence=evidence, known_gaps=[stale]
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
    plan["flows"] = []
    plan["focus_areas"] = []
    plan["invariant_matrices"] = []
    plan["digest"] = module.compute_semantic_review_plan_digest(plan)
    findings = module.validate_semantic_review_plan(plan, acceptance_contract=contract)
    assert "required semantic-review criteria lack plan coverage: C2" in findings

    unresolved = module.validate_semantic_review_plan(
        _review_plan(module, contract),
        acceptance_contract=contract,
        known_path_refs={"src/other.py"},
    )
    assert "focus area R1 references unresolved paths: src/diagnostics.py" in unresolved


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
    waiver = module.KnownGap(
        "G2",
        ("C2",),
        True,
        disposition="waived_by_policy",
        waiver_authorized=True,
        waiver_ref="policy-waiver:G2",
    )
    assessment = module.evaluate_acceptance(
        contract, candidate_revision="candidate-1", evidence=evidence, known_gaps=[waiver]
    )
    assert assessment.status == module.AcceptanceStatus.PASS
    assert assessment.satisfied_criteria == ("C1",)
    assert assessment.waived_criteria == ("C2",)

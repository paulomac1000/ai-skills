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


def _gap_snapshot(
    module: ModuleType,
    contract: dict[str, object],
    gaps: tuple[object, ...] | list[object] = (),
    *,
    candidate_revision: str = "candidate-1",
):
    return module.KnownGapRegistrySnapshot(
        snapshot_ref=f"known-gaps:{candidate_revision}:snapshot-1",
        candidate_revision=candidate_revision,
        contract_digest=contract["digest"],
        gaps=tuple(gaps),
    )


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




def test_acceptance_helper_rejects_schema_boolean_version_and_length_violations() -> None:
    module = _load("qa_contract_schema_parity", TOOL)

    boolean_version = _contract(module)
    boolean_version["schema_version"] = True
    boolean_version["digest"] = module.compute_change_contract_digest(boolean_version)
    assert "schema_version must be integer 1" in module.validate_change_acceptance_contract(boolean_version)

    oversized = _contract(module)
    oversized["change_id"] = "c" * 257
    oversized["revision"] = "r" * 257
    oversized["obligations"][0]["statement"] = "s" * 4097
    oversized["obligations"][0]["source_ref"] = "p" * 2049
    oversized["criteria"][0]["expected_outcome"] = "e" * 4097
    oversized["criteria"][0]["rejection_condition"] = "x" * 4097
    oversized["digest"] = module.compute_change_contract_digest(oversized)
    findings = module.validate_change_acceptance_contract(oversized)
    assert "change_id must be at most 256 characters" in findings
    assert "revision must be at most 256 characters" in findings
    assert "obligation O1 statement must be at most 4096 characters" in findings
    assert "obligation O1 source_ref must be at most 2048 characters" in findings
    assert "criterion C1 expected_outcome must be at most 4096 characters" in findings
    assert "criterion C1 rejection_condition must be at most 4096 characters" in findings

    oversized_ids = _contract(module)
    oversized_ids["obligations"][0]["id"] = "o" * 129
    oversized_ids["criteria"][0]["id"] = "c" * 129
    oversized_ids["criteria"][1]["obligation_refs"] = ["r" * 129]
    oversized_ids["digest"] = module.compute_change_contract_digest(oversized_ids)
    id_findings = module.validate_change_acceptance_contract(oversized_ids)
    assert any("obligation id must be at most 128 characters" in finding for finding in id_findings)
    assert any("criterion id must be at most 128 characters" in finding for finding in id_findings)
    assert "criterion C2 obligation_refs must be at most 128 characters" in id_findings

def test_public_validators_reject_malformed_roots_and_path_sets_without_raising() -> None:
    module = _load("qa_public_validator_roots", TOOL)

    assert module.validate_change_acceptance_contract([]) == (
        "acceptance contract must be an object",
    )
    assert module.validate_change_acceptance_contract("not-an-object") == (
        "acceptance contract must be an object",
    )
    assert module.validate_semantic_review_plan([]) == (
        "semantic review plan must be an object",
    )

    contract = _contract(module)
    plan = _review_plan(module, contract)
    findings = module.validate_semantic_review_plan(
        plan,
        acceptance_contract=contract,
        known_path_refs=["src/diagnostics.py"],
    )
    assert "known_path_refs must be a set of non-empty strings" in findings


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
    assessment = module.evaluate_acceptance(contract, candidate_revision="candidate-1", evidence=evidence, trusted_known_gap_snapshot=_gap_snapshot(module, contract, ()))
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
    assessment = module.evaluate_acceptance(contract, candidate_revision="candidate-1", evidence=stale, trusted_known_gap_snapshot=_gap_snapshot(module, contract, ()))
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
    ,
        trusted_known_gap_snapshot=_gap_snapshot(module, changed, ()),
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
    
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, ()),
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
    
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, ()),
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
    
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, ()),
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
    
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, ()),
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
    
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, [reported_waiver]),
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
    
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, [reported_waiver]),
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
    
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, [reported_waiver]),
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
    
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, [reported_waiver]),
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
    
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, [current]),
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
    
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, [stale]),
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


def test_review_helper_rejects_schema_boolean_version_and_length_violations() -> None:
    module = _load("qa_review_schema_parity", TOOL)
    contract = _contract(module)

    boolean_version = _review_plan(module, contract)
    boolean_version["schema_version"] = True
    boolean_version["digest"] = module.compute_semantic_review_plan_digest(boolean_version)
    assert "schema_version must be integer 1" in module.validate_semantic_review_plan(
        boolean_version, acceptance_contract=contract
    )

    oversized = _review_plan(module, contract)
    oversized["plan_id"] = "p" * 257
    oversized["revision"] = "r" * 257
    oversized["candidate_revision"] = "c" * 257
    oversized["base_revision"] = "b" * 257
    oversized["policy_revision"] = "q" * 257
    oversized["flows"][0]["entry_point"] = "e" * 2049
    oversized["flows"][0]["terminal_outcome"] = "t" * 2049
    oversized["focus_areas"][0]["path_refs"] = ["p" * 2049]
    oversized["focus_areas"][0]["invariants"] = ["i" * 2049]
    oversized["focus_areas"][0]["analogue_refs"] = ["a" * 2049]
    oversized["invariant_matrices"][0]["invariant_ref"] = "m" * 2049
    oversized["invariant_matrices"][0]["analogue_refs"] = ["a" * 2049]
    oversized["digest"] = module.compute_semantic_review_plan_digest(oversized)
    findings = module.validate_semantic_review_plan(oversized, acceptance_contract=contract)
    assert "plan_id must be at most 256 characters" in findings
    assert "revision must be at most 256 characters" in findings
    assert "candidate_revision must be at most 256 characters" in findings
    assert "base_revision must be at most 256 characters" in findings
    assert "policy_revision must be at most 256 characters" in findings
    assert "flow F1 entry_point must be at most 2048 characters" in findings
    assert "flow F1 terminal_outcome must be at most 2048 characters" in findings
    assert "focus area R1 path_refs must be at most 2048 characters" in findings
    assert "focus area R1 invariants must be at most 2048 characters" in findings
    assert "focus area R1 analogue_refs must be at most 2048 characters" in findings
    assert "invariant matrix M1 invariant_ref must be at most 2048 characters" in findings
    assert "invariant matrix M1 analogue_refs must be at most 2048 characters" in findings


def test_review_plan_resolves_analogue_paths_against_known_paths() -> None:
    module = _load("qa_review_analogue_paths", TOOL)
    contract = _contract(module)
    plan = _review_plan(module, contract)
    plan["invariant_matrices"][0]["analogue_refs"] = ["src/matrix_analogue.py"]
    plan["digest"] = module.compute_semantic_review_plan_digest(plan)

    findings = module.validate_semantic_review_plan(
        plan,
        acceptance_contract=contract,
        known_path_refs={"src/diagnostics.py"},
    )
    assert "focus area R1 references unresolved analogue paths: src/provider_errors.py" in findings
    assert "invariant matrix M1 references unresolved analogue paths: src/matrix_analogue.py" in findings

    assert module.validate_semantic_review_plan(
        plan,
        acceptance_contract=contract,
        known_path_refs={
            "src/diagnostics.py",
            "src/provider_errors.py",
            "src/matrix_analogue.py",
        },
    ) == ()


def test_acceptance_forwards_known_paths_into_semantic_review_validation() -> None:
    module = _load("qa_acceptance_known_paths", TOOL)
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

    incomplete = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        semantic_review_plan=plan,
        current_base_revision="base-1",
        known_path_refs={"src/diagnostics.py"},
    
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, ()),
    )
    assert incomplete.status == module.AcceptanceStatus.INCOMPLETE
    assert any("unresolved analogue paths: src/provider_errors.py" in finding for finding in incomplete.findings)

    complete = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        semantic_review_plan=plan,
        current_base_revision="base-1",
        known_path_refs={"src/diagnostics.py", "src/provider_errors.py"},
    
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, ()),
    )
    assert complete.status == module.AcceptanceStatus.PASS


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
    
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, ()),
    )
    assert assessment.status == module.AcceptanceStatus.PASS
    assert assessment.satisfied_criteria == ("C1", "C2")


def test_provider_faithful_failure_requires_faithful_fixture() -> None:
    module = _load("qa_provider_fidelity_fail", TOOL)
    contract: dict[str, object] = {
        "schema_version": 1,
        "change_id": "provider-failure",
        "revision": "r1",
        "obligations": [
            {
                "id": "O1",
                "kind": "contract",
                "statement": "preserve provider compatibility",
                "required": True,
            }
        ],
        "criteria": [
            {
                "id": "C1",
                "obligation_refs": ["O1"],
                "expected_outcome": "provider-compatible input is accepted",
                "rejection_condition": "provider-compatible input fails",
                "required": True,
                "proof_classes": ["integration"],
                "fixture_fidelity": "provider_faithful",
            }
        ],
    }
    contract["digest"] = module.compute_change_contract_digest(contract)
    snapshot = _gap_snapshot(module, contract)

    synthetic_failure = [
        module.CriterionEvidence(
            "C1",
            "integration",
            module.EvidenceStatus.FAIL,
            "candidate-1",
            contract["digest"],
            fixture_source=module.FixtureSource.SYNTHETIC,
        )
    ]
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=synthetic_failure,
        trusted_known_gap_snapshot=snapshot,
    )
    assert assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert any(
        "provider-faithful FAIL lacks provider-faithful fixture evidence" in finding
        for finding in assessment.findings
    )
    assert not any("has current FAIL evidence" in finding for finding in assessment.findings)

    captured_failure = [
        module.CriterionEvidence(
            "C1",
            "integration",
            module.EvidenceStatus.FAIL,
            "candidate-1",
            contract["digest"],
            fixture_source=module.FixtureSource.CAPTURED_PROVIDER,
        )
    ]
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=captured_failure,
        trusted_known_gap_snapshot=snapshot,
    )
    assert assessment.status == module.AcceptanceStatus.FAIL
    assert "required criterion C1 has current FAIL evidence" in assessment.findings


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
    
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, ()),
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
    
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, ()),
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
    
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, ()),
    ).status == module.AcceptanceStatus.PASS

    unbound_fail = base_evidence + [
        module.CriterionEvidence(
            "C2",
            "semantic_review",
            module.EvidenceStatus.FAIL,
            "candidate-1",
            digest,
            fixture_source=module.FixtureSource.CAPTURED_PROVIDER,
        )
    ]
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=unbound_fail,
        semantic_review_plan=widened,
        current_base_revision="base-1",
        trusted_known_gap_snapshot=_gap_snapshot(module, contract),
    )
    assert assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert any(
        "semantic-review FAIL is not bound to the current validated plan" in finding
        for finding in assessment.findings
    )

    bound_fail = base_evidence + [
        module.CriterionEvidence(
            "C2",
            "semantic_review",
            module.EvidenceStatus.FAIL,
            "candidate-1",
            digest,
            fixture_source=module.FixtureSource.CAPTURED_PROVIDER,
            semantic_review_plan_digest=widened["digest"],
        )
    ]
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=bound_fail,
        semantic_review_plan=widened,
        current_base_revision="base-1",
        trusted_known_gap_snapshot=_gap_snapshot(module, contract),
    )
    assert assessment.status == module.AcceptanceStatus.FAIL
    assert "required criterion C2 has current FAIL evidence" in assessment.findings


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
    
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, ()),
    )
    assert missing_base.status == module.AcceptanceStatus.INCOMPLETE
    assert "base-bound semantic review plan requires the current base revision" in missing_base.findings

    stale_base = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        semantic_review_plan=plan,
        current_base_revision="base-0",
    
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, ()),
    )
    assert stale_base.status == module.AcceptanceStatus.INCOMPLETE
    assert any("stale for the current base" in finding for finding in stale_base.findings)

    current = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        semantic_review_plan=plan,
        current_base_revision="base-1",
    
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, ()),
    )
    assert current.status == module.AcceptanceStatus.PASS

    unbound = json.loads(json.dumps(plan))
    unbound["base_revision"] = None
    unbound["digest"] = module.compute_semantic_review_plan_digest(unbound)
    unbound_evidence = [
        item
        if item.proof_class != "semantic_review"
        else module.CriterionEvidence(
            item.criterion_id,
            item.proof_class,
            item.status,
            item.candidate_revision,
            item.contract_digest,
            discriminating_observations=item.discriminating_observations,
            exercise_discriminant=item.exercise_discriminant,
            coverage_complete=item.coverage_complete,
            deferred_count=item.deferred_count,
            fixture_source=item.fixture_source,
            exact_evidence_binding=item.exact_evidence_binding,
            semantic_review_plan_digest=unbound["digest"],
        )
        for item in evidence
    ]
    supplied_base = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=unbound_evidence,
        semantic_review_plan=unbound,
        current_base_revision="base-1",
    
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, ()),
    )
    assert supplied_base.status == module.AcceptanceStatus.INCOMPLETE
    assert any("stale for the current base" in finding for finding in supplied_base.findings)


def test_fail_evidence_requires_proof_of_exercise_before_hard_failure() -> None:
    module = _load("qa_fail_proof_of_exercise", TOOL)
    contract: dict[str, object] = {
        "schema_version": 1,
        "change_id": "failure-proof",
        "revision": "r1",
        "obligations": [
            {
                "id": "O1",
                "kind": "functional",
                "statement": "reject the exercised invalid path",
                "required": True,
            }
        ],
        "criteria": [
            {
                "id": "C1",
                "obligation_refs": ["O1"],
                "expected_outcome": "invalid path is rejected",
                "rejection_condition": "candidate violates the exercised guard",
                "required": True,
                "proof_classes": ["integration"],
                "proof_of_exercise_required": True,
            }
        ],
    }
    contract["digest"] = module.compute_change_contract_digest(contract)
    snapshot = _gap_snapshot(module, contract)

    zero_observations = [
        module.CriterionEvidence(
            "C1",
            "integration",
            module.EvidenceStatus.FAIL,
            "candidate-1",
            contract["digest"],
            discriminating_observations=0,
        )
    ]
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=zero_observations,
        trusted_known_gap_snapshot=snapshot,
    )
    assert assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert any(
        "FAIL lacks discriminating proof-of-exercise observations" in finding
        for finding in assessment.findings
    )
    assert not any("has current FAIL evidence" in finding for finding in assessment.findings)

    missing_discriminant = [
        module.CriterionEvidence(
            "C1",
            "integration",
            module.EvidenceStatus.FAIL,
            "candidate-1",
            contract["digest"],
            discriminating_observations=1,
        )
    ]
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=missing_discriminant,
        trusted_known_gap_snapshot=snapshot,
    )
    assert assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert any(
        "FAIL lacks required proof-of-exercise discriminant" in finding
        for finding in assessment.findings
    )

    exercised_failure = [
        module.CriterionEvidence(
            "C1",
            "integration",
            module.EvidenceStatus.FAIL,
            "candidate-1",
            contract["digest"],
            discriminating_observations=1,
            exercise_discriminant="guard-hit",
        )
    ]
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=exercised_failure,
        trusted_known_gap_snapshot=snapshot,
    )
    assert assessment.status == module.AcceptanceStatus.FAIL
    assert "required criterion C1 has current FAIL evidence" in assessment.findings


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
    ,
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, ()),
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
    ,
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, ()),
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
    ,
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, ()),
    )
    assert assessment.status == module.AcceptanceStatus.PASS

    unbound_fail = [
        module.CriterionEvidence(
            "C1",
            "exact_artifact",
            module.EvidenceStatus.FAIL,
            "candidate-1",
            digest,
        )
    ]
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=unbound_fail,
        trusted_known_gap_snapshot=_gap_snapshot(module, contract),
    )
    assert assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert any(
        "exact-artifact FAIL lacks valid exact evidence binding" in finding
        for finding in assessment.findings
    )
    assert not any("has current FAIL evidence" in finding for finding in assessment.findings)

    stale_fail = [
        module.CriterionEvidence(
            "C1",
            "exact_artifact",
            module.EvidenceStatus.FAIL,
            "candidate-1",
            digest,
            exact_evidence_binding=stale_binding,
        )
    ]
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=stale_fail,
        trusted_known_gap_snapshot=_gap_snapshot(module, contract),
    )
    assert assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert any(
        "exact-artifact FAIL lacks valid exact evidence binding" in finding
        for finding in assessment.findings
    )

    bound_fail = [
        module.CriterionEvidence(
            "C1",
            "exact_artifact",
            module.EvidenceStatus.FAIL,
            "candidate-1",
            digest,
            exact_evidence_binding=current_binding,
        )
    ]
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=bound_fail,
        trusted_known_gap_snapshot=_gap_snapshot(module, contract),
    )
    assert assessment.status == module.AcceptanceStatus.FAIL
    assert "required criterion C1 has current FAIL evidence" in assessment.findings

    non_required_fail = [
        module.CriterionEvidence(
            "C1",
            "integration",
            module.EvidenceStatus.FAIL,
            "candidate-1",
            digest,
        )
    ]
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=non_required_fail,
        trusted_known_gap_snapshot=_gap_snapshot(module, contract),
    )
    assert assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert "criterion C1 FAIL evidence uses non-required proof class: integration" in assessment.findings


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


def test_known_gap_snapshot_is_complete_and_caller_omission_cannot_erase_gap() -> None:
    module = _load("qa_gap_snapshot_completeness", TOOL)
    contract: dict[str, object] = {
        "schema_version": 1,
        "change_id": "gap-snapshot",
        "revision": "r1",
        "obligations": [
            {"id": "O1", "kind": "functional", "statement": "preserve behavior", "required": True}
        ],
        "criteria": [
            {
                "id": "C1",
                "obligation_refs": ["O1"],
                "expected_outcome": "behavior is preserved",
                "rejection_condition": "behavior is not preserved",
                "required": True,
                "proof_classes": ["integration"],
            }
        ],
    }
    contract["digest"] = module.compute_change_contract_digest(contract)
    evidence = [
        module.CriterionEvidence(
            "C1", "integration", module.EvidenceStatus.PASS, "candidate-1", contract["digest"]
        )
    ]
    gap = module.KnownGap("G1", ("C1",), True, disposition="unresolved")
    snapshot = _gap_snapshot(module, contract, [gap])

    no_snapshot = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
    )
    assert no_snapshot.status == module.AcceptanceStatus.INCOMPLETE
    assert "trusted complete known-gap registry snapshot is required" in no_snapshot.findings

    omitted_from_caller = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        trusted_known_gap_snapshot=snapshot,
    )
    assert omitted_from_caller.status == module.AcceptanceStatus.INCOMPLETE
    assert any("remains load-bearing" in finding for finding in omitted_from_caller.findings)

    tampered = module.KnownGap("G1", (), False, disposition="resolved")
    tampered_caller = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        known_gaps=[tampered],
        trusted_known_gap_snapshot=snapshot,
    )
    assert tampered_caller.status == module.AcceptanceStatus.INCOMPLETE
    assert "supplied known gaps do not match trusted registry records" in tampered_caller.findings
    assert any("remains load-bearing" in finding for finding in tampered_caller.findings)

    empty_snapshot = _gap_snapshot(module, contract)
    assert module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        trusted_known_gap_snapshot=empty_snapshot,
    ).status == module.AcceptanceStatus.PASS


def test_known_gap_snapshot_rejects_incomplete_or_malformed_records() -> None:
    module = _load("qa_gap_snapshot_validation", TOOL)
    contract: dict[str, object] = {
        "schema_version": 1,
        "change_id": "gap-snapshot-validation",
        "revision": "r1",
        "obligations": [
            {"id": "O1", "kind": "functional", "statement": "preserve behavior", "required": True}
        ],
        "criteria": [
            {
                "id": "C1",
                "obligation_refs": ["O1"],
                "expected_outcome": "behavior is preserved",
                "rejection_condition": "behavior is not preserved",
                "required": True,
                "proof_classes": ["integration"],
            }
        ],
    }
    contract["digest"] = module.compute_change_contract_digest(contract)
    evidence = [
        module.CriterionEvidence(
            "C1", "integration", module.EvidenceStatus.PASS, "candidate-1", contract["digest"]
        )
    ]
    incomplete = module.KnownGapRegistrySnapshot(
        "known-gaps:incomplete",
        "candidate-1",
        contract["digest"],
        (),
        complete=False,
    )
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        trusted_known_gap_snapshot=incomplete,
    )
    assert assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert "known-gap registry snapshot must be complete" in assessment.findings

    unknown_ref = module.KnownGap("G1", ("missing",), True)
    malformed = _gap_snapshot(module, contract, [unknown_ref])
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        trusted_known_gap_snapshot=malformed,
    )
    assert assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert "known gap G1 references unknown criteria: missing" in assessment.findings


    unscoped = module.KnownGap("G2", (), True, disposition="unresolved")
    unscoped_snapshot = _gap_snapshot(module, contract, [unscoped])
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        trusted_known_gap_snapshot=unscoped_snapshot,
    )
    assert assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert (
        "known gap G2 with load-bearing or unknown impact must reference at least one criterion"
        in assessment.findings
    )

    malformed_gaps = module.KnownGapRegistrySnapshot(
        "known-gaps:malformed-shape",
        "candidate-1",
        contract["digest"],
        None,
    )
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        trusted_known_gap_snapshot=malformed_gaps,
    )
    assert assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert "known-gap registry snapshot gaps must be an array" in assessment.findings


    malformed_container = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        trusted_known_gap_snapshot={"gaps": ()},
    )
    assert malformed_container.status == module.AcceptanceStatus.INCOMPLETE
    assert (
        "trusted known-gap registry snapshot must be a KnownGapRegistrySnapshot record"
        in malformed_container.findings
    )

    malformed_gap_id = module.KnownGap(7, ("C1",), True)
    malformed_record = module.KnownGapRegistrySnapshot(
        "known-gaps:malformed-record",
        "candidate-1",
        contract["digest"],
        (malformed_gap_id,),
    )
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        trusted_known_gap_snapshot=malformed_record,
    )
    assert assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert "known gap id must be a non-empty string" in assessment.findings


def test_acceptance_rejects_malformed_evidence_and_nested_bindings_without_raising() -> None:
    module = _load("qa_malformed_evidence_input", TOOL)
    contract: dict[str, object] = {
        "schema_version": 1,
        "change_id": "malformed-evidence",
        "revision": "r1",
        "obligations": [
            {"id": "O1", "kind": "functional", "statement": "preserve behavior", "required": True}
        ],
        "criteria": [
            {
                "id": "C1",
                "obligation_refs": ["O1"],
                "expected_outcome": "behavior is preserved",
                "rejection_condition": "behavior is not preserved",
                "required": True,
                "proof_classes": ["integration"],
            }
        ],
    }
    contract["digest"] = module.compute_change_contract_digest(contract)
    snapshot = _gap_snapshot(module, contract)

    malformed_record = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=[{}],
        trusted_known_gap_snapshot=snapshot,
    )
    assert malformed_record.status == module.AcceptanceStatus.INCOMPLETE
    assert "evidence entries must be CriterionEvidence records" in malformed_record.findings

    malformed_binding = module.CriterionEvidence(
        "C1",
        "integration",
        module.EvidenceStatus.PASS,
        "candidate-1",
        contract["digest"],
        exact_evidence_binding={"artifact_digest": "sha256:" + "a" * 64},
    )
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=[malformed_binding],
        trusted_known_gap_snapshot=snapshot,
    )
    assert assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert "evidence for C1 exact_evidence_binding has invalid record type" in assessment.findings

    malformed_fixture = module.CriterionEvidence(
        "C1",
        "integration",
        module.EvidenceStatus.PASS,
        "candidate-1",
        contract["digest"],
        fixture_source=[],
    )
    assessment = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=[malformed_fixture],
        trusted_known_gap_snapshot=snapshot,
    )
    assert assessment.status == module.AcceptanceStatus.INCOMPLETE
    assert "evidence for C1 has invalid fixture_source" in assessment.findings


def test_acceptance_rejects_malformed_policy_and_optional_runtime_inputs() -> None:
    module = _load("qa_malformed_policy_input", TOOL)
    contract: dict[str, object] = {
        "schema_version": 1,
        "change_id": "malformed-policy",
        "revision": "r1",
        "obligations": [
            {"id": "O1", "kind": "functional", "statement": "preserve behavior", "required": True}
        ],
        "criteria": [
            {
                "id": "C1",
                "obligation_refs": ["O1"],
                "expected_outcome": "behavior is preserved",
                "rejection_condition": "behavior is not preserved",
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
            "candidate-1",
            contract["digest"],
        )
    ]
    snapshot = _gap_snapshot(module, contract)

    malformed_waiver = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        trusted_known_gap_snapshot=snapshot,
        trusted_policy_waivers=[None],
    )
    assert malformed_waiver.status == module.AcceptanceStatus.INCOMPLETE
    assert (
        "trusted policy waiver entries must be PolicyWaiverAuthorization records"
        in malformed_waiver.findings
    )

    bad_scope = module.PolicyWaiverAuthorization(
        "policy:bad-scope",
        "G1",
        None,
        "candidate-1",
        contract["digest"],
    )
    malformed_scope = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        trusted_known_gap_snapshot=snapshot,
        trusted_policy_waivers=[bad_scope],
    )
    assert malformed_scope.status == module.AcceptanceStatus.INCOMPLETE
    assert "trusted policy waiver policy:bad-scope must scope at least one criterion" in malformed_scope.findings

    malformed_known_gaps = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        known_gaps=7,
        trusted_known_gap_snapshot=snapshot,
    )
    assert malformed_known_gaps.status == module.AcceptanceStatus.INCOMPLETE
    assert "known_gaps must be an array of KnownGap records" in malformed_known_gaps.findings

    malformed_plan = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        trusted_known_gap_snapshot=snapshot,
        semantic_review_plan=7,
    )
    assert malformed_plan.status == module.AcceptanceStatus.INCOMPLETE
    assert "semantic_review_plan must be an object or null" in malformed_plan.findings

    malformed_paths = module.evaluate_acceptance(
        contract,
        candidate_revision="candidate-1",
        evidence=evidence,
        trusted_known_gap_snapshot=snapshot,
        known_path_refs=["src/not-a-set.py"],
    )
    assert malformed_paths.status == module.AcceptanceStatus.INCOMPLETE
    assert "known_path_refs must be a set of non-empty strings" in malformed_paths.findings

    malformed_contract = module.evaluate_acceptance(
        7,
        candidate_revision="candidate-1",
        evidence=evidence,
        trusted_known_gap_snapshot=snapshot,
    )
    assert malformed_contract.status == module.AcceptanceStatus.INCOMPLETE
    assert "acceptance contract must be an object" in malformed_contract.findings


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
    
        trusted_known_gap_snapshot=_gap_snapshot(module, contract, [gap]),
    )
    assert assessment.status == module.AcceptanceStatus.PASS
    assert assessment.satisfied_criteria == ("C1",)
    assert assessment.waived_criteria == ("C2",)

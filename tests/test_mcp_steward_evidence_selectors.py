from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "contracts" / "evidence-claim-plan.yaml"

EXPECTED_CASES = {
    "steward.design.enforced": (
        ("tests.test_mcp_steward_architect", "test_generated_design_pack_is_cross_contract_valid"),
        (
            "tests.test_mcp_steward_architect",
            "test_design_pack_rejects_unresolved_capability_profile_ref_and_producer_dimension_drift",
        ),
    ),
    "steward.mutation.admitted": (
        (
            "tests.test_mcp_steward_architect",
            "test_mutation_admission_fails_closed_on_authority_fences_capability_candidate_budget_and_ambiguity",
        ),
        (
            "tests.test_mcp_steward_runtime_security",
            "test_real_dispatch_gate_rejects_capability_drift_and_stale_fence_with_zero_provider_calls",
        ),
    ),
    "steward.acceptance.layered": (
        (
            "tests.test_mcp_steward_architect",
            "test_production_acceptance_cannot_skip_independent_live_or_exact_full_path",
        ),
    ),
    "steward.claim.bound": (
        (
            "tests.test_mcp_steward_architect",
            "test_completion_resolves_candidate_binding_producer_authority_and_freshness",
        ),
        (
            "tests.test_mcp_steward_runtime_security",
            "test_evidence_promotion_uses_observed_binding_coverage_and_authority_without_minting",
        ),
    ),
    "steward.cancellation.reconciled": (
        (
            "tests.test_mcp_steward_architect",
            "test_generated_python_runtime_imports_recovers_cancels_and_does_not_hot_poll",
        ),
    ),
}


def test_atomic_steward_evidence_selectors_match_all_required_junit_case_identities() -> None:
    document = yaml.safe_load(PLAN.read_text(encoding="utf-8"))
    claims = {
        claim["subject"]: claim
        for claim in document["profiles"]["repository-rules"]
        if claim.get("subject") in EXPECTED_CASES
    }

    assert set(claims) == set(EXPECTED_CASES)
    for subject, cases in EXPECTED_CASES.items():
        claim = claims[subject]
        selectors = claim["selectors"]

        assert claim["execution_id"] == "repository"
        assert claim["result_files"] == ["repository-junit.xml"]
        assert all("tests/" not in selector for selector in selectors), subject
        for module, test_name in cases:
            identity = f"{module}::{test_name}"
            assert any(fnmatchcase(identity, selector) for selector in selectors), (subject, identity, selectors)

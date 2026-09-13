from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "contracts" / "evidence-claim-plan.yaml"

EXPECTED_CASES = {
    "steward.design.enforced": "test_generated_design_pack_is_cross_contract_valid",
    "steward.mutation.admitted": "test_mutation_admission_fails_closed_on_authority_candidate_budget_and_ambiguity",
    "steward.acceptance.layered": "test_production_acceptance_cannot_skip_independent_live_or_exact_full_path",
    "steward.claim.bound": "test_completion_resolves_candidate_binding_producer_authority_and_freshness",
    "steward.cancellation.reconciled": "test_generated_python_runtime_imports_recovers_cancels_and_does_not_hot_poll",
}


def test_atomic_steward_evidence_selectors_match_junit_case_identities() -> None:
    document = yaml.safe_load(PLAN.read_text(encoding="utf-8"))
    claims = {
        claim["subject"]: claim
        for claim in document["profiles"]["repository-rules"]
        if claim.get("subject") in EXPECTED_CASES
    }

    assert set(claims) == set(EXPECTED_CASES)
    for subject, test_name in EXPECTED_CASES.items():
        claim = claims[subject]
        selectors = claim["selectors"]
        identity = f"tests.test_mcp_steward_architect::{test_name}"

        assert claim["execution_id"] == "repository"
        assert claim["result_files"] == ["repository-junit.xml"]
        assert any(fnmatchcase(identity, selector) for selector in selectors), subject
        assert all("tests/test_mcp_steward_architect.py::" not in selector for selector in selectors), subject

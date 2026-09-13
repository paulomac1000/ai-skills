from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "contracts/evidence-claim-plan.yaml"
text = path.read_text(encoding="utf-8")

replacements = {
"""  - kind: rule
    subject: steward.design.enforced
    selectors:
    - '*test_mcp_steward_architect::test_generated_design_pack_is_cross_contract_valid'
    result_files:
    - repository-junit.xml
    execution_id: repository
""": """  - kind: rule
    subject: steward.design.enforced
    selectors:
    - '*test_mcp_steward_architect::test_generated_design_pack_is_cross_contract_valid'
    - '*test_mcp_steward_architect::test_design_pack_rejects_unresolved_capability_profile_ref_and_producer_dimension_drift'
    result_files:
    - repository-junit.xml
    execution_id: repository
""",
"""  - kind: rule
    subject: steward.mutation.admitted
    selectors:
    - '*test_mcp_steward_architect::test_mutation_admission_fails_closed_on_authority_candidate_budget_and_ambiguity'
    result_files:
    - repository-junit.xml
    execution_id: repository
""": """  - kind: rule
    subject: steward.mutation.admitted
    selectors:
    - '*test_mcp_steward_architect::test_mutation_admission_fails_closed_on_authority_fences_capability_candidate_budget_and_ambiguity'
    - '*test_mcp_steward_runtime_security::test_real_dispatch_gate_rejects_capability_drift_and_stale_fence_with_zero_provider_calls'
    result_files:
    - repository-junit.xml
    execution_id: repository
""",
"""  - kind: rule
    subject: steward.claim.bound
    selectors:
    - '*test_mcp_steward_architect::test_completion_resolves_candidate_binding_producer_authority_and_freshness'
    result_files:
    - repository-junit.xml
    execution_id: repository
""": """  - kind: rule
    subject: steward.claim.bound
    selectors:
    - '*test_mcp_steward_architect::test_completion_resolves_candidate_binding_producer_authority_and_freshness'
    - '*test_mcp_steward_runtime_security::test_evidence_promotion_uses_observed_binding_coverage_and_authority_without_minting'
    result_files:
    - repository-junit.xml
    execution_id: repository
""",
}

for old, new in replacements.items():
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one evidence block, found {count}")
    text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8", newline="\n")
print("Steward evidence claims now bind validator and real runtime regressions")

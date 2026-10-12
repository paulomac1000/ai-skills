#!/usr/bin/env python3
"""Canonical Python quality targets shared by local and hosted repository gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

QUALITY_PATHS = (
    "contracts",
    "scripts/ci.py",
    "scripts/ci_environment.py",
    "scripts/install_locked.py",
    "scripts/quality_targets.py",
    "scripts/select_lock.py",
    "skills/afds-doc-writer/validate.py",
    "skills/agents-md-architect/tools",
    "skills/changelog-release-architect/tools",
    "skills/ci-cd-architect/tools",
    "skills/mcp-gateway-release-verifier/tools",
    "skills/mcp-server-consumer/tools",
    "skills/mcp-steward-architect/tools",
    "skills/qa-change-verifier/tools",
    "skills/readme-architect/tools",
    "skills/skill-architect/tools",
    "skills/mcp-server-architect/tools/generate_python_server.py",
    "skills/mcp-server-architect/tools/generate_python_server_impl.py",
    "skills/mcp-server-architect/tools/generate_dotnet_server.py",
    "skills/mcp-server-architect/tools/inspect_existing_project.py",
    "skills/mcp-server-architect/tools/plan_existing_project.py",
    "skills/mcp-server-architect/tools/check_consumer_canaries.py",
    "skills/mcp-server-architect/tools/capture_mcp_contract.py",
    "skills/mcp-server-architect/tools/compare_mcp_contracts.py",
    "skills/mcp-server-architect/tools/exact_candidate_acceptance.py",
    "skills/mcp-server-architect/tools/mcp_exact_candidate_probe.py",
    "skills/mcp-server-architect/tools/transport_dogfood.py",
    "skills/mcp-server-architect/tools/skill_schema_contract.py",
    "skills/mcp-server-architect/tools/server_invariants.py",
    "skills/mcp-server-architect/tools/control_plane_invariants.py",
    "skills/mcp-server-architect/tools/gateway_identity.py",
    "skills/mcp-server-architect/tools/discovery_index_lifecycle.py",
    "skills/mcp-server-architect/tools/provider_schema_compat.py",
    "skills/mcp-server-architect/tools/semantic_facade.py",
    "scripts/check_release_version.py",
)
TYPE_PATHS = (
    "contracts/artifact_closure.py",
    "contracts/external_gate_deviation.py",
    "contracts/audit_log.py",
    "contracts/diagnostic_egress.py",
    "contracts/semver.py",
    "contracts/evidence.py",
    "contracts/mcp_public_contract.py",
    "contracts/render_rule_catalog.py",
    "contracts/rule_applicability.py",
    "contracts/skill_schema_contract.py",
    "contracts/validate_adoption.py",
    "contracts/validate_atomic_claims.py",
    "contracts/validate_capability_manifest.py",
    "contracts/validate_conformance.py",
    "contracts/validate_consumer_feedback.py",
    "contracts/validate_deployment_observation.py",
    "contracts/validate_evidence_provider.py",
    "contracts/validate_skills_lock.py",
    "contracts/validate_upstream_contract.py",
    "contracts/validate_live_backend_test_policy.py",
    "contracts/validate_operational_claims.py",
    "contracts/validate_trusted_executable_sources.py",
    "contracts/write_evidence_report.py",
    "contracts/run_evidence_command.py",
    "scripts/ci.py",
    "scripts/ci_environment.py",
    "scripts/install_locked.py",
    "scripts/quality_targets.py",
    "scripts/select_lock.py",
    "scripts/check_release_version.py",
    "skills/afds-doc-writer/validate.py",
    "skills/agents-md-architect/tools/audit_agents_md.py",
    "skills/agents-md-architect/tools/discover_repository.py",
    "skills/agents-md-architect/tools/runtime_fact_classification.py",
    "skills/agents-md-architect/tools/validate_agents_md.py",
    "skills/changelog-release-architect/tools/check_release_branch.py",
    "skills/ci-cd-architect/tools/check_ci_execution_policy.py",
    "skills/ci-cd-architect/tools/check_github_actions_policy.py",
    "skills/ci-cd-architect/tools/check_github_actions_policy_impl.py",
    "skills/ci-cd-architect/tools/check_consumer_trust_hygiene.py",
    "skills/ci-cd-architect/tools/review_state_transitions.py",
    "skills/ci-cd-architect/tools/artifact_publication_lease.py",
    "skills/mcp-gateway-release-verifier/tools/compose_release_verdict.py",
    "skills/mcp-gateway-release-verifier/tools/local_candidate_lane.py",
    "skills/mcp-server-consumer/tools/decision_engine.py",
    "skills/mcp-server-consumer/tools/admission.py",
    "skills/mcp-server-consumer/tools/consumer_contracts.py",
    "skills/mcp-server-consumer/tools/delivery_reconciliation.py",
    "skills/mcp-server-consumer/tools/extraction.py",
    "skills/mcp-server-consumer/tools/contract_refs.py",
    "skills/mcp-steward-architect/tools/generate_steward.py",
    "skills/mcp-steward-architect/tools/validate_steward.py",
    "skills/mcp-steward-architect/tools/persistent_context.py",
    "skills/mcp-steward-architect/tools/integration_lease.py",
    "skills/qa-change-verifier/tools/plan_verification.py",
    "skills/qa-change-verifier/tools/migration_acceptance.py",
    "skills/readme-architect/tools/audit_readme.py",
    "skills/readme-architect/tools/collect_readme_evidence.py",
    "skills/skill-architect/tools/audit_skill.py",
    "skills/skill-architect/tools/scaffold_skill.py",
    "skills/skill-architect/tools/validate_skill_evals.py",
    "skills/mcp-server-architect/tools/generate_python_server.py",
    "skills/mcp-server-architect/tools/generate_python_server_impl.py",
    "skills/mcp-server-architect/tools/generate_dotnet_server.py",
    "skills/mcp-server-architect/tools/inspect_existing_project.py",
    "skills/mcp-server-architect/tools/plan_existing_project.py",
    "skills/mcp-server-architect/tools/check_consumer_canaries.py",
    "skills/mcp-server-architect/tools/capture_mcp_contract.py",
    "skills/mcp-server-architect/tools/compare_mcp_contracts.py",
    "skills/mcp-server-architect/tools/exact_candidate_acceptance.py",
    "skills/mcp-server-architect/tools/mcp_exact_candidate_probe.py",
    "skills/mcp-server-architect/tools/transport_dogfood.py",
    "skills/mcp-server-architect/tools/skill_schema_contract.py",
    "skills/mcp-server-architect/tools/server_invariants.py",
    "skills/mcp-server-architect/tools/control_plane_invariants.py",
    "skills/mcp-server-architect/tools/gateway_identity.py",
    "skills/mcp-server-architect/tools/discovery_index_lifecycle.py",
    "skills/mcp-server-architect/tools/provider_schema_compat.py",
    "skills/mcp-server-architect/tools/semantic_facade.py",
)
BANDIT_PATHS = (
    "contracts",
    "scripts",
    "skills/afds-doc-writer",
    "skills/agents-md-architect/tools",
    "skills/changelog-release-architect/tools",
    "skills/ci-cd-architect/tools",
    "skills/mcp-gateway-release-verifier/tools",
    "skills/mcp-server-consumer/tools",
    "skills/mcp-steward-architect/tools",
    "skills/qa-change-verifier/tools",
    "skills/readme-architect/tools",
    "skills/skill-architect/tools",
    "skills/mcp-server-architect/tools",
)
POLICY_COVERAGE_PATHS = (
    "contracts/*.py",
    "skills/afds-doc-writer/*.py",
    "skills/agents-md-architect/tools/*.py",
    "skills/ci-cd-architect/tools/*.py",
    "skills/mcp-gateway-release-verifier/tools/*.py",
    "skills/mcp-server-consumer/tools/*.py",
    "skills/mcp-steward-architect/tools/*.py",
    "skills/qa-change-verifier/tools/*.py",
    "skills/skill-architect/tools/*.py",
    "skills/mcp-server-architect/tools/check_consumer_canaries.py",
    "skills/mcp-server-architect/tools/inspect_existing_project.py",
    "skills/mcp-server-architect/tools/exact_candidate_acceptance.py",
    "skills/mcp-server-architect/tools/transport_dogfood.py",
    "skills/mcp-server-architect/tools/skill_schema_contract.py",
    "skills/mcp-server-architect/tools/server_invariants.py",
    "skills/mcp-server-architect/tools/control_plane_invariants.py",
    "skills/mcp-server-architect/tools/gateway_identity.py",
    "skills/mcp-server-architect/tools/discovery_index_lifecycle.py",
    "skills/mcp-server-architect/tools/provider_schema_compat.py",
    "skills/mcp-server-architect/tools/semantic_facade.py",
)
SECURITY_BOUNDARY_COVERAGE_FLOORS = (
    ("contracts/validate_external_adoption.py", 60),
    ("contracts/validate_external_trust_lock.py", 90),
    ("contracts/validate_live_backend_test_policy.py", 65),
    ("contracts/validate_trusted_executable_sources.py", 70),
    ("contracts/validate_upstream_contract.py", 65),
    ("skills/ci-cd-architect/tools/check_github_provider_controls.py", 60),
    ("skills/mcp-server-architect/tools/check_consumer_canaries.py", 45),
    ("skills/mcp-server-architect/tools/inspect_existing_project.py", 80),
)
# coverage.py's normal --fail-under threshold combines statement and branch
# opportunities. These explicit branch-only baselines prevent trust-boundary
# decision paths from regressing while adversarial tests raise the floors over time.
SECURITY_BOUNDARY_BRANCH_COVERAGE_FLOORS = (
    ("contracts/validate_external_adoption.py", 50),
    ("contracts/validate_external_trust_lock.py", 90),
    ("contracts/validate_live_backend_test_policy.py", 60),
    ("contracts/validate_trusted_executable_sources.py", 70),
    ("contracts/validate_upstream_contract.py", 75),
    ("skills/ci-cd-architect/tools/check_github_provider_controls.py", 60),
    ("skills/mcp-server-architect/tools/check_consumer_canaries.py", 35),
    ("skills/mcp-server-architect/tools/inspect_existing_project.py", 80),
)

TEST_QUALITY_PATHS = ("tests",)

TARGETS = {
    "quality": QUALITY_PATHS,
    "test-quality": TEST_QUALITY_PATHS,
    "typing": TYPE_PATHS,
    "bandit": BANDIT_PATHS,
    "policy-coverage": POLICY_COVERAGE_PATHS,
}


def render_target(name: str) -> str:
    """Render one target list for shell consumption."""
    values = TARGETS[name]
    return ",".join(values) if name == "policy-coverage" else " ".join(values)


def select_test_quality_files(changed_tests: Sequence[str]) -> tuple[str, ...]:
    """Select existing test Python files without traversal, symlinks, or shell-unsafe paths."""
    root = Path(__file__).resolve().parents[1]
    tests_path = root / "tests"
    if tests_path.is_symlink() or not tests_path.is_dir():
        raise ValueError("test-quality root must be a real directory")
    tests_root = tests_path.resolve(strict=True)
    if not tests_root.is_relative_to(root):
        raise ValueError("test-quality root escapes repository")
    if not changed_tests:
        return TEST_QUALITY_PATHS
    selected: set[str] = set()
    for name in changed_tests:
        parts = name.split("/")
        if (
            len(parts) < 2
            or parts[0] != "tests"
            or not name.endswith(".py")
            or "\\" in name
            or ":" in name
            or re.fullmatch(r"[A-Za-z0-9_./-]+", name) is None
            or any(not part or part in {".", ".."} for part in parts)
            or any(char.isspace() for char in name)
        ):
            raise ValueError(f"invalid test-quality source: {name!r}")
        source = root
        for part in parts:
            source = source / part
            if source.is_symlink():
                raise ValueError(f"test-quality source contains symlink: {name!r}")
        try:
            resolved = source.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ValueError(f"missing test-quality source: {name!r}") from exc
        if not resolved.is_relative_to(tests_root) or not resolved.is_file() or source.is_symlink():
            raise ValueError(f"test-quality source escapes or is not a regular file: {name!r}")
        selected.add(name)
    return tuple(sorted(selected))


def profile_provenance(profile: str, selected: Sequence[str]) -> dict[str, object]:
    """Expose selected targets and locked tool configuration; never a PASS receipt."""
    from select_lock import selected_lock

    root = Path(__file__).resolve().parents[1]
    lock = selected_lock()
    config = root / "pyproject.toml"
    try:
        ruff_version = version("ruff")
    except PackageNotFoundError:
        ruff_version = "unavailable"
    return {
        "profile": profile,
        "targets": list(selected),
        "ruffVersion": ruff_version,
        "configPath": config.name,
        "configSha256": hashlib.sha256(config.read_bytes()).hexdigest(),
        "lockPath": lock.name,
        "lockSha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
        "evidence": "diagnostic configuration only; no lint PASS implied",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=tuple(TARGETS))
    parser.add_argument("--changed-test", action="append", default=[], metavar="PATH")
    parser.add_argument("--provenance", action="store_true")
    args = parser.parse_args(argv)
    if args.changed_test and args.target != "test-quality":
        parser.error("--changed-test requires test-quality")
    try:
        if args.target == "test-quality":
            selected = select_test_quality_files(args.changed_test)
        else:
            selected = TARGETS[args.target]
    except ValueError as exc:
        parser.error(str(exc))
    if args.provenance:
        if args.target not in {"quality", "test-quality"}:
            parser.error("--provenance requires a Ruff profile")
        print(json.dumps(profile_provenance(args.target, selected), sort_keys=True))
    else:
        print(" ".join(selected) if args.target == "test-quality" else render_target(args.target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

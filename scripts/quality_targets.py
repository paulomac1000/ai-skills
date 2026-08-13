#!/usr/bin/env python3
"""Canonical Python quality targets shared by local and hosted repository gates."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

QUALITY_PATHS = (
    "contracts",
    "scripts/ci.py",
    "scripts/ci_environment.py",
    "scripts/install_locked.py",
    "scripts/quality_targets.py",
    "scripts/select_lock.py",
    "skills/afds-doc-writer/validate.py",
    "skills/agents-md-architect/tools",
    "skills/ci-cd-architect/tools",
    "skills/mcp-server-consumer/tools",
    "skills/mcp-server-architect/tools/generate_python_server.py",
    "skills/mcp-server-architect/tools/generate_python_server_impl.py",
    "skills/mcp-server-architect/tools/generate_dotnet_server.py",
    "skills/mcp-server-architect/tools/inspect_existing_project.py",
    "skills/mcp-server-architect/tools/plan_existing_project.py",
    "skills/mcp-server-architect/tools/check_consumer_canaries.py",
    "skills/mcp-server-architect/tools/capture_mcp_contract.py",
    "skills/mcp-server-architect/tools/compare_mcp_contracts.py",
    "scripts/check_release_version.py",
)
TYPE_PATHS = (
    "contracts/semver.py",
    "contracts/evidence.py",
    "contracts/mcp_public_contract.py",
    "contracts/render_rule_catalog.py",
    "contracts/rule_applicability.py",
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
    "skills/agents-md-architect/tools/validate_agents_md.py",
    "skills/ci-cd-architect/tools/check_ci_execution_policy.py",
    "skills/ci-cd-architect/tools/check_github_actions_policy.py",
    "skills/ci-cd-architect/tools/check_github_actions_policy_impl.py",
    "skills/ci-cd-architect/tools/check_consumer_trust_hygiene.py",
    "skills/mcp-server-consumer/tools/decision_engine.py",
    "skills/mcp-server-consumer/tools/decision_engine_legacy.py",
    "skills/mcp-server-architect/tools/generate_python_server.py",
    "skills/mcp-server-architect/tools/generate_python_server_impl.py",
    "skills/mcp-server-architect/tools/generate_dotnet_server.py",
    "skills/mcp-server-architect/tools/inspect_existing_project.py",
    "skills/mcp-server-architect/tools/plan_existing_project.py",
    "skills/mcp-server-architect/tools/check_consumer_canaries.py",
    "skills/mcp-server-architect/tools/capture_mcp_contract.py",
    "skills/mcp-server-architect/tools/compare_mcp_contracts.py",
)
BANDIT_PATHS = (
    "contracts",
    "scripts",
    "skills/afds-doc-writer",
    "skills/agents-md-architect/tools",
    "skills/ci-cd-architect/tools",
    "skills/mcp-server-consumer/tools",
    "skills/mcp-server-architect/tools",
)
POLICY_COVERAGE_PATHS = (
    "contracts/*.py",
    "skills/afds-doc-writer/*.py",
    "skills/agents-md-architect/tools/*.py",
    "skills/ci-cd-architect/tools/*.py",
    "skills/mcp-server-consumer/tools/*.py",
)

TARGETS = {
    "quality": QUALITY_PATHS,
    "typing": TYPE_PATHS,
    "bandit": BANDIT_PATHS,
    "policy-coverage": POLICY_COVERAGE_PATHS,
}


def render_target(name: str) -> str:
    """Render one target list for shell consumption."""
    values = TARGETS[name]
    return ",".join(values) if name == "policy-coverage" else " ".join(values)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=tuple(TARGETS))
    args = parser.parse_args(argv)
    print(render_target(args.target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

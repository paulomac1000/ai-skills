from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"


def _semver_is_accepted(value: str) -> bool:
    process = subprocess.run(
        [
            sys.executable,
            str(ROOT / "skills/mcp-server-architect/tools/compare_mcp_contracts.py"),
            "--validate-version",
            value,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return process.returncode == 0


def test_protocol_profile_uses_one_current_revision() -> None:
    profile = (SKILLS / "mcp-server-architect/references/protocol-and-sdk-compatibility.md").read_text(encoding="utf-8")
    assert "2026-07-28" in profile
    assert "2025-11-25" in profile
    assert "current revision" in profile.casefold()


def test_python_profile_routes_official_sdk_and_fastmcp_package_separately() -> None:
    manifest = (SKILLS / "mcp-server-architect/manifest.yaml").read_text(encoding="utf-8")
    official = (SKILLS / "mcp-server-architect/references/python-official-mcp-sdk.md").read_text(encoding="utf-8")
    fastmcp = (SKILLS / "mcp-server-architect/references/python-fastmcp-package.md").read_text(encoding="utf-8")
    assert "python-official-mcp" in manifest
    assert "python-fastmcp-package" in manifest
    assert "mcp" in official.casefold()
    assert "fastmcp" in fastmcp.casefold()


def test_migration_plan_distinguishes_discovery_from_acceptance() -> None:
    source = (SKILLS / "mcp-server-architect/tools/plan_existing_project.py").read_text(encoding="utf-8")
    assert '"provider_verification": "not-evaluated"' in source
    assert '"acceptance": "not-evaluated"' in source


def test_public_contract_compare_is_semver_aware() -> None:
    script = ROOT / "contracts/mcp_public_contract.py"
    namespace: dict[str, object] = {}
    exec(compile(script.read_text(encoding="utf-8"), str(script), "exec"), namespace)
    compare = namespace["compare_contracts"]
    old = {
        "schema_version": 1,
        "server_version": "1.0.0",
        "protocol_revision": "2026-07-28",
        "transports": ["stdio"],
        "tools": [
            {
                "name": "read",
                "description": "read",
                "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
                "output_schema": {"type": "object", "properties": {}, "additionalProperties": False},
                "error_contract": ["INTERNAL"],
            }
        ],
    }
    new = json.loads(json.dumps(old))
    new["server_version"] = "2.0.0"
    new["tools"] = []
    result = compare(old, new)
    assert result["required_bump"] == "major"


def test_stable_semver_examples_are_canonical() -> None:
    for version in (
        "0.0.0",
        "1.2.3",
        "1.2.3-alpha",
        "1.2.3-alpha.1",
        "1.2.3+build.5",
        "1.2.3-alpha.1+build.5",
    ):
        assert _semver_is_accepted(version), version

    for version in (
        "01.2.3",
        "1.02.3",
        "1.2.03",
        "1.2.3-01",
        "1.2.3-alpha.01",
        "1.2.3-alpha..1",
        "1.2.3+build..1",
        "1.2",
        "1.2.3/evil",
        "1.2.3 alpha",
    ):
        assert not _semver_is_accepted(version), version


def test_target_authorization_precedes_network_resolution_in_normative_docs() -> None:
    transport = (ROOT / "skills/mcp-server-architect/references/transport-lifecycle-and-conformance.md").read_text(
        encoding="utf-8"
    )
    simulation = (ROOT / "skills/mcp-server-architect/references/dotnet-migration-simulation.md").read_text(
        encoding="utf-8"
    )

    assert "authorize the selector namespace or tenant before any discovery or lookup" in transport
    assert "failed preliminary authorization must produce no network-backed target probe" in transport
    assert "authorize its device namespace before discovery" in simulation
    assert "unauthorized selector and prove the resolver performs no network-backed discovery" in simulation
    assert "Authorization occurs after target resolution" not in transport


def test_dotnet_approval_capacity_check_is_serialized() -> None:
    source = (
        ROOT / "skills/mcp-server-architect/tools/dotnet-template/src/"
        "__NAMESPACE__.Mcp.Server/ApprovalRegistry.cs.template"
    ).read_text(encoding="utf-8")
    lock_index = source.index("lock (_gate)")
    count_index = source.index("_records.Count >= MaximumRecords")
    add_index = source.index("_records.TryAdd(token, record)")
    assert lock_index < count_index < add_index
    assert "while (true)" in source


def test_dotnet_smoke_rejects_unknown_mode_and_retries_probe_timeout() -> None:
    source = (
        ROOT / "skills/mcp-server-architect/tools/dotnet-template/tests/__NAMESPACE__.Mcp.Smoke/Program.cs.template"
    ).read_text(encoding="utf-8")
    assert 'args.Length == 2 && !string.Equals(args[1], "--http", StringComparison.Ordinal)' in source
    assert "if (args.Length == 2)" in source
    assert "args.Contains(" not in source
    assert "catch (HttpRequestException)" in source
    assert "catch (OperationCanceledException)" in source


def test_run_evidence_command_uses_bounded_process_tree_termination() -> None:
    source = (ROOT / "contracts/run_evidence_command.py").read_text(encoding="utf-8")
    assert "start_new_session=True" in source or "CREATE_NEW_PROCESS_GROUP" in source
    assert "_terminate_process_tree" in source


def test_trusted_authority_files_are_bound_to_tracked_head_bytes() -> None:
    source = (ROOT / "contracts/validate_trusted_executable_sources.py").read_text(encoding="utf-8")
    assert '"ls-files", "--error-unmatch"' in source
    assert '"status", "--porcelain=v1"' in source


def test_release_version_gate_handles_unreachable_base() -> None:
    source = (ROOT / "scripts/check_release_version.py").read_text(encoding="utf-8")
    assert "cannot read base revision" in source


def test_passthrough_control_variable_is_never_forwarded() -> None:
    source = (ROOT / "scripts/ci_environment.py").read_text(encoding="utf-8")
    assert 'part.strip() != "AI_SKILLS_CI_PASSTHROUGH"' in source


def test_runtime_version_channels_are_rejected() -> None:
    source = (ROOT / "contracts/validate_operational_claims.py").read_text(encoding="utf-8")
    for marker in ("stable", "rolling", "nightly", "snapshot"):
        assert marker in source


def test_evidence_runner_timeout_fixture_has_startup_headroom() -> None:
    source = (ROOT / "tests/test_post_review_integrity.py").read_text(encoding="utf-8")
    assert '"--timeout-seconds",\n            "5"' in source


def test_missing_provider_environment_is_not_inferred_from_incomplete_listing() -> None:
    source = (SKILLS / "ci-cd-architect/tools/check_github_provider_controls.py").read_text(encoding="utf-8")
    assert "total_count" in source
    assert "unverifiable" in source


def test_external_trust_lock_rejects_non_mapping_document() -> None:
    source = (ROOT / "contracts/validate_external_trust_lock.py").read_text(encoding="utf-8")
    assert "candidate trust lock must contain a mapping" in source


def test_consumer_feedback_owner_reader_maps_file_errors_to_findings() -> None:
    source = (ROOT / "contracts/validate_consumer_feedback.py").read_text(encoding="utf-8")
    assert "UnicodeDecodeError" in source


def test_local_reusable_acceptance_identity_is_supported() -> None:
    workflow = (ROOT / ".github/workflows/consumer-acceptance.yml").read_text(encoding="utf-8")
    assert "github.job_workflow_sha" in workflow
    assert "job.workflow_sha" not in workflow


def test_provider_dispatcher_supplies_bound_candidate_identity() -> None:
    workflow = (ROOT / ".github/workflows/consumer-acceptance-dispatch.yml").read_text(encoding="utf-8")
    assert "candidate_repository" in workflow
    assert "candidate_revision" in workflow


def test_no_current_decision_engine_depends_on_legacy_sibling() -> None:
    current = (SKILLS / "mcp-server-consumer/tools/decision_engine.py").read_text(encoding="utf-8")
    assert "decision_engine_legacy" not in current


@pytest.mark.parametrize(
    "template",
    [
        ROOT / "contracts/conformance-report.yaml.template",
        ROOT / "contracts/ai-skills.lock.yaml.template",
    ],
)
def test_current_contract_templates_do_not_hardcode_stale_mcp_version(template: Path) -> None:
    text = template.read_text(encoding="utf-8")
    assert "1.2.0" not in text

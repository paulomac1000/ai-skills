"""Regression coverage for the post-1.2.0 contract consistency hardening."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _render_publish() -> str:
    text = (ROOT / "skills/ci-cd-architect/templates/publish.yml.template").read_text(encoding="utf-8")
    replacements = {
        "<TIMEOUT_MINUTES>": "30",
        "<PYTHON_VERSION>": "3.12",
        "<DEPENDENCY_FILE>": "requirements.txt",
        "<INSTALL_COMMAND>": "python -m pip install -r requirements.txt",
        "<TEST_COMMAND>": "python -m pytest",
        "<CONTAINER_SMOKE_COMMAND>": 'docker run --rm "$IMAGE_REF" --help',
        "<RELEASE_ENVIRONMENT>": "production-release",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def test_publish_template_passes_its_declared_policy_profile(tmp_path: Path) -> None:
    tools = ROOT / "skills/ci-cd-architect/tools"
    sys.path.insert(0, str(tools))
    import check_github_actions_policy_impl as policy

    workflow = tmp_path / "publish.yml"
    workflow.write_text(_render_publish(), encoding="utf-8")

    def reader(path: Path, _root: Path) -> tuple[str | None, str | None]:
        return path.read_text(encoding="utf-8"), None

    findings = policy.audit_workflow(workflow, tmp_path, reader=reader)
    assert findings == [], [finding.message for finding in findings]


def test_publish_template_never_pushes_all_tags_or_builds_in_privileged_job() -> None:
    text = _render_publish()
    document = yaml.safe_load(text)
    publish = document["jobs"]["publish"]
    validate = document["jobs"]["validate-build"]
    assert "docker push --all-tags" not in text
    assert "actions/checkout@" not in str(publish)
    assert publish["needs"] == "validate-build"
    assert validate["outputs"]["release_sha"]


def test_mcp_manifest_keeps_protocol_claims_separate_by_sdk() -> None:
    manifest = yaml.safe_load((ROOT / "skills/mcp-server-architect/manifest.yaml").read_text(encoding="utf-8"))
    profiles = manifest["protocol"]["sdk_profiles"]
    assert manifest["protocol"]["default_revision"] == "2026-07-28"

    python = profiles["python-official-mcp"]
    assert python["current_revision_support"] == "not-claimed"
    assert python["repository_tested_revisions"] == []
    assert python["packages"][0]["verified_baseline_versions"] == ["2.0.0"]

    fastmcp = profiles["python-fastmcp-package"]
    assert fastmcp["generated"] is False
    assert fastmcp["verified_baseline_versions"] == []

    dotnet = profiles["dotnet-official-mcp"]
    assert dotnet["current_revision_support"] == "not-claimed"
    assert dotnet["repository_tested_revisions"] == []
    assert dotnet["verified_baseline_versions"] == ["1.4.1"]
    assert dotnet["upstream_stable_candidate_versions"] == ["2.1.0"]


def test_afds_governance_replaces_basename_exemptions() -> None:
    validator = (ROOT / "skills/afds-doc-writer/validate.py").read_text(encoding="utf-8")
    governance = yaml.safe_load((ROOT / "skills/afds-doc-writer/governance.yaml").read_text(encoding="utf-8"))
    assert "EXEMPT_NAMES" not in validator
    assert governance["default_profile"] == "governed"
    assert any(entry["match"] == "README.md" for entry in governance["documents"])


def test_lightweight_conformance_contract_has_no_provider_identifiers() -> None:
    template = (ROOT / "contracts/conformance-report.yaml.template").read_text(encoding="utf-8")
    assert "run_id:" not in template
    assert "job_id:" not in template
    assert "artifact_id:" not in template
    assert "acceptance_authority:" not in template


def test_closed_literal_runner_matrix_is_accepted(tmp_path: Path) -> None:
    tools = ROOT / "skills/ci-cd-architect/tools"
    sys.path.insert(0, str(tools))
    import check_github_actions_policy_impl as policy

    workflow = tmp_path / "matrix.yml"
    workflow.write_text(
        """# ai-skills-policy-profile: pull-request
name: matrix
on: pull_request
permissions:
  contents: read
concurrency:
  group: matrix
  cancel-in-progress: true
jobs:
  test:
    strategy:
      matrix:
        include:
          - os: ubuntu-24.04
          - os: macos-15
          - os: windows-2025
    runs-on: ${{ matrix.os }}
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          persist-credentials: false
""",
        encoding="utf-8",
    )

    def reader(path: Path, _root: Path) -> tuple[str | None, str | None]:
        return path.read_text(encoding="utf-8"), None

    assert policy.audit_workflow(workflow, tmp_path, reader=reader) == []


def test_repository_workflow_passes_declared_policy() -> None:
    tools = ROOT / "skills/ci-cd-architect/tools"
    sys.path.insert(0, str(tools))
    from check_github_actions_policy import audit_repository

    findings = audit_repository(ROOT)
    assert findings == [], [finding.render() for finding in findings]


def test_protected_release_write_job_rejects_checkout(tmp_path: Path) -> None:
    tools = ROOT / "skills/ci-cd-architect/tools"
    sys.path.insert(0, str(tools))
    import check_github_actions_policy_impl as policy

    workflow = tmp_path / "unsafe-release.yml"
    workflow.write_text(
        """# ai-skills-policy-profile: protected-release
name: unsafe
on: workflow_dispatch
permissions:
  contents: read
concurrency:
  group: unsafe
  cancel-in-progress: false
jobs:
  validate:
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    steps:
      - run: echo validated
  publish:
    needs: validate
    environment: production
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          persist-credentials: false
""",
        encoding="utf-8",
    )

    def reader(path: Path, _root: Path) -> tuple[str | None, str | None]:
        return path.read_text(encoding="utf-8"), None

    findings = policy.audit_workflow(workflow, tmp_path, reader=reader)
    assert any("must not execute repository source" in item.message for item in findings)


def test_trusted_auditor_template_executes_external_immutable_verifier() -> None:
    text = (ROOT / "skills/ci-cd-architect/templates/trusted-workflow-audit.yml.template").read_text(encoding="utf-8")
    assert "workflow_call:" in text
    assert "<TRUSTED_VERIFIER_REPOSITORY>" in text
    assert "<TRUSTED_VERIFIER_SHA>" in text
    assert "trusted-verifier/skills/ci-cd-architect/tools/check_github_actions_policy.py" in text
    assert "candidate/skills/ci-cd-architect/tools/check_github_actions_policy.py" not in text


def test_protocol_sdk_versions_match_committed_dependency_contracts() -> None:
    manifest = yaml.safe_load((ROOT / "skills/mcp-server-architect/manifest.yaml").read_text(encoding="utf-8"))
    profiles = manifest["protocol"]["sdk_profiles"]
    runtime = (ROOT / "skills/mcp-server-architect/locks/python-runtime.in").read_text(encoding="utf-8")
    packages = (ROOT / "skills/mcp-server-architect/tools/dotnet-template/Directory.Packages.props.template").read_text(
        encoding="utf-8"
    )

    python_package = profiles["python-official-mcp"]["packages"][0]
    python_version = python_package["verified_baseline_versions"][0]
    assert f"mcp=={python_version}" in runtime

    dotnet = profiles["dotnet-official-mcp"]
    dotnet_version = dotnet["verified_baseline_versions"][0]
    assert f'Include="ModelContextProtocol" Version="{dotnet_version}"' in packages
    assert f'Include="ModelContextProtocol.AspNetCore" Version="{dotnet_version}"' in packages
    assert dotnet["upstream_stable_candidate_versions"][0] not in packages


def test_new_conformance_modules_are_in_typing_gate() -> None:
    namespace: dict[str, object] = {}
    source = (ROOT / "scripts/quality_targets.py").read_text(encoding="utf-8")
    exec(compile(source, "scripts/quality_targets.py", "exec"), namespace)
    type_paths = set(namespace["TYPE_PATHS"])
    assert "contracts/render_rule_catalog.py" in type_paths
    assert "contracts/rule_applicability.py" in type_paths
    assert "contracts/validate_conformance.py" in type_paths

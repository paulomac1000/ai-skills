"""Regressions promoted from real downstream adoption feedback."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import yaml

ROOT = Path(__file__).resolve().parents[1]
CI_TOOLS = ROOT / "skills/ci-cd-architect/tools"
AGENTS_TOOLS = ROOT / "skills/agents-md-architect/tools"
CONTRACTS = ROOT / "contracts"


def _load(path: Path, name: str, *extra_paths: Path) -> ModuleType:
    for candidate in (path.parent, *extra_paths):
        if str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_agents_validator_accepts_concrete_directory_reference(tmp_path: Path) -> None:
    validator = _load(AGENTS_TOOLS / "validate_agents_md.py", "agents_real_usage_validator", CONTRACTS)
    (tmp_path / "docs").mkdir()
    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        "# Agent instructions\n\n"
        "## Scope\nThis file governs the repository.\n\n"
        "## Architecture\nKeep architecture boundaries explicit.\n\n"
        "## Commands\nRun `python -m pytest` for tests.\n\n"
        "## Verification\nRun tests and review evidence.\n\n"
        "## Routing\nRead `docs/` when documentation ownership is relevant.\n",
        encoding="utf-8",
    )

    findings = validator.validate_path(agents, repository_root=tmp_path)

    reference_errors = [finding for finding in findings if finding.code.startswith("links.")]
    assert not reference_errors, reference_errors


def test_agents_validator_does_not_treat_placeholder_pattern_as_literal_file(tmp_path: Path) -> None:
    validator = _load(AGENTS_TOOLS / "validate_agents_md.py", "agents_real_usage_pattern_validator", CONTRACTS)
    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        "# Agent instructions\n\n"
        "## Scope\nThis file governs the repository.\n\n"
        "## Architecture\nKeep architecture boundaries explicit.\n\n"
        "## Commands\nRun `python -m pytest` for tests.\n\n"
        "## Verification\nRun tests and review evidence.\n\n"
        "## Routing\nUse `tests/unit/<domain>/` for domain-specific unit tests.\n",
        encoding="utf-8",
    )

    findings = validator.validate_path(agents, repository_root=tmp_path)

    assert not any(finding.code == "links.missing" for finding in findings)


def test_run_classifier_distinguishes_no_runner_from_code_failure() -> None:
    classifier = _load(CI_TOOLS / "classify_github_run_evidence.py", "real_usage_run_classifier")
    failed_run = {"status": "completed", "conclusion": "failure"}

    no_runner = {"jobs": [{"status": "completed", "conclusion": "failure", "runner_id": 0, "steps": []}]}
    executed = {
        "jobs": [
            {
                "status": "completed",
                "conclusion": "failure",
                "runner_id": 42,
                "steps": [{"name": "test", "status": "completed", "conclusion": "failure"}],
            }
        ]
    }

    assert classifier.classify_run(failed_run, no_runner) == "provider-no-runner"
    assert classifier.classify_run(failed_run, executed) == "executed-fail"
    assert classifier.classify_run({"status": "completed", "conclusion": "success"}, no_runner) == "missing-evidence"


def _write_candidate_lock(root: Path, *, repository: str, revision: str) -> str:
    relative = "trusted-executable-sources.lock.yaml"
    document = {
        "schema_version": 1,
        "sources": [
            {
                "id": "ai-skills",
                "role": "auditor",
                "repository": repository,
                "revision": revision,
                "credential_access": "read-only-provider",
                "files": [
                    {
                        "authority_path": "contracts/validate_external_adoption.py",
                        "sha256": "sha256:" + "0" * 64,
                    }
                ],
            }
        ],
    }
    (root / relative).write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return relative


def test_external_trust_binding_rejects_candidate_selected_authority(tmp_path: Path, monkeypatch) -> None:
    validator = _load(
        CONTRACTS / "validate_external_trust_lock.py",
        "real_usage_external_trust_lock",
        CONTRACTS,
    )
    relative = _write_candidate_lock(
        tmp_path,
        repository="candidate/controlled-authority",
        revision="1" * 40,
    )
    lock_text = (tmp_path / relative).read_text(encoding="utf-8")
    monkeypatch.setattr(validator.trusted_sources, "_verify_candidate_identity", lambda *_args: None)
    monkeypatch.setattr(
        validator.trusted_sources,
        "_authority_text",
        lambda *_args, **_kwargs: lock_text,
    )

    findings = validator.validate_external_lock(
        relative,
        candidate_root=tmp_path,
        candidate_repository="consumer/project",
        candidate_revision="3" * 40,
        authority_root=tmp_path,
        source_id="ai-skills",
        expected_repository="trusted/ai-skills",
        expected_revision="2" * 40,
        required_authority_paths=("contracts/validate_external_adoption.py",),
    )

    assert any("repository does not match externally supplied" in finding for finding in findings)
    assert any("revision does not match externally supplied" in finding for finding in findings)


class _FakeGitHubClient:
    def __init__(self, responses: dict[str, tuple[int, object | None, str]]) -> None:
        self.responses = responses

    def get(self, path: str) -> tuple[int, object | None, str]:
        return self.responses.get(path, (404, None, "not found"))


def _provider_candidate(root: Path) -> None:
    workflows = root / ".github/workflows"
    workflows.mkdir(parents=True)
    (root / ".github/workflow-policy.yaml").write_text(
        "schema_version: 1\nworkflows:\n  .github/workflows/release.yml: protected-release\n",
        encoding="utf-8",
    )
    (workflows / "release.yml").write_text(
        "# ai-skills-policy-profile: protected-release\n"
        "name: release\n"
        "on: workflow_dispatch\n"
        "jobs:\n  publish:\n    environment: release\n    runs-on: ubuntu-24.04\n    steps: []\n",
        encoding="utf-8",
    )


def test_provider_preflight_detects_unprotected_default_branch(tmp_path: Path) -> None:
    provider = _load(CI_TOOLS / "check_github_provider_controls.py", "real_usage_provider_preflight", CONTRACTS)
    _provider_candidate(tmp_path)
    client = _FakeGitHubClient(
        {
            "/repos/acme/project": (200, {"default_branch": "main"}, ""),
            "/repos/acme/project/branches/main": (200, {"protected": False}, ""),
            "/repos/acme/project/environments?per_page=100": (200, {"environments": [{"name": "release"}]}, ""),
            "/repos/acme/project/environments/release": (
                200,
                {"protection_rules": [{"type": "required_reviewers"}], "deployment_branch_policy": None},
                "",
            ),
        }
    )

    findings = provider.check_provider_controls(tmp_path, "acme/project", client)

    assert any(finding.state == "misconfigured" and "not protected" in finding.message for finding in findings)


def test_provider_preflight_detects_missing_declared_environment(tmp_path: Path) -> None:
    provider = _load(CI_TOOLS / "check_github_provider_controls.py", "real_usage_provider_environment", CONTRACTS)
    _provider_candidate(tmp_path)
    client = _FakeGitHubClient(
        {
            "/repos/acme/project": (200, {"default_branch": "main"}, ""),
            "/repos/acme/project/branches/main": (200, {"protected": True}, ""),
            "/repos/acme/project/environments?per_page=100": (200, {"environments": []}, ""),
        }
    )

    findings = provider.check_provider_controls(tmp_path, "acme/project", client)

    assert any(
        finding.state == "misconfigured" and "release environment 'release' does not exist" in finding.message
        for finding in findings
    )


def test_provider_preflight_preserves_permission_failure_as_unverifiable(tmp_path: Path) -> None:
    provider = _load(CI_TOOLS / "check_github_provider_controls.py", "real_usage_provider_permissions", CONTRACTS)
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflow-policy.yaml").write_text("schema_version: 1\nworkflows: {}\n", encoding="utf-8")
    client = _FakeGitHubClient(
        {
            "/repos/acme/project": (200, {"default_branch": "main"}, ""),
            "/repos/acme/project/branches/main": (403, None, "forbidden"),
        }
    )

    findings = provider.check_provider_controls(tmp_path, "acme/project", client)

    assert any(finding.state == "unverifiable" and "HTTP 403" in finding.message for finding in findings)


def test_materialized_acceptance_workflow_requires_authority_owned_caller() -> None:
    workflow = (ROOT / ".github/workflows/consumer-acceptance.yml").read_text(encoding="utf-8")
    dispatcher = (ROOT / ".github/workflows/consumer-acceptance-dispatch.yml").read_text(encoding="utf-8")

    assert "${{ github.repository }}" in workflow
    assert "${{ github.sha }}" in workflow
    assert "${{ github.ref_protected }}" in workflow
    assert "${{ job.workflow_repository }}" in workflow
    assert "${{ job.workflow_sha }}" in workflow
    assert "${{ job.workflow_file_path }}" in workflow
    assert "provider-backed acceptance must be orchestrated by the authority repository" in workflow
    assert "contracts/validate_external_trust_lock.py" in workflow
    assert "contracts/validate_external_adoption.py" in workflow
    assert "check_github_provider_controls.py" in workflow
    assert "--expected-repository \"$AUTHORITY_REPOSITORY\"" in workflow
    assert "--expected-revision \"$AUTHORITY_SHA\"" in workflow
    assert "uses: ./.github/workflows/consumer-acceptance.yml" in dispatcher
    assert "AI_SKILLS_CONSUMER_READ_TOKEN" in dispatcher

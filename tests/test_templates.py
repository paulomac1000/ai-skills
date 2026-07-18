"""Static and behavioral safety checks for bundled CI/CD templates."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator

import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "skills/ci-cd-architect/templates"
FULL_SHA = re.compile(r"[0-9a-f]{40}")
REPLACEMENTS = {
    "<TIMEOUT_MINUTES>": "20",
    "<DEFAULT_BRANCH>": "trunk",
    "<PYTHON_VERSION>": "3.13",
    "<DEPENDENCY_FILE>": "requirements-dev.txt",
    "<INSTALL_COMMAND>": "python -m pip install -r requirements-dev.txt",
    "<TYPECHECK_COMMAND>": "python -m mypy src",
    "<SECURITY_COMMAND>": "python -m bandit -r src",
    "<TEST_COMMAND>": "python -m pytest --cov=src --cov-report=xml",
    "<TEST_ARTIFACT_PATH>": "coverage.xml",
    "<MCP_REGISTRATION_TEST_COMMAND>": "python -m pytest tests/test_registration.py",
    "<MCP_CLIENT_TEST_COMMAND>": "python -m pytest tests/test_client.py",
    "<MCP_FAILURE_TEST_COMMAND>": "python -m pytest tests/test_failures.py",
    "<LOCAL_IMAGE_REF>": "local/example:test",
    "<CONTAINER_SMOKE_COMMAND>": "docker run --rm \"$IMAGE_REF\" --health-check",
    "<DOTNET_VERSION>": "10.0.x",
    "<SOLUTION_PATH>": "src/App.sln",
    "<REPORTGENERATOR_VERSION>": "5.4.3",
    "<DOTNET_COVERAGE_COMMAND>": "reportgenerator -reports:TestResults/**/coverage.cobertura.xml -targetdir:coverage-report",
    "<DOTNET_BOUNDED_TEST_COMMAND>": "dotnet test tests/App.UnitTests/App.UnitTests.csproj --configuration Release --no-restore",
    "<PYTHON_COMPILE_PATHS>": "src tests",
    "<RELEASE_ENVIRONMENT>": "production",
    "<DOTNET_RELEASE_IDENTITY_COMMAND>": "echo 'version=1.2.3' >> \"$GITHUB_OUTPUT\"",
    "<DOTNET_PACKAGE_VERIFY_COMMAND>": "test -n \"$(find nupkg -name '*.nupkg' -print -quit)\"",
    "<VALIDATOR_PATH>": "skills/afds-doc-writer/validate.py",
    "<DOC_INSTALL_COMMAND>": "python -m pip install pyyaml",
    "<VALIDATION_COMMAND>": "python skills/afds-doc-writer/validate.py skills",
    "<SEMGREP_RULES>": "p/default p/secrets",
    "<SEMGREP_CRON>": "17 3 * * 2",
}


def workflow_files() -> list[Path]:
    return sorted(TEMPLATES.glob("*.yml.template"))


def render(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    for token, value in REPLACEMENTS.items():
        text = text.replace(token, value)
    missing = sorted(set(re.findall(r"<[A-Z_]+>", text)))
    assert not missing, (path, missing)
    return text


def parse(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(render(path))
    assert isinstance(document, dict), path
    return document


def walk(value: Any) -> Iterator[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def event_map(document: dict[str, Any]) -> dict[str, Any]:
    events = document.get("on", document.get(True))
    assert isinstance(events, dict)
    return events


def uses_values(document: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for node in walk(document):
        if isinstance(node, dict) and "uses" in node:
            assert isinstance(node["uses"], str)
            values.append(node["uses"])
    return values


def test_expected_production_profiles_are_present() -> None:
    names = {path.name for path in workflow_files()}
    assert {
        "ci.yml.template",
        "python-mcp.yml.template",
        "python-container.yml.template",
        "dotnet-ci.yml.template",
        "dotnet-package.yml.template",
        "docs-validation.yml.template",
        "semgrep-pr.yml.template",
        "semgrep-scheduled.yml.template",
        "publish.yml.template",
    }.issubset(names)
    assert (TEMPLATES / "dependabot-multi-ecosystem.yaml.template").exists()
    assert (TEMPLATES / "pre-commit-python.yaml.template").exists()
    assert (TEMPLATES / "pre-commit-dotnet.yaml.template").exists()


def test_all_external_uses_references_are_full_sha_pinned() -> None:
    for path in workflow_files():
        values = uses_values(parse(path))
        assert values, path
        for value in values:
            if value.startswith("./"):
                continue
            assert "@" in value, (path, value)
            action, revision = value.rsplit("@", 1)
            assert action and FULL_SHA.fullmatch(revision), (path, value)


def test_jobs_are_bounded_and_checkout_drops_credentials() -> None:
    for path in workflow_files():
        document = parse(path)
        assert document.get("permissions") == {"contents": "read"}, path
        jobs = document.get("jobs")
        assert isinstance(jobs, dict) and jobs
        for job_name, job in jobs.items():
            assert isinstance(job, dict), (path, job_name)
            timeout = job.get("timeout-minutes")
            assert type(timeout) is int and timeout > 0, (path, job_name)
            for step in job.get("steps") or []:
                if isinstance(step, dict) and str(step.get("uses", "")).startswith("actions/checkout@"):
                    assert step.get("with", {}).get("persist-credentials") is False


def test_default_branch_is_parameterized_where_branch_push_exists() -> None:
    for path in workflow_files():
        source = path.read_text(encoding="utf-8")
        if re.search(r"(?m)^\s+branches:\s*", source):
            assert "branches: [<DEFAULT_BRANCH>]" in source, path


def test_documentation_workflow_tracks_its_own_contract() -> None:
    events = event_map(parse(TEMPLATES / "docs-validation.yml.template"))
    workflow_path = ".github/workflows/documentation.yml"
    assert workflow_path in events["pull_request"]["paths"]
    assert workflow_path in events["push"]["paths"]


def test_publish_builds_once_then_smoke_tests_before_push() -> None:
    document = parse(TEMPLATES / "publish.yml.template")
    jobs = document["jobs"]
    assert jobs["publish"]["needs"] == "validate"
    steps = jobs["publish"]["steps"]

    metadata_index = next(
        i for i, step in enumerate(steps)
        if str(step.get("uses", "")).startswith("docker/metadata-action@")
    )
    build_index = next(
        i for i, step in enumerate(steps)
        if str(step.get("uses", "")).startswith("docker/build-push-action@")
    )
    smoke_index = next(i for i, step in enumerate(steps) if step.get("name") == "Smoke-test exact release image")
    push_index = next(i for i, step in enumerate(steps) if step.get("name") == "Push smoke-tested image tags")
    attest_index = next(
        i for i, step in enumerate(steps)
        if str(step.get("uses", "")).startswith("actions/attest-build-provenance@")
    )
    assert metadata_index < build_index < smoke_index < push_index < attest_index
    build = steps[build_index]
    assert build["with"]["load"] is True
    assert build["with"]["push"] is False
    assert "docker push --all-tags" in steps[push_index]["run"]
    assert jobs["publish"]["steps"][attest_index]["with"]["subject-digest"] == "${{ steps.push.outputs.digest }}"


def test_publish_reuses_validated_revision_and_locates_metadata_by_action() -> None:
    document = parse(TEMPLATES / "publish.yml.template")
    validate = document["jobs"]["validate"]
    publish = document["jobs"]["publish"]
    validate_checkout = next(
        step for step in validate["steps"]
        if str(step.get("uses", "")).startswith("actions/checkout@")
    )
    publish_checkout = next(
        step for step in publish["steps"]
        if str(step.get("uses", "")).startswith("actions/checkout@")
    )
    assert "inputs.release_ref" in validate_checkout["with"]["ref"]
    assert publish_checkout["with"]["ref"] == "${{ needs.validate.outputs.release_sha }}"
    metadata = next(
        step for step in publish["steps"]
        if str(step.get("uses", "")).startswith("docker/metadata-action@")
    )
    tags = metadata["with"]["tags"]
    assert "needs.validate.outputs.release_tag" in tags
    assert "needs.validate.outputs.release_short_sha" in tags
    assert "type=semver" not in tags and "type=sha" not in tags


def test_dotnet_quality_provisions_coverage_and_reports_safely() -> None:
    document = parse(TEMPLATES / "dotnet-ci.yml.template")
    job = document["jobs"]["build-test"]
    assert job["permissions"] == {"actions": "read", "checks": "write", "contents": "read"}
    install = next(step for step in job["steps"] if step.get("name") == "Install pinned ReportGenerator")
    coverage = next(step for step in job["steps"] if step.get("name") == "Generate coverage report")
    reporter = next(step for step in job["steps"] if step.get("name") == "Publish test report")
    assert "--version \"5.4.3\"" in install["run"]
    assert "TestResults/**/coverage.cobertura.xml" in coverage["run"]
    assert "pull_request.head.repo.full_name" in reporter["if"]


def test_dotnet_package_release_uses_one_validated_tag_and_revision() -> None:
    document = parse(TEMPLATES / "dotnet-package.yml.template")
    steps = document["jobs"]["package"]["steps"]
    resolver = next(step for step in steps if step.get("id") == "release_ref")
    checkouts = [step for step in steps if str(step.get("uses", "")).startswith("actions/checkout@")]
    publisher = next(step for step in steps if step.get("name") == "Publish package files")
    release = next(step for step in steps if str(step.get("uses", "")).startswith("softprops/action-gh-release@"))
    assert "refs/tags/$release_tag" in resolver["run"]
    assert checkouts[-1]["with"]["ref"] == "${{ steps.release_ref.outputs.sha }}"
    assert "for package in \"${packages[@]}\"" in publisher["run"]
    assert release["with"]["tag_name"] == "${{ steps.release_ref.outputs.tag }}"
    assert release["with"]["target_commitish"] == "${{ steps.release_ref.outputs.sha }}"


def test_semgrep_manual_baseline_and_fork_upload_are_explicit() -> None:
    document = parse(TEMPLATES / "semgrep-pr.yml.template")
    steps = document["jobs"]["semgrep"]["steps"]
    scan = next(step for step in steps if step.get("name") == "Scan changed code")
    upload = next(step for step in steps if step.get("name") == "Upload SARIF")
    baseline = scan["env"]["SEMGREP_BASELINE_REF"]
    assert "pull_request.base.sha" in baseline
    assert "repository.default_branch" in baseline
    assert "pull_request.head.repo.full_name" in upload["if"]


def test_renovate_manager_matches_action_subpaths_without_changing_dep_name() -> None:
    config = json.loads((ROOT / "renovate.json").read_text(encoding="utf-8"))
    pattern = config["customManagers"][0]["matchStrings"][0].replace("(?<", "(?P<")
    match = re.search(
        pattern,
        "uses: github/codeql-action/upload-sarif@411bbbe57033eedfc1a82d68c01345aa96c737d7 # v4",
    )
    assert match is not None
    assert match.group("depName") == "github/codeql-action"


def test_local_gate_templates_are_parameterized_and_bounded() -> None:
    python_gate = render(TEMPLATES / "pre-commit-python.yaml.template")
    dotnet_gate = render(TEMPLATES / "pre-commit-dotnet.yaml.template")
    assert "compileall -q src tests" in python_gate
    assert "id: dotnet-restore" in dotnet_gate
    assert "tests/App.UnitTests/App.UnitTests.csproj" in dotnet_gate


def test_non_workflow_configuration_templates_parse() -> None:
    for path in sorted(TEMPLATES.glob("*.yaml.template")):
        text = render(path)
        assert yaml.safe_load(text) is not None, path

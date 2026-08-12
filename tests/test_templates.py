"""Static and behavioral safety checks for bundled CI/CD templates."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "skills/ci-cd-architect/templates"
FULL_SHA = re.compile(r"[0-9a-f]{40}")
REPLACEMENTS = {
    "<TIMEOUT_MINUTES>": "20",
    "<FAST_TIMEOUT_MINUTES>": "10",
    "<FULL_TIMEOUT_MINUTES>": "30",
    "<DEFAULT_BRANCH>": "trunk",
    "<PYTHON_VERSION>": "3.13",
    "<DEPENDENCY_FILE>": "requirements-dev-linux-x64-py312.lock",
    "<VERIFIER_LOCK_FILE>": "requirements-dev-linux-x64-py312.lock",
    "<INSTALL_COMMAND>": "python -m pip install --require-hashes -r requirements-dev-linux-x64-py312.lock",
    "<TYPECHECK_COMMAND>": "python -m mypy src",
    "<SECURITY_COMMAND>": "python -m bandit -r src",
    "<TEST_COMMAND>": "python -m pytest --cov=src --cov-report=xml",
    "<FAST_CHECK_COMMAND>": "python -m pytest -q tests/unit",
    "<FULL_CHECK_COMMAND>": "python -m pytest -q",
    "<ARTIFACT_CHECK_COMMAND>": "python -m pytest -q tests/artifact",
    "<TEST_ARTIFACT_PATH>": "coverage.xml",
    "<MCP_REGISTRATION_TEST_COMMAND>": "python -m pytest tests/test_registration.py",
    "<MCP_CLIENT_TEST_COMMAND>": "python -m pytest tests/test_client.py",
    "<MCP_FAILURE_TEST_COMMAND>": "python -m pytest tests/test_failures.py",
    "<LOCAL_IMAGE_REF>": "local/example:test",
    "<CONTAINER_SMOKE_COMMAND>": 'docker run --rm "$IMAGE_REF" --health-check',
    "<QUARANTINE_REGISTRY>": "quarantine.example.invalid",
    "<QUARANTINE_REPOSITORY>": "example/service",
    "<QUARANTINE_USERNAME_SECRET>": "QUARANTINE_USERNAME",
    "<QUARANTINE_PASSWORD_SECRET>": "QUARANTINE_PASSWORD",
    "<QUARANTINE_READ_USERNAME_SECRET>": "QUARANTINE_READ_USERNAME",
    "<QUARANTINE_READ_PASSWORD_SECRET>": "QUARANTINE_READ_PASSWORD",
    "<DOTNET_VERSION>": "10.0.302",
    "<SOLUTION_PATH>": "src/App.sln",
    "<SERVER_PROJECT>": "src/App/App.csproj",
    "<MCP_CONTRACT_TEST_PROJECT>": "tests/App.Mcp.ContractTests/App.Mcp.ContractTests.csproj",
    "<PACKAGED_ARTIFACT_SMOKE_COMMAND>": "dotnet artifacts/server/App.dll --smoke",
    "<SET_EXACT_CANDIDATE_MCP_VERSION_COMMAND>": "python scripts/set-candidate.py",
    "<REPORTGENERATOR_VERSION>": "5.4.3",
    "<DOTNET_COVERAGE_COMMAND>": "reportgenerator -reports:TestResults/**/coverage.cobertura.xml -targetdir:coverage-report",
    "<DOTNET_BOUNDED_TEST_COMMAND>": "dotnet test tests/App.UnitTests/App.UnitTests.csproj --configuration Release --no-restore",
    "<PYTHON_COMPILE_PATHS>": "src tests",
    "<RELEASE_ENVIRONMENT>": "production",
    "<DOTNET_RELEASE_IDENTITY_COMMAND>": 'test "$NORMALIZED_VERSION" = "1.2.3"',
    "<DOTNET_PACKAGE_VERIFY_COMMAND>": "test -n \"$(find nupkg -name '*.nupkg' -print -quit)\"",
    "<DOTNET_PACKAGE_IDS>": "Example.Package",
    "<VALIDATOR_PATH>": "skills/afds-doc-writer/validate.py",
    "<DOC_INSTALL_COMMAND>": "python -m pip install pyyaml",
    "<VALIDATION_COMMAND>": "python skills/afds-doc-writer/validate.py skills",
    "<SEMGREP_RULES>": "p/default p/secrets",
    "<SEMGREP_CRON>": "17 3 * * 2",
    "<TRUSTED_VERIFIER_REPOSITORY>": "paulomac1000/ai-skills",
    "<TRUSTED_VERIFIER_SHA>": "661ff01a5e70d58d6c94a12545b24647e52063ed",
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
        "dotnet-mcp.yml.template",
        "dotnet-package.yml.template",
        "docs-validation.yml.template",
        "semgrep-pr.yml.template",
        "semgrep-scheduled.yml.template",
        "publish.yml.template",
        "trusted-workflow-audit.yml.template",
    }.issubset(names)
    assert (TEMPLATES / "dependabot-multi-ecosystem.yaml.template").exists()
    assert (TEMPLATES / "pre-commit-python.yaml.template").exists()
    assert (TEMPLATES / "pre-commit-dotnet.yaml.template").exists()
    assert (TEMPLATES / "on-demand-ci.yaml.template").exists()


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


def test_every_rendered_workflow_passes_declared_policy_profile(tmp_path: Path) -> None:
    tools = ROOT / "skills/ci-cd-architect/tools"
    sys.path.insert(0, str(tools))
    import check_github_actions_policy as policy

    for source in workflow_files():
        rendered = tmp_path / source.name.removesuffix(".template")
        rendered.write_text(render(source), encoding="utf-8")
        findings = policy.audit_workflow(rendered, tmp_path)
        assert findings == [], (source, [finding.message for finding in findings])


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
                if isinstance(step, dict) and str(step.get("uses", "")).startswith(
                    "actions/checkout@"
                ):
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


def test_publish_builds_smokes_quarantines_and_promotes_exact_digest() -> None:
    document = parse(TEMPLATES / "publish.yml.template")
    validate = document["jobs"]["validate-build"]
    publish = document["jobs"]["publish"]
    assert publish["needs"] == "validate-build"
    validate_steps = validate["steps"]
    build_index = next(
        i for i, step in enumerate(validate_steps) if step.get("name") == "Build release image once"
    )
    smoke_index = next(
        i for i, step in enumerate(validate_steps) if step.get("name") == "Smoke-test local release image"
    )
    quarantine_index = next(
        i for i, step in enumerate(validate_steps) if step.get("id") == "quarantine"
    )
    digest_smoke_index = next(
        i
        for i, step in enumerate(validate_steps)
        if step.get("name") == "Smoke-test exact quarantined digest"
    )
    assert build_index < smoke_index < quarantine_index < digest_smoke_index
    build = validate_steps[build_index]
    assert "docker buildx build --load" in build["run"]
    assert "org.opencontainers.image.revision=$RELEASE_SHA" in build["run"]
    quarantine = validate_steps[quarantine_index]
    assert "docker push" in quarantine["run"]
    assert "imagetools inspect" in quarantine["run"]
    assert "sha256:[0-9a-f]{64}" in quarantine["run"]
    assert validate.get("permissions") is None

    publish_steps = publish["steps"]
    assert not any(
        str(step.get("uses", "")).startswith("actions/checkout@")
        for step in publish_steps
    )
    promote = next(step for step in publish_steps if step.get("id") == "promote")
    assert "imagetools create" in promote["run"]
    assert 'source_ref="${QUARANTINE_REF%:*}@$EXPECTED_DIGEST"' in promote["run"]
    assert 'test "$promoted" = "$EXPECTED_DIGEST"' in promote["run"]
    assert "docker push --all-tags" not in promote["run"]
    attest = next(
        step
        for step in publish_steps
        if str(step.get("uses", "")).startswith("actions/attest-build-provenance@")
    )
    assert attest["with"]["subject-name"] == "${{ steps.promote.outputs.subject_name }}"
    assert attest["with"]["subject-digest"] == "${{ steps.promote.outputs.digest }}"


def test_publish_constrains_revision_and_keeps_candidate_out_of_publisher() -> None:
    document = parse(TEMPLATES / "publish.yml.template")
    validate = document["jobs"]["validate-build"]
    publish = document["jobs"]["publish"]
    checkout = next(
        step
        for step in validate["steps"]
        if str(step.get("uses", "")).startswith("actions/checkout@")
    )
    assert checkout["with"]["fetch-depth"] == 0
    assert checkout["with"]["persist-credentials"] is False
    resolver = next(step for step in validate["steps"] if step.get("id") == "revision")
    assert "git merge-base --is-ancestor" in resolver["run"]
    assert "origin/$DEFAULT_BRANCH" in resolver["run"]
    assert "^[0-9a-f]{40}$" in resolver["run"]
    assert "git checkout --detach" in resolver["run"]
    assert not any(
        str(step.get("uses", "")).startswith("actions/checkout@")
        for step in publish["steps"]
    )
    source = (TEMPLATES / "publish.yml.template").read_text(encoding="utf-8")
    assert "sha-$RELEASE_SHA" in source
    assert "release_short_sha" not in source


def test_dotnet_quality_provisions_coverage_and_reports_safely() -> None:
    document = parse(TEMPLATES / "dotnet-ci.yml.template")
    job = document["jobs"]["build-test"]
    assert job["permissions"] == {
        "actions": "read",
        "checks": "write",
        "contents": "read",
    }
    install = next(
        step for step in job["steps"] if step.get("name") == "Install pinned ReportGenerator"
    )
    coverage = next(
        step for step in job["steps"] if step.get("name") == "Generate coverage report"
    )
    reporter = next(
        step for step in job["steps"] if step.get("name") == "Publish test report"
    )
    assert '--version "5.4.3"' in install["run"]
    assert "TestResults/**/coverage.cobertura.xml" in coverage["run"]
    assert "pull_request.head.repo.full_name" in reporter["if"]


def test_dotnet_mcp_profile_runs_stable_contract_and_isolates_candidate_lane() -> None:
    document = parse(TEMPLATES / "dotnet-mcp.yml.template")
    jobs = document["jobs"]
    stable = jobs["stable-contract"]
    candidate = jobs["candidate-sdk"]
    stable_names = {step.get("name") for step in stable["steps"]}
    assert {
        "Public-client stdio contract",
        "Public-client Streamable HTTP contract",
        "Authorization, catalog, and protocol error contract",
        "Cancellation, shutdown, and task contract",
        "Packaged artifact smoke",
    }.issubset(stable_names)
    assert stable.get("continue-on-error") is not True
    assert candidate["if"] == "github.event_name == 'workflow_dispatch'"
    assert candidate["continue-on-error"] is True
    source = (TEMPLATES / "dotnet-mcp.yml.template").read_text(encoding="utf-8")
    assert "EnableLegacySse" not in source
    assert "WithToolsFromAssembly" not in source


def _embedded_nuget_validator() -> str:
    document = parse(TEMPLATES / "dotnet-package.yml.template")
    step = next(
        step
        for step in document["jobs"]["validate-package"]["steps"]
        if step.get("name") == "Validate exact package identity allowlist"
    )
    run = step["run"]
    marker = "python - <<'PY'\n"
    assert marker in run and run.rstrip().endswith("PY")
    return run.split(marker, 1)[1].rsplit("\nPY", 1)[0]


def _write_nupkg(path: Path, nuspec: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("package.nuspec", nuspec)


def _run_nuget_validator(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["EXPECTED_PACKAGE_IDS"] = "Example.Package"
    env["EXPECTED_VERSION"] = "1.2.3"
    return subprocess.run(
        [sys.executable, "-c", _embedded_nuget_validator()],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_dotnet_package_release_uses_closed_artifact_and_identity_set(tmp_path: Path) -> None:
    document = parse(TEMPLATES / "dotnet-package.yml.template")
    validate = document["jobs"]["validate-package"]
    publish = document["jobs"]["publish"]
    steps = validate["steps"]
    resolver = next(step for step in steps if step.get("id") == "release_ref")
    identity = next(step for step in steps if step.get("id") == "release")
    pack = next(step for step in steps if step.get("name") == "Pack")
    allowlist = next(
        step
        for step in steps
        if step.get("name") == "Validate exact package identity allowlist"
    )
    close = next(step for step in steps if step.get("id") == "close")
    checkouts = [
        step
        for step in steps
        if str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    publish_steps = publish["steps"]
    verify = next(
        step
        for step in publish_steps
        if step.get("name") == "Verify package artifact identity before publication"
    )
    publisher = next(
        step for step in publish_steps if step.get("name") == "Publish package files"
    )
    release = next(
        step
        for step in publish_steps
        if str(step.get("uses", "")).startswith("softprops/action-gh-release@")
    )
    assert "refs/tags/$release_tag" in resolver["run"]
    assert "git merge-base --is-ancestor" in resolver["run"]
    assert checkouts[-1]["with"]["ref"] == "${{ steps.release_ref.outputs.sha }}"
    assert 'normalized_version="${RELEASE_TAG#v}"' in identity["run"]
    assert 'echo "version=$normalized_version"' in identity["run"]
    assert "$NORMALIZED_VERSION" in identity["run"]
    assert "canonical SemVer 2.0" in identity["run"]
    assert pack["env"]["PACKAGE_VERSION"] == "${{ steps.release.outputs.version }}"
    assert '-p:PackageVersion="$PACKAGE_VERSION"' in pack["run"]
    assert allowlist["env"]["EXPECTED_PACKAGE_IDS"] == "Example.Package"
    script = allowlist["run"]
    for required in (
        'direct_child(root, "metadata")',
        'direct_child_text(metadata, "id")',
        'direct_child_text(metadata, "version")',
        "Unexpected PackageId",
        "Missing allowlisted PackageId",
        "publish-files.txt",
    ):
        assert required in script
    assert "root.iter()" not in script
    assert "hashlib.sha256" in close["run"]
    assert '"sha256":' in close["run"]
    assert "hashlib.sha256" in verify["run"]
    assert "release-manifest.json" in verify["run"]
    assert publish["needs"] == "validate-package"
    assert not any(
        str(step.get("uses", "")).startswith("actions/checkout@")
        for step in publish_steps
    )
    assert "mapfile -t packages < nupkg/publish-files.txt" in publisher["run"]
    assert 'for package in "${packages[@]}"' in publisher["run"]
    assert release["with"]["tag_name"] == "${{ needs.validate-package.outputs.release_tag }}"
    assert release["with"]["target_commitish"] == "${{ needs.validate-package.outputs.release_sha }}"

    malicious = """<?xml version="1.0"?><package><metadata><dependencies><group><dependency id="Example.Package" version="1.2.3" /></group></dependencies><id>Malicious.Package</id><version>9.9.9</version></metadata></package>"""
    _write_nupkg(tmp_path / "nupkg/malicious.nupkg", malicious)
    rejected = _run_nuget_validator(tmp_path)
    assert rejected.returncode != 0
    assert "Unexpected PackageId 'Malicious.Package'" in rejected.stderr

    for path in (tmp_path / "nupkg").glob("*"):
        path.unlink()
    valid = """<?xml version="1.0"?><package xmlns="http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd"><metadata><id>Example.Package</id><version>1.2.3</version><dependencies><group><dependency id="Other" version="7.0.0" /></group></dependencies></metadata></package>"""
    _write_nupkg(tmp_path / "nupkg/valid.nupkg", valid)
    accepted = _run_nuget_validator(tmp_path)
    assert accepted.returncode == 0, accepted.stderr
    assert (tmp_path / "nupkg/publish-files.txt").read_text(encoding="utf-8") == (
        "nupkg/valid.nupkg\n"
    )


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

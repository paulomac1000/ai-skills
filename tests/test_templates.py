from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "skills/ci-cd-architect/templates"


class GitHubWorkflowLoader(yaml.SafeLoader):
    pass


for first_char, resolvers in list(GitHubWorkflowLoader.yaml_implicit_resolvers.items()):
    GitHubWorkflowLoader.yaml_implicit_resolvers[first_char] = [
        resolver
        for resolver in resolvers
        if resolver[0] != "tag:yaml.org,2002:bool" or first_char not in "OoYyNn"
    ]


def parse(path: Path) -> dict:
    rendered = (
        path.read_text(encoding="utf-8")
        .replace("<PYTHON_VERSION>", "3.12")
        .replace("<DOTNET_VERSION>", "10.0.x")
        .replace("<DEPENDENCY_FILE>", "requirements-dev.txt")
        .replace("<INSTALL_COMMAND>", "python -m pip install -r requirements-dev.txt")
        .replace("<TEST_COMMAND>", "python -m pytest")
        .replace("<MCP_CONFORMANCE_COMMAND>", "python -m pytest tests/test_mcp.py")
        .replace("<MCP_STDIO_COMMAND>", "python -m pytest tests/test_stdio.py")
        .replace("<CONTAINER_SMOKE_COMMAND>", "docker run --rm example:test")
        .replace("<PACKAGE_PROJECT>", "src/Package/Package.csproj")
        .replace("<SMOKE_PROJECT>", "tests/Package.Smoke/Package.Smoke.csproj")
        .replace("<PACKAGE_ID>", "Package.Id")
        .replace("<RELEASE_ENVIRONMENT>", "package-release")
        .replace("<TIMEOUT_MINUTES>", "20")
        .replace("<DOCS_VALIDATION_COMMAND>", "python docs/validate.py")
        .replace("<SEMGREP_CONFIG>", "p/default")
        .replace("<PACKAGE_SOURCE>", "https://api.nuget.org/v3/index.json")
        .replace("<PACKAGE_API_KEY_SECRET>", "NUGET_API_KEY")
        .replace("<PACKAGE_ARTIFACT_NAME>", "package-artifacts")
        .replace("<PACKAGE_RETENTION_DAYS>", "14")
    )
    document = yaml.load(rendered, Loader=GitHubWorkflowLoader)
    assert isinstance(document, dict)
    return document


def test_all_workflow_templates_parse_after_rendering() -> None:
    for path in sorted(TEMPLATES.glob("*.yml.template")):
        document = parse(path)
        assert document.get("name"), path
        assert document.get("on"), path
        assert document.get("jobs"), path


def test_action_references_are_full_shas() -> None:
    action_pattern = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
    for path in sorted(TEMPLATES.glob("*.yml.template")):
        document = parse(path)
        for job in document["jobs"].values():
            for step in job.get("steps", []):
                uses = step.get("uses")
                if uses:
                    assert action_pattern.match(uses), (path, uses)


def test_every_template_job_has_timeout() -> None:
    for path in sorted(TEMPLATES.glob("*.yml.template")):
        document = parse(path)
        for job_name, job in document["jobs"].items():
            assert job.get("timeout-minutes"), (path, job_name)


def test_checkout_disables_persisted_credentials() -> None:
    for path in sorted(TEMPLATES.glob("*.yml.template")):
        document = parse(path)
        for job in document["jobs"].values():
            for step in job.get("steps", []):
                uses = str(step.get("uses", ""))
                if uses.startswith("actions/checkout@"):
                    assert step.get("with", {}).get("persist-credentials") is False


def test_pr_templates_are_read_only_and_do_not_use_secrets() -> None:
    for path in sorted(TEMPLATES.glob("*.yml.template")):
        document = parse(path)
        events = document.get("on", {})
        if isinstance(events, dict) and "pull_request" in events:
            permissions = document.get("permissions", {})
            assert permissions == {"contents": "read"}, path
            assert "secrets." not in path.read_text(encoding="utf-8"), path


def test_uploads_define_retention_and_missing_file_policy() -> None:
    for path in sorted(TEMPLATES.glob("*.yml.template")):
        document = parse(path)
        for job in document["jobs"].values():
            for step in job.get("steps", []):
                uses = str(step.get("uses", ""))
                if uses.startswith("actions/upload-artifact@"):
                    with_block = step.get("with", {})
                    assert with_block.get("retention-days")
                    assert with_block.get("if-no-files-found") in {"error", "warn", "ignore"}


def test_dotnet_package_template_has_tag_derived_version_and_protected_publish() -> None:
    document = parse(TEMPLATES / "dotnet-package.yml.template")
    assert set(document["on"]) == {"push", "workflow_dispatch"}
    publish = document["jobs"]["publish"]
    assert publish["environment"] == "package-release"
    assert publish["permissions"] == {"contents": "read"}
    publish_text = yaml.safe_dump(publish)
    assert "NUGET_API_KEY" in publish_text
    assert "dotnet nuget push" in publish_text
    assert "--skip-duplicate" not in publish_text
    assert "refs/tags/v" in yaml.safe_dump(document["jobs"]["validate"])


def test_dotnet_package_template_builds_manifest_from_exact_discovered_files() -> None:
    document = parse(TEMPLATES / "dotnet-package.yml.template")
    validate_steps = document["jobs"]["validate"]["steps"]
    metadata_step = next(step for step in validate_steps if step.get("id") == "metadata")
    package_step = next(step for step in validate_steps if step.get("id") == "packages")
    assert "printf '%s\\n' \"$packages\"" not in package_step["run"]
    assert "find artifacts/package -maxdepth 1 -type f" in package_step["run"]
    assert "sort -z" in package_step["run"]
    assert "mapfile -d ''" in package_step["run"]
    assert "package_manifest.tsv" in package_step["run"]
    assert "sha256sum" in package_step["run"]
    assert "wc -c" in package_step["run"]
    assert "PACKAGE_MANIFEST_PATH" in metadata_step["run"]
    assert "artifact_count" in metadata_step["run"]
    assert "artifact_total_bytes" in metadata_step["run"]


def test_dotnet_package_template_rejects_additional_or_spoofed_identity() -> None:
    document = parse(TEMPLATES / "dotnet-package.yml.template")
    metadata_step = next(
        step for step in document["jobs"]["validate"]["steps"] if step.get("id") == "metadata"
    )
    script = metadata_step["run"]
    assert "package/metadata/id" in script
    assert "package/metadata/version" in script
    assert "local-name()" not in script
    assert "package/*[local-name()='metadata']" not in script
    assert "package/metadata/*[local-name()='id']" not in script
    assert "package/metadata/*[local-name()='version']" not in script
    assert "count(//*[local-name()='metadata'])" in script
    assert "count(//*[local-name()='id'])" in script
    assert "count(//*[local-name()='version'])" in script
    assert "count(package/metadata/id)" in script
    assert "count(package/metadata/version)" in script
    assert "package/metadata/id/text()" in script
    assert "package/metadata/version/text()" in script
    assert "normalize-space(package/metadata/id/text())" in script
    assert "normalize-space(package/metadata/version/text())" in script
    assert 'metadata_id="$direct_id"' in script
    assert 'metadata_version="$direct_version"' in script
    assert "Package identity is not uniquely declared" in script


def test_publish_template_validates_then_smokes_and_pushes_same_local_image() -> None:
    document = parse(TEMPLATES / "publish.yml.template")
    jobs = document["jobs"]
    assert set(jobs) == {"validate", "publish"}
    steps = jobs["publish"]["steps"]
    metadata_index = next(
        i for i, step in enumerate(steps) if str(step.get("uses", "")).startswith("docker/metadata-action@")
    )
    build_index = next(
        i for i, step in enumerate(steps) if str(step.get("uses", "")).startswith("docker/build-push-action@")
    )
    smoke_index = next(i for i, step in enumerate(steps) if step.get("name") == "Smoke-test exact release image")
    push_index = next(i for i, step in enumerate(steps) if step.get("name") == "Push smoke-tested image tags")
    attest_index = next(
        i
        for i, step in enumerate(steps)
        if str(step.get("uses", "")).startswith("actions/attest-build-provenance@")
    )
    assert metadata_index < build_index < smoke_index < push_index < attest_index
    build = steps[build_index]
    assert build["with"]["load"] is True
    assert build["with"]["push"] is False
    push_script = steps[push_index]["run"]
    assert "docker push --all-tags" not in push_script
    assert "while IFS= read -r image_tag" in push_script
    assert 'docker push "$image_tag"' in push_script
    assert 'done <<< "$IMAGE_TAGS"' in push_script
    assert jobs["publish"]["steps"][attest_index]["with"]["subject-digest"] == "${{ steps.push.outputs.digest }}"


def test_publish_reuses_validated_revision_and_locates_metadata_by_action() -> None:
    document = parse(TEMPLATES / "publish.yml.template")
    validate = document["jobs"]["validate"]
    publish = document["jobs"]["publish"]
    validate_checkout = next(
        step for step in validate["steps"] if str(step.get("uses", "")).startswith("actions/checkout@")
    )
    publish_checkout = next(
        step for step in publish["steps"] if str(step.get("uses", "")).startswith("actions/checkout@")
    )
    assert validate_checkout["with"]["fetch-depth"] == 0
    assert publish_checkout["with"]["ref"] == "${{ needs.validate.outputs.release_sha }}"
    revision = next(step for step in validate["steps"] if step.get("id") == "revision")
    assert "git rev-parse HEAD" in revision["run"]
    assert "refs/tags/$release_tag^{commit}" in revision["run"]


def test_dependabot_multi_ecosystem_template_is_valid() -> None:
    document = yaml.safe_load(
        (TEMPLATES / "dependabot-multi-ecosystem.yaml.template")
        .read_text(encoding="utf-8")
        .replace("<DEFAULT_BRANCH>", "main")
    )
    updates = document["updates"]
    assert {update["package-ecosystem"] for update in updates} == {"pip", "github-actions"}
    assert all(update["target-branch"] == "main" for update in updates)

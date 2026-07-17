"""Static safety checks for bundled workflow templates."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "skills/ci-cd-architect/templates"
ACTION = re.compile(r"uses:\s*([^\s@]+)@([^\s#]+)")
FULL_SHA = re.compile(r"[0-9a-f]{40}")
REPLACEMENTS = {
    "<TIMEOUT_MINUTES>": "15",
    "<PYTHON_VERSION>": "3.12",
    "<INSTALL_COMMAND>": "python -m pip install -r requirements.txt",
    "<TEST_COMMAND>": "python -m pytest",
    "<DOTNET_VERSION>": "10.0.x",
    "<SOLUTION_PATH>": "src/App.sln",
    "<VALIDATOR_PATH>": "scripts/validate.py",
    "<VALIDATION_COMMAND>": "python scripts/validate.py",
    "<DEFAULT_BRANCH>": "trunk",
    "<DEPENDENCY_FILE>": "requirements.txt",
    "<RELEASE_ENVIRONMENT>": "production",
}


def template_files() -> list[Path]:
    """Return all supported workflow templates."""
    return sorted(TEMPLATES.glob("*.yml.template"))


def render(path: Path) -> str:
    """Render neutral placeholders with deterministic test values."""
    rendered = path.read_text(encoding="utf-8")
    for token, value in REPLACEMENTS.items():
        rendered = rendered.replace(token, value)
    assert not re.search(r"<[A-Z_]+>", rendered)
    return rendered


def parse(path: Path) -> dict[str, Any]:
    """Return one rendered workflow mapping."""
    document = yaml.safe_load(render(path))
    assert isinstance(document, dict)
    return document


def test_expected_templates_are_present() -> None:
    assert {path.name for path in template_files()} == {
        "ci.yml.template",
        "docs-validation.yml.template",
        "dotnet-ci.yml.template",
        "publish.yml.template",
    }


def test_third_party_actions_are_pinned_to_full_commits() -> None:
    for path in template_files():
        matches = ACTION.findall(path.read_text(encoding="utf-8"))
        assert matches, path
        for _, revision in matches:
            assert FULL_SHA.fullmatch(revision), (path, revision)


def test_each_job_has_timeout_and_each_checkout_drops_credentials() -> None:
    for path in template_files():
        document = parse(path)
        assert document.get("permissions") == {"contents": "read"}
        jobs = document.get("jobs")
        assert isinstance(jobs, dict) and jobs
        for job_name, job in jobs.items():
            assert isinstance(job, dict), (path, job_name)
            timeout = job.get("timeout-minutes")
            assert type(timeout) is int and timeout > 0, (path, job_name)
            steps = job.get("steps") or []
            for step in steps:
                if isinstance(step, dict) and str(step.get("uses", "")).startswith(
                    "actions/checkout@"
                ):
                    assert step.get("with", {}).get("persist-credentials") is False


def test_templates_render_to_valid_yaml() -> None:
    for path in template_files():
        assert isinstance(parse(path), dict)


def test_default_branch_is_parameterized() -> None:
    for name in ("ci.yml.template", "docs-validation.yml.template", "dotnet-ci.yml.template"):
        text = (TEMPLATES / name).read_text(encoding="utf-8")
        assert "branches: [<DEFAULT_BRANCH>]" in text
        assert "branches: [main]" not in text


def test_documentation_workflow_changes_trigger_both_paths() -> None:
    document = parse(TEMPLATES / "docs-validation.yml.template")
    events = document.get("on", document.get(True))
    assert isinstance(events, dict)
    workflow_path = ".github/workflows/documentation.yml"
    assert workflow_path in events["pull_request"]["paths"]
    assert workflow_path in events["push"]["paths"]


def test_publish_validates_and_reuses_the_exact_revision() -> None:
    document = parse(TEMPLATES / "publish.yml.template")
    jobs = document["jobs"]
    assert jobs["publish"]["needs"] == "validate"
    assert jobs["publish"]["environment"] == "production"
    assert jobs["publish"]["permissions"]["contents"] == "read"
    validate_steps = jobs["validate"]["steps"]
    publish_steps = jobs["publish"]["steps"]
    validate_checkouts = [
        step for step in validate_steps
        if str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    publish_checkouts = [
        step for step in publish_steps
        if str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    assert len(validate_checkouts) == 1
    assert len(publish_checkouts) == 1
    validate_checkout = validate_checkouts[0]
    publish_checkout = publish_checkouts[0]
    assert "inputs.release_ref" in validate_checkout["with"]["ref"]
    assert publish_checkout["with"]["ref"] == "${{ needs.validate.outputs.release_sha }}"
    outputs = jobs["validate"]["outputs"]
    assert outputs["release_sha"] == "${{ steps.revision.outputs.sha }}"
    assert outputs["release_short_sha"] == "${{ steps.revision.outputs.short_sha }}"
    assert outputs["release_tag"] == "${{ steps.revision.outputs.tag }}"
    metadata_tags = jobs["publish"]["steps"][3]["with"]["tags"]
    assert "needs.validate.outputs.release_tag" in metadata_tags
    assert "needs.validate.outputs.release_short_sha" in metadata_tags
    assert "type=semver" not in metadata_tags
    assert "type=sha" not in metadata_tags

    revision_index = next(
        index for index, step in enumerate(validate_steps) if step.get("id") == "revision"
    )
    install_index = next(
        index for index, step in enumerate(validate_steps)
        if step.get("run") == "python -m pip install -r requirements.txt"
    )
    test_index = next(
        index for index, step in enumerate(validate_steps)
        if step.get("run") == "python -m pytest"
    )
    verify_index = next(
        index for index, step in enumerate(validate_steps)
        if step.get("name") == "Verify revision was not changed"
    )
    assert revision_index < install_index < test_index < verify_index
    assert validate_steps[verify_index]["env"]["EXPECTED_SHA"] == "${{ steps.revision.outputs.sha }}"

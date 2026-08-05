"""Machine-readable compatibility and adoption contract for every published skill."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from contracts.semver import is_semver

ROOT = Path(__file__).resolve().parents[1]
RELEASE_VERSION = "1.2.0"
RELEASE_MATURITY = "stable"
SUPPORTED_MATURITY = {"experimental", "release-candidate", "stable", "deprecated"}
ALLOWED_OPERATING_SYSTEMS = {"linux", "macos", "windows"}
RUNNER_OPERATING_SYSTEM = {"ubuntu": "linux", "macos": "macos", "windows": "windows"}
RELEASE_TEXT_SUFFIXES = {
    ".cs",
    ".csproj",
    ".example",
    ".in",
    ".j2",
    ".json",
    ".lock",
    ".md",
    ".py",
    ".template",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def load_matrix() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "contracts/compatibility-matrix.yaml").read_text(encoding="utf-8"))


def combination(value: dict[str, Any], lane: str | None = None) -> tuple[str, str, str, str, str]:
    return (
        str(value["operating_system"]),
        str(value["architecture"]),
        str(value["runtime"]),
        str(value["version"]),
        str(lane or value["lane"]),
    )


def _runner_operating_system(runner: str) -> str:
    for prefix, operating_system in RUNNER_OPERATING_SYSTEM.items():
        if runner.startswith(prefix):
            return operating_system
    raise AssertionError(f"unsupported workflow runner: {runner}")


def _setup_python(step_list: list[dict[str, Any]]) -> dict[str, Any]:
    return next(step["with"] for step in step_list if str(step.get("uses", "")).startswith("actions/setup-python@"))


def workflow_combinations(workflow: dict[str, Any]) -> dict[str, set[tuple[str, str, str, str, str]]]:
    jobs = workflow["jobs"]
    python = {
        combination(
            {
                "operating_system": item["operating_system"],
                "architecture": item["architecture"],
                "runtime": "python",
                "version": item["python"],
            },
            "python-compatibility",
        )
        for item in jobs["compatibility-python"]["strategy"]["matrix"]["include"]
    }
    dotnet = {
        combination(
            {
                "operating_system": item["operating_system"],
                "architecture": item["architecture"],
                "runtime": "dotnet",
                "version": item["dotnet"],
            },
            "dotnet-compatibility",
        )
        for item in jobs["dotnet-generator"]["strategy"]["matrix"]["include"]
    }
    container_job = jobs["python-container-artifact"]
    setup = _setup_python(container_job["steps"])
    runner = str(container_job["runs-on"])
    docker = {
        (
            _runner_operating_system(runner),
            str(setup.get("architecture", "x64")),
            "python",
            str(setup["python-version"]),
            "docker-artifact",
        )
    }
    return {
        "python-compatibility": python,
        "dotnet-compatibility": dotnet,
        "docker-artifact": docker,
    }


def test_every_skill_manifest_is_versioned_and_declares_exact_evidenced_combinations() -> None:
    manifests = sorted((ROOT / "skills").glob("*/manifest.yaml"))
    matrix = load_matrix()
    lanes = matrix["lanes"]
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    actual_workflow_combinations = workflow_combinations(workflow)
    assert manifests and matrix["schema_version"] == 2

    for lane_id, lane in lanes.items():
        assert lane["workflow_job"] in workflow["jobs"], lane_id
        assert lane.get("providers") == ["github-actions"], lane_id
        declared = {combination(item, lane_id) for item in lane["combinations"]}
        assert declared == actual_workflow_combinations[lane_id], (
            lane_id,
            declared,
            actual_workflow_combinations[lane_id],
        )

    for path in manifests:
        manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
        directory = path.parent

        assert manifest["schema_version"] == 1, path
        assert manifest["name"] == directory.name, path
        assert is_semver(manifest["version"]), path
        assert manifest["version"] == RELEASE_VERSION, path
        assert manifest["maturity"] in SUPPORTED_MATURITY, path
        assert manifest["maturity"] == RELEASE_MATURITY, path
        assert manifest["skill_format"] == "ai-skills/v1", path
        assert manifest["normative_entrypoint"] == "STANDARD.md", path
        assert (directory / manifest["normative_entrypoint"]).is_file(), path

        compatibility = manifest["compatibility"]
        assert compatibility["agent_contract"] == "tool-capable-instruction-agent", path
        operating_systems = set(compatibility["operating_systems"])
        assert operating_systems and operating_systems <= ALLOWED_OPERATING_SYSTEMS, path

        evidence_lanes = compatibility.get("evidence_lanes")
        assert isinstance(evidence_lanes, list) and evidence_lanes, path
        selected: set[tuple[str, str, str, str, str]] = set()
        for lane_id in evidence_lanes:
            assert lane_id in lanes, (path, lane_id)
            lane = lanes[lane_id]
            assert manifest["name"] in lane["skills"], (path, lane_id)
            selected.update(combination(item, lane_id) for item in lane["combinations"])

        tested = {combination(item) for item in compatibility["tested_combinations"]}
        assert tested and tested <= selected, (path, tested - selected)
        assert {item[0] for item in tested} == operating_systems, path

        declared_runtimes = compatibility.get("runtimes") or {}
        for runtime, specifier in declared_runtimes.items():
            assert isinstance(specifier, str) and specifier, (path, runtime)
            assert any(item[2] == runtime for item in tested), (path, runtime)

        providers = set(compatibility.get("providers") or [])
        if providers:
            covered = {provider for lane_id in evidence_lanes for provider in lanes[lane_id].get("providers", [])}
            assert providers <= covered, (path, providers - covered)

        adoption = manifest["adoption"]
        assert adoption["extension"] in {"generic", "mcp"}, path
        for field in ("template", "validator", "rule_catalog", "rule_map"):
            resource = Path(adoption[field])
            assert not resource.is_absolute() and ".." not in resource.parts, (path, field)
            assert (ROOT / resource).is_file(), (path, field)

        dependencies = manifest["dependencies"]
        assert isinstance(dependencies["skills"], list), path
        assert isinstance(dependencies["tools"], list) and dependencies["tools"], path

        deprecation = manifest["deprecation"]
        assert deprecation["policy"] == "semantic-versioning", path
        assert deprecation["minimum_notice"], path


def test_release_documentation_matches_manifest_version_and_maturity() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    migration_template = yaml.safe_load(
        (ROOT / "skills/mcp-server-architect/templates/migration-assessment.yaml.template").read_text(encoding="utf-8")
    )

    assert f"`{RELEASE_VERSION}`" in readme
    assert f"## {RELEASE_VERSION} - " in changelog
    assert f"maturity: {RELEASE_MATURITY}" in readme
    assert migration_template["skill"]["version"] == RELEASE_VERSION
    assert migration_template["skill"]["maturity"] == RELEASE_MATURITY
    assert f"{RELEASE_VERSION}-" not in readme
    assert f"## {RELEASE_VERSION}-" not in changelog
    assert "production release candidate" not in readme.casefold()
    assert "controlled production pilot" not in readme.casefold()


def test_current_release_prerelease_identity_is_absent_from_published_content() -> None:
    stale_identity = f"{RELEASE_VERSION}-rc."
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.casefold() not in RELEASE_TEXT_SUFFIXES:
            continue
        relative_parts = path.relative_to(ROOT).parts
        if ".git" in relative_parts or "tests" in relative_parts:
            continue
        assert stale_identity not in path.read_text(encoding="utf-8"), path


def test_required_manifest_resources_exist_and_are_relative() -> None:
    for path in sorted((ROOT / "skills").glob("*/manifest.yaml")):
        manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
        for relative in manifest["required"]:
            resource = Path(relative)
            assert not resource.is_absolute(), (path, relative)
            assert ".." not in resource.parts, (path, relative)
            assert (path.parent / relative).is_file(), (path, relative)

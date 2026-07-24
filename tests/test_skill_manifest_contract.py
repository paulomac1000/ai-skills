"""Machine-readable compatibility and adoption contract for every published skill."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from contracts.semver import is_semver

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_MATURITY = {"experimental", "release-candidate", "stable", "deprecated"}
ALLOWED_OPERATING_SYSTEMS = {"linux", "macos", "windows"}


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
    docker = {("linux", "x64", "python", "3.12", "docker-artifact")}
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
        declared = {combination(item, lane_id) for item in lane["combinations"]}
        assert declared == actual_workflow_combinations[lane_id], (lane_id, declared, actual_workflow_combinations[lane_id])

    for path in manifests:
        manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
        directory = path.parent

        assert manifest["schema_version"] == 1, path
        assert manifest["name"] == directory.name, path
        assert is_semver(manifest["version"]), path
        assert manifest["maturity"] in SUPPORTED_MATURITY, path
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


def test_required_manifest_resources_exist_and_are_relative() -> None:
    for path in sorted((ROOT / "skills").glob("*/manifest.yaml")):
        manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
        for relative in manifest["required"]:
            resource = Path(relative)
            assert not resource.is_absolute(), (path, relative)
            assert ".." not in resource.parts, (path, relative)
            assert (path.parent / resource).is_file(), (path, relative)

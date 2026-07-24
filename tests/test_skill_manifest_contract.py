"""Machine-readable compatibility and adoption contract for every published skill."""

from __future__ import annotations

from pathlib import Path

import yaml

from contracts.semver import is_semver

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_MATURITY = {"experimental", "release-candidate", "stable", "deprecated"}
ALLOWED_OPERATING_SYSTEMS = {"linux", "macos", "windows"}


def load_matrix() -> dict:
    return yaml.safe_load((ROOT / "contracts/compatibility-matrix.yaml").read_text(encoding="utf-8"))


def test_every_skill_manifest_is_versioned_and_declares_evidenced_compatibility() -> None:
    manifests = sorted((ROOT / "skills").glob("*/manifest.yaml"))
    matrix = load_matrix()
    lanes = matrix["lanes"]
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    workflow_jobs = workflow["jobs"]
    assert manifests and matrix["schema_version"] == 1

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
        selected = []
        for lane_id in evidence_lanes:
            assert lane_id in lanes, (path, lane_id)
            lane = lanes[lane_id]
            assert manifest["name"] in lane["skills"], (path, lane_id)
            assert lane["workflow_job"] in workflow_jobs, (path, lane_id, lane["workflow_job"])
            selected.append(lane)

        covered_os = {os_name for lane in selected for os_name in lane.get("operating_systems", [])}
        assert operating_systems <= covered_os, (path, operating_systems - covered_os)

        tested_versions = compatibility.get("tested_runtime_versions") or {}
        for runtime, specifier in (compatibility.get("runtimes") or {}).items():
            assert isinstance(specifier, str) and specifier, (path, runtime)
            versions = tested_versions.get(runtime)
            assert isinstance(versions, list) and versions, (path, runtime)
            covered = {version for lane in selected for version in (lane.get("runtimes") or {}).get(runtime, [])}
            assert set(versions) <= covered, (path, runtime, set(versions) - covered)

        providers = set(compatibility.get("providers") or [])
        if providers:
            covered = {provider for lane in selected for provider in lane.get("providers", [])}
            assert providers <= covered, (path, providers - covered)

        adoption = manifest["adoption"]
        assert adoption["extension"] in {"generic", "mcp"}, path
        for field in ("template", "validator", "rule_catalog"):
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

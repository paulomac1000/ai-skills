"""Machine-readable compatibility contract for every published skill."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"0|[1-9]\d*\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
SUPPORTED_MATURITY = {"experimental", "release-candidate", "stable", "deprecated"}


def test_every_skill_manifest_is_versioned_and_declares_compatibility() -> None:
    manifests = sorted((ROOT / "skills").glob("*/manifest.yaml"))
    assert manifests

    for path in manifests:
        manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
        directory = path.parent

        assert manifest["schema_version"] == 1, path
        assert manifest["name"] == directory.name, path
        assert SEMVER.fullmatch(str(manifest["version"])), path
        assert manifest["maturity"] in SUPPORTED_MATURITY, path
        assert manifest["skill_format"] == "ai-skills/v1", path
        assert manifest["normative_entrypoint"] == "STANDARD.md", path
        assert (directory / manifest["normative_entrypoint"]).is_file(), path

        compatibility = manifest["compatibility"]
        assert compatibility["agent_contract"] == "tool-capable-instruction-agent", path
        assert set(compatibility["operating_systems"]) == {"linux", "macos", "windows"}, path

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

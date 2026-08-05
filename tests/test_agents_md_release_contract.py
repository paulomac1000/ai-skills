"""Release and dependency contracts for agents-md-architect."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {"router", "application", "monorepo", "mcp-server", "safety-critical"}


def test_rule_catalog_version_matches_single_repository_release() -> None:
    catalog = yaml.safe_load((ROOT / "contracts/rule-catalog.yaml").read_text(encoding="utf-8"))
    versions = {
        yaml.safe_load(path.read_text(encoding="utf-8"))["version"]
        for path in (ROOT / "skills").glob("*/manifest.yaml")
    }
    assert versions == {catalog["catalog_version"]}


def test_conditional_skill_dependencies_are_known_and_installed() -> None:
    for manifest_path in sorted((ROOT / "skills").glob("*/manifest.yaml")):
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        profiles = (manifest.get("conditional_dependencies") or {}).get("profiles") or {}
        assert set(profiles) <= PROFILES
        for profile, contract in profiles.items():
            skills = contract.get("skills")
            assert isinstance(skills, list) and skills, (manifest_path, profile)
            for skill_name in skills:
                assert (ROOT / "skills" / skill_name / "manifest.yaml").is_file(), (
                    manifest_path,
                    profile,
                    skill_name,
                )


def test_repository_agents_md_passes_published_strict_tools() -> None:
    tools = ROOT / "skills/agents-md-architect/tools"
    validator = subprocess.run(
        [
            sys.executable,
            str(tools / "validate_agents_md.py"),
            "--strict",
            "--repository-root",
            str(ROOT),
            "--layout",
            "single",
            "--profile",
            "application",
            "--language",
            "en",
            str(ROOT / "AGENTS.md"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert validator.returncode == 0, validator.stdout + validator.stderr

    audit = subprocess.run(
        [
            sys.executable,
            str(tools / "audit_agents_md.py"),
            "--strict",
            "--layout",
            "single",
            "--profile",
            "application",
            "--language",
            "en",
            str(ROOT),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert audit.returncode == 0, audit.stdout + audit.stderr

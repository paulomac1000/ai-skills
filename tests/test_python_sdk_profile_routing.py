"""Regression tests for package-identity-based Python MCP profile routing."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/mcp-server-architect"


def test_legacy_python_fastmcp_filename_is_only_a_compatibility_pointer() -> None:
    redirect = (SKILL / "references/python-fastmcp.md").read_text(encoding="utf-8")
    assert "not an SDK profile" in redirect
    assert "python-official-mcp-sdk.md" in redirect
    assert "python-fastmcp-package.md" in redirect
    assert "New documentation must link directly" in redirect


def test_official_and_fastmcp_profiles_have_distinct_package_identity() -> None:
    official = (SKILL / "references/python-official-mcp-sdk.md").read_text(encoding="utf-8")
    fastmcp = (SKILL / "references/python-fastmcp-package.md").read_text(encoding="utf-8")

    assert "distribution is `mcp`" in official
    assert "official `mcp` namespace" in official
    assert "distribution and import namespace are `fastmcp`" in fastmcp
    assert "AuthMiddleware" in fastmcp
    assert "AccessToken" in fastmcp
    assert "Mounted servers" in fastmcp
    assert "does not claim that the official generator emits a FastMCP project" in fastmcp


def test_skill_routes_by_distribution_imports_and_public_api() -> None:
    skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    for required in (
        "distribution name, exact SDK version, import namespace",
        "registration/enumeration APIs",
        "auth context",
        "transport startup API",
        "references/python-official-mcp-sdk.md",
        "references/python-fastmcp-package.md",
        "unsupported-sdk-profile",
        "Route Python by package identity",
    ):
        assert required in skill


def test_manifest_records_profile_support_without_conflating_upstream_and_evidence() -> None:
    manifest = yaml.safe_load((SKILL / "manifest.yaml").read_text(encoding="utf-8"))
    profiles = manifest["protocol"]["sdk_profiles"]

    official = profiles["python-official-mcp"]
    assert official["distribution"] == "mcp"
    assert official["generated"] is True
    assert official["repository_tested_revisions"] == []
    assert official["current_revision_support"] == "not-claimed"

    fastmcp = profiles["python-fastmcp-package"]
    assert fastmcp["distribution"] == "fastmcp"
    assert fastmcp["generated"] is False
    assert fastmcp["verified_baseline_versions"] == []

    dotnet = profiles["dotnet-official-mcp"]
    assert dotnet["verified_baseline_versions"] == ["1.4.1"]
    assert dotnet["upstream_stable_candidate_versions"] == ["2.1.0"]
    assert dotnet["repository_tested_revisions"] == []


def test_python_generator_is_official_mcp_only() -> None:
    pyproject = (SKILL / "tools/python-template/pyproject.toml.template").read_text(encoding="utf-8")
    assert '"mcp==2.0.0"' in pyproject
    assert '"fastmcp' not in pyproject

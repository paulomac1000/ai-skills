"""Static contract tests for recovered MCP server guidance."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/mcp-server-architect"


def text(path: str) -> str:
    return (SKILL / path).read_text(encoding="utf-8")


def test_mcp_standard_contains_recovered_operational_rules() -> None:
    standard = text("STANDARD.md")
    transport = text("references/transport-lifecycle-and-conformance.md")
    official = text("references/python-official-mcp-sdk.md")
    fastmcp = text("references/python-fastmcp-package.md")
    dotnet = text("references/dotnet-mcp-sdk.md")
    combined_python = official + "\n" + fastmcp
    combined = standard + "\n" + transport + "\n" + combined_python + "\n" + dotnet

    for required in (
        "Streamable HTTP",
        "HTTP+SSE",
        "lifespan",
        "cancellation",
        "concurrency",
        "idempotency",
        "pagination",
        "authorization",
        "confused-deputy",
        "official client",
        "exact artifact",
    ):
        assert required.casefold() in combined.casefold(), required

    assert "distribution is `mcp`" in official
    assert "distribution and import namespace are `fastmcp`" in fastmcp
    assert "dependency lock and assessment identify the exact package version" in official
    assert "ModelContextProtocol" in dotnet
    assert "1.4.1" in dotnet


def test_standard_rejects_deprecated_sse_for_new_servers() -> None:
    skill = text("SKILL.md")
    standard = text("STANDARD.md")
    combined = skill + "\n" + standard
    assert "Never add the deprecated two-endpoint HTTP+SSE transport" in skill
    assert "deprecated" in combined.casefold()
    assert "Streamable HTTP" in combined


def test_migration_entrypoint_is_small_and_specialist_references_remain_routable() -> None:
    skill = text("SKILL.md")
    manifest = text("manifest.yaml")
    for required in (
        "references/testing-strategy.md",
        "references/upstream-contract-discovery.md",
    ):
        assert required in skill
    for routed in (
        "references/migration-assessment.md",
        "references/security-and-operations.md",
        "references/python-official-mcp-sdk.md",
        "references/python-fastmcp-package.md",
    ):
        assert routed in manifest
    assert "load other references only when" in skill

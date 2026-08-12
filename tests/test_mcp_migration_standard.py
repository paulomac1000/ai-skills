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
    assert "mcp==2.0.0" in official
    assert "ModelContextProtocol" in dotnet
    assert "1.4.1" in dotnet


def test_standard_rejects_deprecated_sse_for_new_servers() -> None:
    skill = text("SKILL.md")
    standard = text("STANDARD.md")
    combined = skill + "\n" + standard
    assert "Never add the deprecated two-endpoint HTTP+SSE transport" in skill
    assert "deprecated" in combined.casefold()
    assert "Streamable HTTP" in combined


def test_migration_and_testing_references_are_linked_from_skill() -> None:
    skill = text("SKILL.md")
    for required in (
        "references/migration-assessment.md",
        "references/testing-strategy.md",
        "references/security-and-operations.md",
        "references/python-official-mcp-sdk.md",
        "references/python-fastmcp-package.md",
    ):
        assert required in skill

"""Regression contract for migration-derived MCP architecture rules."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "skills/mcp-server-architect"
REFERENCES = MCP / "references"


def read(name: str) -> str:
    return (REFERENCES / name).read_text(encoding="utf-8")


def assert_terms(text: str, required: set[str]) -> None:
    folded = text.casefold()
    missing = {term for term in required if term.casefold() not in folded}
    assert not missing, missing


def test_language_neutral_standard_owns_migration_invariants() -> None:
    text = (MCP / "STANDARD.md").read_text(encoding="utf-8")
    required = {
        "one invocation kernel",
        "Never silently replace an unavailable requested or default target",
        "A single risk label is insufficient",
        "Automatic retry requires all of the following",
        "expected disconnect",
        "bounded executor",
        "component-aware paths",
        "128 bits of entropy",
        "Generated project acceptance",
        "browser profiles are credential stores",
        "configuration-order",
        "Python migration simulation",
        ".NET migration simulation",
        "deprecated two-endpoint HTTP+SSE",
        "before any network-backed target resolution",
        "exclusive no-replace publication",
    }
    assert_terms(text, required)


def test_manifest_contract_rejects_class_wide_optimistic_defaults() -> None:
    text = read("capability-manifests-and-versioning.md")
    assert_terms(
        text,
        {
            "confidentiality",
            "idempotency_mechanism",
            "retry_conditions",
            "concurrency_scope",
            "target_binding",
            "active_state",
            "A write defaults to `idempotent: false`, `retryable: false`, and `concurrent_safe: false`",
            "unknown-outcome state",
            "never falls back silently",
            "authorizes the capability plus selector namespace before network-backed target resolution",
            "revalidates any mutable address-to-identity mapping",
        },
    )


def test_python_profile_covers_real_migration_failure_modes() -> None:
    text = read("python-fastmcp.md")
    assert_terms(
        text,
        {
            "skills/mcp-server-architect/tools/generate_python_server.py",
            "official MCP Python SDK",
            "separately distributed FastMCP package",
            "mcp>=2.0.0,<3",
            "real-client suite",
            "one invocation kernel",
            "threading.local",
            "contextvars.ContextVar",
            "asyncio.to_thread",
            "bounded executor",
            "run_until_complete",
            "default to non-retryable",
            "no-silent-fallback",
            "Path.resolve",
            "bounded task registry",
            "credential store",
            "UI drift",
            "Pagination",
            "ISO 8601",
            "deprecated two-endpoint HTTP+SSE transport from protocol revision 2024-11-05",
            "disabled by default",
            "named legacy clients",
            "owner and removal deadline",
            "authenticates the principal and intended audience",
            "explicit `has_more: false`",
        },
    )


def test_dotnet_profile_covers_executable_sdk_and_host_failure_modes() -> None:
    text = read("dotnet-mcp.md")
    assert_terms(
        text,
        {
            "ModelContextProtocol.AspNetCore",
            "1.4.1",
            "AddAuthorizationFilters",
            "ClaimsPrincipal",
            "authentication before principal-partitioned rate limiting",
            "UseStructuredContent",
            "OutputSchemaType",
            "McpException",
            "WithTools<T>",
            "WithToolsFromAssembly",
            "InheritEnvironmentVariables = false",
            "InMemoryMcpTaskStore",
            "supervised executor",
            "package/metadata/id",
            "official C# MCP client",
            "exact published artifact",
            "EnableLegacySse",
        },
    )


def test_transport_contract_prevents_adapter_policy_drift() -> None:
    text = read("transport-lifecycle-and-conformance.md")
    assert_terms(
        text,
        {
            "One invocation kernel",
            "does not silently select",
            "registration count or successful port binding alone never means ready",
            "public exposure is never sufficient security",
            "asyncio.run",
            "expected disconnect",
            "configured default",
            "deprecated two-endpoint HTTP+SSE",
            "text/event-stream",
            "no protocol-wide removal date",
        },
    )


def test_runtime_boundary_contract_covers_files_tasks_sessions_and_browsers() -> None:
    text = read("runtime-boundaries-and-artifacts.md")
    assert_terms(
        text,
        {
            "Path.is_relative_to",
            "time-of-check/time-of-use",
            "opaque artifact handle",
            "at least 128 bits of entropy",
            "rejects an oversized body before buffering it in full",
            "browser profile contains credentials",
            "profile lock",
            "selector drift",
            "server-level instructions",
            "embedded in another application",
            "do not delete or cancel task records merely because the initiating session disconnected",
            "until terminal completion",
            "before any network-backed discovery",
        },
    )


def test_python_simulation_covers_each_server_archetype() -> None:
    text = read("python-migration-simulation.md")
    headings = {
        "## Archetype A: large read-only aggregator",
        "## Archetype B: heterogeneous local-device controller",
        "## Archetype C: SSH network appliance",
        "## Archetype D: multi-backend privileged administrator",
        "## Archetype E: financial API adapter",
        "## Archetype F: browser automation and interactive sessions",
        "## Cross-cutting ambiguity resolutions",
        "## Migration acceptance checklist",
    }
    assert headings.issubset(set(text.splitlines()))
    assert_terms(
        text,
        {
            "DHCP identity change",
            "failed-default behavior",
            "empty and final pagination pages",
            "configuration import order",
            "ambiguous mutation reconciliation",
            "post-restart verification",
            "secret-cache prohibition",
            "symlink escapes",
            "two-process locking",
            "oversized HTTP bodies",
            "selector drift",
            "Generated code must execute",
        },
    )


def test_dotnet_simulation_covers_distinct_archetypes_and_sdk_boundaries() -> None:
    text = read("dotnet-migration-simulation.md")
    headings = {
        "## Archetype A: read-only aggregator with exports",
        "## Archetype B: physical-device controller",
        "## Archetype C: financial API adapter",
        "## Archetype D: multi-backend SSH administrator",
        "## .NET-specific ambiguity resolutions",
        "## Migration acceptance checklist",
    }
    assert headings.issubset(set(text.splitlines()))
    assert_terms(
        text,
        {
            "ClaimsPrincipal",
            "principal-bound artifact",
            "physical effect",
            "decimal",
            "host-key fingerprint",
            "no silent target fallback",
            "AddAuthorizationFilters",
            "task store is not an executor",
            "legacy HTTP+SSE",
            "official C# MCP client",
        },
    )


def test_testing_strategy_has_executable_migration_evidence() -> None:
    text = read("testing-strategy.md")
    assert_terms(
        text,
        {
            "Generator acceptance",
            "official in-memory MCP client",
            "official C# MCP client",
            "Invocation-kernel parity",
            "prohibition of silent fallback",
            "bounded executor saturation",
            "timeout after the upstream commits a mutation",
            "Filesystem and artifact safety",
            "Task registry",
            "Browser automation",
            "full-final",
            "configuration-order",
            "Archetype migration matrix",
            "stable production SDK lane",
            "direct package/metadata",
            "deprecated legacy HTTP+SSE",
        },
    )

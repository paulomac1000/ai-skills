"""Regression contract for migration-derived MCP architecture rules."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "skills/mcp-server-architect"
REFERENCES = MCP / "references"


def read(name: str) -> str:
    """Read one MCP standard document."""
    return (REFERENCES / name).read_text(encoding="utf-8")


def test_language_neutral_standard_owns_migration_invariants() -> None:
    text = (MCP / "STANDARD.md").read_text(encoding="utf-8")
    required = {
        "one invocation kernel",
        "Never silently replace an unavailable requested or default target",
        "A single risk label is insufficient",
        "Automatic retry requires all of the following",
        "expected disconnect",
        "bounded executor",
        "configuration-order",
        "Python migration simulation",
    }
    assert all(term in text for term in required)


def test_manifest_contract_rejects_class_wide_optimistic_defaults() -> None:
    text = read("capability-manifests-and-versioning.md")
    required = {
        "confidentiality",
        "idempotency_mechanism",
        "retry_conditions",
        "concurrency_scope",
        "target_binding",
        "active_state",
        "A write defaults to `idempotent: false`, `retryable: false`, and `concurrent_safe: false`",
        "unknown-outcome state",
        "never falls back silently",
    }
    assert all(term in text for term in required)


def test_python_profile_covers_real_migration_failure_modes() -> None:
    text = read("python-fastmcp.md")
    required = {
        "official MCP Python SDK",
        "separately distributed FastMCP package",
        "stable official SDK line",
        "pre-release",
        "one invocation kernel",
        "threading.local",
        "contextvars.ContextVar",
        "asyncio.to_thread",
        "bounded executor",
        "run_until_complete",
        "no automatic retry",
        "no-silent-fallback",
        "Pagination",
        "ISO 8601",
    }
    assert all(term in text for term in required)


def test_transport_contract_prevents_adapter_policy_drift() -> None:
    text = read("transport-lifecycle-and-conformance.md")
    required = {
        "One invocation kernel",
        "never falls back silently",
        "tool count or successful port binding alone never means ready",
        "acknowledging public exposure is never sufficient security",
        "does not call `asyncio.run`, `run_until_complete`",
        "expected disconnect",
        "failed-default",
    }
    assert all(term in text for term in required)


def test_simulation_covers_each_python_server_archetype() -> None:
    text = read("python-migration-simulation.md")
    headings = {
        "## Archetype A: large read-only aggregator",
        "## Archetype B: heterogeneous local-device controller",
        "## Archetype C: SSH network appliance",
        "## Archetype D: multi-backend privileged administrator",
        "## Archetype E: financial API adapter",
        "## Cross-cutting ambiguity resolutions",
        "## Migration acceptance checklist",
    }
    assert headings.issubset(set(text.splitlines()))

    regression_terms = {
        "DHCP identity change",
        "failed-default behavior",
        "pagination termination",
        "configuration import order",
        "ambiguous mutation completion",
        "post-restart verification",
        "secret-cache prohibition",
    }
    assert all(term in text for term in regression_terms)


def test_testing_strategy_has_executable_migration_evidence() -> None:
    text = read("testing-strategy.md")
    required = {
        "Invocation-kernel parity",
        "prohibition of silent fallback",
        "bounded executor saturation",
        "commit-then-timeout",
        "full-final",
        "configuration-order",
        "Archetype migration matrix",
        "stable production SDK lane",
    }
    assert all(term in text for term in required)

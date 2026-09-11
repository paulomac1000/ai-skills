"""Deterministic checks for the seven production MCP runtime/API invariants."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

INVARIANTS = (
    "runtime_identity",
    "diagnostic_parity",
    "actionable_preconditions",
    "managed_resource_ownership",
    "durable_async_progress",
    "bounded_results",
    "scoped_health",
)

_REQUIRED_RUNTIME_IDENTITY = {
    "version",
    "source_revision",
    "artifact_digest",
    "config_revision",
    "instance_generation",
}
_REQUIRED_HEALTH_DIMENSIONS = {"process", "transport", "auth", "read", "write", "provider"}


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _truthy_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def evaluate_runtime_api_invariants(design: Mapping[str, object]) -> dict[str, bool]:
    """Return deterministic pass/fail state for each invariant; absent evidence fails closed."""
    runtime = _mapping(design.get("runtime_identity"))
    diagnostics = _mapping(design.get("diagnostics"))
    mutation = _mapping(design.get("mutation"))
    ownership = _mapping(design.get("managed_resource"))
    async_work = _mapping(design.get("async_progress"))
    results = _mapping(design.get("results"))
    health = _mapping(design.get("health"))

    dimensions = health.get("dimensions")
    dimension_set = (
        {item for item in dimensions if isinstance(item, str)}
        if isinstance(dimensions, Sequence) and not isinstance(dimensions, (str, bytes))
        else set()
    )

    governed = ownership.get("governed") is True
    may_outlive = async_work.get("may_outlive_request") is True

    return {
        "runtime_identity": all(_truthy_text(runtime.get(key)) for key in _REQUIRED_RUNTIME_IDENTITY),
        "diagnostic_parity": (
            _truthy_text(diagnostics.get("public_failure_class"))
            and diagnostics.get("public_failure_class") == diagnostics.get("log_failure_class")
            and diagnostics.get("actionable") is True
        ),
        "actionable_preconditions": (
            mutation.get("preconditions_exposed_before_execution") is True
            and mutation.get("reports_all_independent_violations") is True
        ),
        "managed_resource_ownership": (
            not governed
            or (
                ownership.get("raw_mutation_blocked") is True
                and _truthy_text(ownership.get("owner_route"))
            )
        ),
        "durable_async_progress": (
            not may_outlive
            or (
                async_work.get("durable_operation_id") is True
                and async_work.get("status_surface") is True
                and async_work.get("timeout_is_terminal_failure") is False
            )
        ),
        "bounded_results": (
            results.get("default_bounded") is True
            and results.get("partial_marker") is True
            and results.get("continuation") is True
            and results.get("full_detail_opt_in") is True
        ),
        "scoped_health": (
            _REQUIRED_HEALTH_DIMENSIONS.issubset(dimension_set)
            and health.get("freshness_bound") is True
            and health.get("generation_bound") is True
            and health.get("single_green_boolean") is False
        ),
    }


def invariant_violations(design: Mapping[str, object]) -> tuple[str, ...]:
    """Return failed invariant names in canonical order."""
    results = evaluate_runtime_api_invariants(design)
    return tuple(name for name in INVARIANTS if not results[name])

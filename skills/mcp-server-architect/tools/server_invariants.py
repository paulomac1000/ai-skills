"""Deterministic checks for production MCP runtime/API invariants."""

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
    "failure_contract",
    "stream_terminality",
    "unresolved_idempotency",
    "identity_separation",
    "exception_diagnostics",
)

_REQUIRED_RUNTIME_IDENTITY = {
    "version",
    "source_revision",
    "artifact_digest",
    "config_revision",
    "instance_generation",
}
_REQUIRED_HEALTH_DIMENSIONS = {"process", "transport", "auth", "read", "write", "provider"}
_REQUIRED_IDENTITY_ROLES = {"operation", "idempotency", "correlation", "causation", "trace"}
_UNRESOLVED_IDEMPOTENCY_STATES = {
    "in_flight",
    "indeterminate",
    "unknown_outcome",
    "reconcile_required",
}
_TERMINAL_IDEMPOTENCY_STATES = {"completed", "failed_terminal", "cancelled_terminal"}
_DETERMINISTIC_FAILURES = {"invalid_input", "invariant_failure", "policy_failure"}
_TRANSIENT_FAILURES = {"rate_limited", "transient_infrastructure"}
_ALLOWED_RECOVERY_DISPOSITIONS = {
    "retry",
    "wait",
    "reconcile",
    "remediate",
    "block",
    "fail_closed",
    "manual_resolution",
}


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _truthy_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_set(value: object) -> set[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return set()
    return {item for item in value if isinstance(item, str) and item}


def evaluate_runtime_api_invariants(design: Mapping[str, object]) -> dict[str, bool]:
    """Return deterministic pass/fail state for each invariant; absent evidence fails closed."""
    runtime = _mapping(design.get("runtime_identity"))
    diagnostics = _mapping(design.get("diagnostics"))
    mutation = _mapping(design.get("mutation"))
    ownership = _mapping(design.get("managed_resource"))
    async_work = _mapping(design.get("async_progress"))
    results = _mapping(design.get("results"))
    health = _mapping(design.get("health"))
    failure = _mapping(design.get("failure_contract"))
    terminality = _mapping(design.get("stream_terminality"))
    idempotency = _mapping(design.get("idempotency_state"))
    identities = _mapping(design.get("operation_identities"))
    exception_diagnostics = _mapping(design.get("exception_diagnostics"))

    dimension_set = _string_set(health.get("dimensions"))
    identity_roles = _string_set(identities.get("roles"))
    governed = ownership.get("governed") is True
    may_outlive = async_work.get("may_outlive_request") is True
    durability_promised = idempotency.get("durability_promised") is True

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
            or (ownership.get("raw_mutation_blocked") is True and _truthy_text(ownership.get("owner_route")))
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
        "failure_contract": (
            failure.get("stable_machine_failure") is True
            and failure.get("internal_wire_separated") is True
            and failure.get("protocol_native_mapping") is True
            and failure.get("classification_separate_from_recovery") is True
            and failure.get("unknown_defaults_to_retry") is False
        ),
        "stream_terminality": (
            terminality.get("exactly_one_authoritative_terminal") is True
            and terminality.get("eof_without_terminal") == "incomplete_unknown"
            and terminality.get("disconnect_is_terminal") is False
            and terminality.get("post_terminal_progress_rejected") is True
            and terminality.get("conflicting_terminal_rejected") is True
            and terminality.get("wait_cancellation_cancels_work") is False
        ),
        "unresolved_idempotency": (
            idempotency.get("indeterminate_replay_blocking") is True
            and idempotency.get("generic_cleanup_can_clear_unresolved") is False
            and idempotency.get("expiry_becomes_not_seen") is False
            and idempotency.get("completed_vs_unresolved_cleanup_separate") is True
            and (not durability_promised or idempotency.get("restart_preserves_identity") is True)
        ),
        "identity_separation": (
            _REQUIRED_IDENTITY_ROLES.issubset(identity_roles)
            and identities.get("single_identifier_for_all") is False
            and identities.get("explicit_mapping_when_equal") is True
        ),
        "exception_diagnostics": (
            exception_diagnostics.get("trusted_original_cause") is True
            and exception_diagnostics.get("trusted_stack") is True
            and exception_diagnostics.get("public_sanitized") is True
            and exception_diagnostics.get("durable_exception_object") is False
            and exception_diagnostics.get("public_operation_correlated") is True
            and exception_diagnostics.get("raw_forensic_boundary") is True
            and exception_diagnostics.get("ordinary_telemetry_uses_opaque_ref") is True
            and exception_diagnostics.get("diagnostic_failure_policy_explicit") is True
        ),
    }


def invariant_violations(design: Mapping[str, object]) -> tuple[str, ...]:
    """Return failed invariant names in canonical order."""
    results = evaluate_runtime_api_invariants(design)
    return tuple(name for name in INVARIANTS if not results[name])


def classify_progress_sequence(events: Sequence[object]) -> str:
    """Classify one observed progress stream without treating transport end as domain success."""
    terminal: tuple[str, str] | None = None
    for event in events:
        if not isinstance(event, Mapping):
            return "malformed"
        kind = event.get("kind")
        if kind == "progress":
            if terminal is not None:
                return "invalid_post_terminal_progress"
            continue
        if kind == "terminal":
            outcome = event.get("outcome")
            terminal_id = event.get("terminal_id")
            if not _truthy_text(outcome) or not _truthy_text(terminal_id):
                return "malformed"
            current = (str(terminal_id), str(outcome))
            if terminal is None:
                terminal = current
                continue
            if event.get("replay") is True and current == terminal:
                continue
            return "conflicting_terminal"
        if kind in {"eof", "disconnect", "wait_cancelled"}:
            return "complete" if terminal is not None else "incomplete_unknown"
        return "malformed"
    return "complete" if terminal is not None else "incomplete_unknown"


def exception_boundary_is_safe(
    public_failure: Mapping[str, object],
    trusted_diagnostic: Mapping[str, object],
) -> bool:
    """Require trusted exception detail without leaking it into the public failure."""
    operation_id = public_failure.get("operation_id")
    if not _truthy_text(operation_id) or trusted_diagnostic.get("operation_id") != operation_id:
        return False
    if not _truthy_text(public_failure.get("failure_class")):
        return False
    raw_detail_ref = trusted_diagnostic.get("raw_detail_ref")
    if (
        trusted_diagnostic.get("forensic_boundary") is not True
        or not _truthy_text(raw_detail_ref)
        or public_failure.get("diagnostic_ref") != raw_detail_ref
    ):
        return False
    forbidden_public_fields = {"stack", "stack_trace", "cause", "exception", "exception_object"}
    pending: list[object] = [public_failure]
    seen: set[int] = set()
    while pending:
        value = pending.pop()
        if isinstance(value, Mapping):
            identity = id(value)
            if identity in seen:
                continue
            seen.add(identity)
            if forbidden_public_fields.intersection(value):
                return False
            pending.extend(value.values())
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            identity = id(value)
            if identity in seen:
                continue
            seen.add(identity)
            pending.extend(value)
    return _truthy_text(trusted_diagnostic.get("cause")) and _truthy_text(trusted_diagnostic.get("stack"))


def idempotency_state_after_cleanup(state: str, *, cleanup: str = "generic_ttl") -> str:
    """Apply maintenance cleanup without converting unresolved effects into replay permission."""
    if cleanup != "generic_ttl":
        raise ValueError("unsupported cleanup policy")
    if state in _UNRESOLVED_IDEMPOTENCY_STATES:
        return "reconcile_required"
    if state in _TERMINAL_IDEMPOTENCY_STATES:
        return "expired_terminal_record"
    if state == "proven_not_applied":
        return "proven_not_applied"
    raise ValueError("unknown idempotency state")


def replay_is_safe(state: str) -> bool:
    """Return whether current authoritative state proves a new execution is replay-safe."""
    return state == "proven_not_applied"


def recovery_disposition_is_admissible(
    failure_class: str,
    disposition: str,
    *,
    side_effect_ambiguous: bool = False,
    outer_budget_preserved: bool = True,
    policy_bound: bool = True,
) -> bool:
    """Check conservative recovery constraints without making one universal retry policy."""
    if not policy_bound or disposition not in _ALLOWED_RECOVERY_DISPOSITIONS:
        return False
    if side_effect_ambiguous:
        return disposition in {"reconcile", "manual_resolution", "fail_closed"}
    if failure_class == "unknown":
        return disposition in {"block", "manual_resolution", "fail_closed"}
    if failure_class in _DETERMINISTIC_FAILURES:
        return disposition in {"remediate", "block", "fail_closed", "manual_resolution"}
    if failure_class in _TRANSIENT_FAILURES:
        if disposition == "retry":
            return outer_budget_preserved
        return disposition in {"wait", "block", "fail_closed", "manual_resolution"}
    return disposition != "retry"

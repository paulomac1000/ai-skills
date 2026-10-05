"""Regressions for MCP failure, terminality, idempotency, and diagnostic invariants."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills/mcp-server-architect/tools/server_invariants.py"


def _load() -> ModuleType:
    name = "mcp_runtime_failure_contracts"
    spec = importlib.util.spec_from_file_location(name, TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_progress_requires_exactly_one_authoritative_terminal() -> None:
    checks = _load()
    assert checks.classify_progress_sequence([{"kind": "progress"}, {"kind": "eof"}]) == "incomplete_unknown"
    assert checks.classify_progress_sequence([{"kind": "progress"}, {"kind": "disconnect"}]) == "incomplete_unknown"
    assert checks.classify_progress_sequence([{"kind": "wait_cancelled"}]) == "incomplete_unknown"
    assert checks.classify_progress_sequence(
        [{"kind": "progress"}, {"kind": "terminal", "terminal_id": "t1", "outcome": "completed"}]
    ) == "complete"


def test_duplicate_conflicting_and_post_terminal_events_fail_closed() -> None:
    checks = _load()
    terminal = {"kind": "terminal", "terminal_id": "t1", "outcome": "completed"}
    assert checks.classify_progress_sequence([terminal, {"kind": "progress"}]) == "invalid_post_terminal_progress"
    assert checks.classify_progress_sequence(
        [terminal, {"kind": "terminal", "terminal_id": "t2", "outcome": "failed"}]
    ) == "conflicting_terminal"
    assert checks.classify_progress_sequence([terminal, {**terminal, "replay": True}]) == "complete"
    assert checks.classify_progress_sequence([{"kind": "progress"}, "bad-event"]) == "malformed"
    assert checks.classify_progress_sequence([{"kind": "eof"}, terminal]) == "incomplete_unknown"


def test_indeterminate_idempotency_cleanup_never_manufactures_replay_permission() -> None:
    checks = _load()
    for state in ("in_flight", "indeterminate", "unknown_outcome", "reconcile_required"):
        after = checks.idempotency_state_after_cleanup(state)
        assert after == "reconcile_required"
        assert checks.replay_is_safe(after) is False
    assert checks.idempotency_state_after_cleanup("completed") == "expired_terminal_record"
    assert checks.replay_is_safe("proven_not_applied") is True


def test_recovery_disposition_is_separate_from_failure_classification() -> None:
    checks = _load()
    assert checks.recovery_disposition_is_admissible("invalid_input", "retry") is False
    assert checks.recovery_disposition_is_admissible("rate_limited", "retry", outer_budget_preserved=True) is True
    assert checks.recovery_disposition_is_admissible("rate_limited", "retry", outer_budget_preserved=False) is False
    assert checks.recovery_disposition_is_admissible("rate_limited", "wait") is True
    assert checks.recovery_disposition_is_admissible("rate_limited", "invented") is False
    assert (
        checks.recovery_disposition_is_admissible(
            "upstream_timeout",
            "reconcile",
            side_effect_ambiguous=True,
        )
        is True
    )
    assert checks.recovery_disposition_is_admissible("upstream_timeout", "retry", side_effect_ambiguous=True) is False
    assert checks.recovery_disposition_is_admissible("unknown", "retry") is False
    assert checks.recovery_disposition_is_admissible("unknown", "fail_closed") is True


def test_exception_diagnostics_preserve_trusted_cause_without_public_leakage() -> None:
    checks = _load()
    public = {"failure_class": "internal", "operation_id": "op-1", "diagnostic_ref": "forensic:1"}
    trusted = {
        "operation_id": "op-1",
        "cause": "ValueError: boom",
        "stack": "traceback...",
        "forensic_boundary": True,
        "raw_detail_ref": "forensic:1",
    }
    assert checks.exception_boundary_is_safe(public, trusted) is True
    assert checks.exception_boundary_is_safe({**public, "stack": "traceback..."}, trusted) is False
    assert checks.exception_boundary_is_safe({**public, "details": {"cause": "ValueError: boom"}}, trusted) is False
    assert checks.exception_boundary_is_safe({**public, "details": [{"stack_trace": "traceback..."}]}, trusted) is False

    cycle: list[object] = []
    cyclic_public = {**public, "details": cycle}
    cycle.append(cyclic_public)
    assert checks.exception_boundary_is_safe(cyclic_public, trusted) is True

    assert checks.exception_boundary_is_safe(public, {**trusted, "operation_id": "op-2"}) is False
    assert checks.exception_boundary_is_safe(
        public,
        {
            "operation_id": "op-1",
            "cause": "ValueError: boom",
            "forensic_boundary": True,
            "raw_detail_ref": "forensic:1",
        },
    ) is False
    assert checks.exception_boundary_is_safe(
        public,
        {**trusted, "forensic_boundary": False},
    ) is False


def test_static_runtime_contracts_cover_failure_identity_and_exception_boundaries() -> None:
    checks = _load()
    design = {
        "failure_contract": {
            "stable_machine_failure": True,
            "internal_wire_separated": True,
            "protocol_native_mapping": True,
            "classification_separate_from_recovery": True,
            "unknown_defaults_to_retry": False,
        },
        "stream_terminality": {
            "exactly_one_authoritative_terminal": True,
            "eof_without_terminal": "incomplete_unknown",
            "disconnect_is_terminal": False,
            "post_terminal_progress_rejected": True,
            "conflicting_terminal_rejected": True,
            "wait_cancellation_cancels_work": False,
        },
        "idempotency_state": {
            "indeterminate_replay_blocking": True,
            "generic_cleanup_can_clear_unresolved": False,
            "expiry_becomes_not_seen": False,
            "completed_vs_unresolved_cleanup_separate": True,
            "durability_promised": True,
            "restart_preserves_identity": True,
        },
        "operation_identities": {
            "roles": ["operation", "idempotency", "correlation", "causation", "trace"],
            "single_identifier_for_all": False,
            "explicit_mapping_when_equal": True,
        },
        "exception_diagnostics": {
            "trusted_original_cause": True,
            "trusted_stack": True,
            "public_sanitized": True,
            "durable_exception_object": False,
            "public_operation_correlated": True,
            "raw_forensic_boundary": True,
            "ordinary_telemetry_uses_opaque_ref": True,
            "diagnostic_failure_policy_explicit": True,
        },
    }
    result = checks.evaluate_runtime_api_invariants(design)
    for invariant in (
        "failure_contract",
        "stream_terminality",
        "unresolved_idempotency",
        "identity_separation",
        "exception_diagnostics",
    ):
        assert result[invariant] is True

    design["exception_diagnostics"] = {**design["exception_diagnostics"], "public_sanitized": False}
    assert checks.evaluate_runtime_api_invariants(design)["exception_diagnostics"] is False

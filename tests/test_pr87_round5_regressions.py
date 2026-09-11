"""Compound-failure regressions for PR #87 dispatch durability recovery."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR = ROOT / "skills/agent-task-orchestrator/tools/task_orchestrator.py"
EXECUTION_REVISION = "e" * 40


def _load_orchestrator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("task_orchestrator_round5_regressions", ORCHESTRATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _reserve(module: ModuleType, attempts: Path, attempt_id: str):
    reservation = module.reserve_dispatch(
        attempt_store=attempts,
        attempt_id=attempt_id,
        intent_revision=12,
        execution_revision=EXECUTION_REVISION,
    )
    assert reservation.allowed is True
    assert reservation.reservation_token is not None
    return reservation


def _inject_compound_failure(module: ModuleType, attempts: Path, attempt_id: str, monkeypatch):
    original_sync = module._fsync_directory
    original_open = module.os.open
    original_acquire = module._try_acquire_bind_lock
    first_fault_seen = Event()
    recovery_fault_seen = Event()
    observer_lock_attempt = Event()
    release_recovery_fault = Event()
    sync_injected = False
    recovery_injected = False
    record_name = module._attempt_record_path(attempts.resolve(), attempt_id).name

    def fail_once_after_visible_dispatched(path: Path) -> None:
        nonlocal sync_injected
        record_path = module._attempt_record_path(path, attempt_id)
        if not sync_injected and record_path.exists():
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if record.get("state") == "dispatched":
                sync_injected = True
                first_fault_seen.set()
                raise module.OrchestrationError("injected post-replace directory fsync failure")
        original_sync(path)

    def fail_once_before_recovery_replace(path, flags: int, mode: int = 0o777, *, dir_fd=None):
        nonlocal recovery_injected
        candidate = Path(path)
        is_attempt_temp = candidate.name.startswith(f".{record_name}.") and candidate.name.endswith(".tmp")
        if first_fault_seen.is_set() and not recovery_injected and is_attempt_temp:
            recovery_injected = True
            recovery_fault_seen.set()
            assert release_recovery_fault.wait(5), "test observer did not reach the transition lock"
            raise OSError("injected ambiguity-recovery temp-file creation failure")
        if dir_fd is None:
            return original_open(path, flags, mode)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    def observe_lock_attempt(descriptor: int) -> None:
        if recovery_fault_seen.is_set():
            observer_lock_attempt.set()
        original_acquire(descriptor)

    monkeypatch.setattr(module, "_fsync_directory", fail_once_after_visible_dispatched)
    monkeypatch.setattr(module.os, "open", fail_once_before_recovery_replace)
    monkeypatch.setattr(module, "_try_acquire_bind_lock", observe_lock_attempt)
    return first_fault_seen, recovery_fault_seen, observer_lock_attempt, release_recovery_fault


def _assert_marker_uncertain(module: ModuleType, attempts: Path, attempt_id: str) -> None:
    store = attempts.resolve()
    record_path = module._attempt_record_path(store, attempt_id)
    with module._attempt_transition_lock(store, record_path) as transition_lock:
        assert module._bind_lock_durability_uncertain(transition_lock) is True


def test_compound_failure_reserve_observer_never_reports_already_dispatched(tmp_path: Path, monkeypatch) -> None:
    module = _load_orchestrator()
    attempts = tmp_path / "attempts"
    attempt_id = "attempt-round5-reserve-observer"
    child_job_id = "child-round5-reserve-observer"
    reservation = _reserve(module, attempts, attempt_id)
    first_fault, recovery_fault, observer_lock, release_recovery = _inject_compound_failure(
        module, attempts, attempt_id, monkeypatch
    )

    bind_args = {
        "attempt_store": attempts,
        "attempt_id": attempt_id,
        "reservation_token": reservation.reservation_token,
        "child_job_id": child_job_id,
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        binder = pool.submit(module.bind_dispatched_child, **bind_args)
        assert first_fault.wait(5), "bind did not reach the injected directory-fsync failure"
        assert recovery_fault.wait(5), "bind did not reach the injected pre-replace recovery failure"
        observer = pool.submit(
            module.reserve_dispatch,
            attempt_store=attempts,
            attempt_id=attempt_id,
            intent_revision=12,
            execution_revision=EXECUTION_REVISION,
        )
        assert observer_lock.wait(5), "reserve observer did not reach the serialized transition read"
        assert not observer.done(), "reserve observer bypassed the transition lock"
        release_recovery.set()

        with pytest.raises(module.DispatchDurabilityError) as raised:
            binder.result(timeout=5)
        observer_result = observer.result(timeout=5)

    assert isinstance(raised.value.__cause__, module.OrchestrationError)
    assert observer_result.code == "RECONCILE_REQUIRED"
    assert observer_result.code != "ALREADY_DISPATCHED"
    record_path = module._attempt_record_path(attempts.resolve(), attempt_id)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["state"] == "dispatched"
    assert record["child_job_id"] == child_job_id
    _assert_marker_uncertain(module, attempts, attempt_id)

    reconciled = module.reconcile_dispatch(
        attempt_store=attempts,
        attempt_id=attempt_id,
        child_job_id=child_job_id,
    )
    assert reconciled.code == "ALREADY_DISPATCHED"
    after_reconcile = module.reserve_dispatch(
        attempt_store=attempts,
        attempt_id=attempt_id,
        intent_revision=12,
        execution_revision=EXECUTION_REVISION,
    )
    assert after_reconcile.code == "ALREADY_DISPATCHED"


def test_compound_failure_same_child_bind_observer_never_reports_already_dispatched(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_orchestrator()
    attempts = tmp_path / "attempts"
    attempt_id = "attempt-round5-bind-observer"
    child_job_id = "child-round5-bind-observer"
    reservation = _reserve(module, attempts, attempt_id)
    first_fault, recovery_fault, observer_lock, release_recovery = _inject_compound_failure(
        module, attempts, attempt_id, monkeypatch
    )

    bind_args = {
        "attempt_store": attempts,
        "attempt_id": attempt_id,
        "reservation_token": reservation.reservation_token,
        "child_job_id": child_job_id,
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        binder = pool.submit(module.bind_dispatched_child, **bind_args)
        assert first_fault.wait(5), "bind did not reach the injected directory-fsync failure"
        assert recovery_fault.wait(5), "bind did not reach the injected pre-replace recovery failure"
        observer = pool.submit(module.bind_dispatched_child, **bind_args)
        assert observer_lock.wait(5), "same-child observer did not reach the serialized transition read"
        assert not observer.done(), "same-child observer bypassed the transition lock"
        release_recovery.set()

        with pytest.raises(module.DispatchDurabilityError):
            binder.result(timeout=5)
        observer_result = observer.result(timeout=5)

    assert observer_result.code == "RECONCILE_REQUIRED"
    assert observer_result.code != "ALREADY_DISPATCHED"
    _assert_marker_uncertain(module, attempts, attempt_id)


def test_dispatch_once_preserves_uncertainty_through_compound_recovery_failure(tmp_path: Path, monkeypatch) -> None:
    module = _load_orchestrator()
    attempts = tmp_path / "attempts"
    attempts.mkdir()
    attempt_id = "attempt-round5-dispatch-once"
    child_job_id = "child-round5-dispatch-once"
    first_fault, recovery_fault, _observer_lock, release_recovery = _inject_compound_failure(
        module, attempts, attempt_id, monkeypatch
    )
    release_recovery.set()

    result = module.dispatch_once(
        attempt_store=attempts,
        attempt_id=attempt_id,
        intent_revision=12,
        execution_revision=EXECUTION_REVISION,
        dispatch=lambda: child_job_id,
    )

    assert first_fault.is_set()
    assert recovery_fault.is_set()
    assert result.code == "RECONCILE_REQUIRED"
    assert result.code != "ALREADY_DISPATCHED"
    record_path = module._attempt_record_path(attempts.resolve(), attempt_id)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["state"] == "dispatch_ambiguous"
    assert record["child_job_id"] == child_job_id

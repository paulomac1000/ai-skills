"""Concurrent observer-race regressions for PR #87 round-4 dispatch durability hardening."""

from __future__ import annotations

import importlib.util
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR = ROOT / "skills/agent-task-orchestrator/tools/task_orchestrator.py"
EXECUTION_REVISION = "e" * 40


def _load_orchestrator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("task_orchestrator_round4_regressions", ORCHESTRATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _reserve(module: ModuleType, attempts: Path, attempt_id: str):
    reservation = module.reserve_dispatch(
        attempt_store=attempts,
        attempt_id=attempt_id,
        intent_revision=11,
        execution_revision=EXECUTION_REVISION,
    )
    assert reservation.allowed is True
    assert reservation.reservation_token is not None
    return reservation


def _pause_failed_dispatched_sync(module: ModuleType, attempt_id: str, monkeypatch):
    original_sync = module._fsync_directory
    original_acquire = module._try_acquire_bind_lock
    fault_seen = Event()
    observer_lock_attempt = Event()
    release_fault = Event()
    injected = False

    def fail_once_after_visible_dispatched(path: Path) -> None:
        nonlocal injected
        record_path = module._attempt_record_path(path, attempt_id)
        if not injected and record_path.exists():
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if record.get("state") == "dispatched":
                injected = True
                fault_seen.set()
                assert release_fault.wait(5), "test observer did not reach the transition lock"
                raise module.OrchestrationError("injected post-replace directory fsync failure")
        original_sync(path)

    def observe_lock_attempt(descriptor: int) -> None:
        if fault_seen.is_set():
            observer_lock_attempt.set()
        original_acquire(descriptor)

    monkeypatch.setattr(module, "_fsync_directory", fail_once_after_visible_dispatched)
    monkeypatch.setattr(module, "_try_acquire_bind_lock", observe_lock_attempt)
    return fault_seen, observer_lock_attempt, release_fault


def test_reserve_observer_cannot_see_already_dispatched_during_failed_fsync(tmp_path: Path, monkeypatch) -> None:
    module = _load_orchestrator()
    attempts = tmp_path / "attempts"
    attempt_id = "attempt-round4-reserve-observer"
    child_job_id = "child-round4-reserve-observer"
    reservation = _reserve(module, attempts, attempt_id)
    fault_seen, observer_lock_attempt, release_fault = _pause_failed_dispatched_sync(
        module, attempt_id, monkeypatch
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        binder = pool.submit(
            module.bind_dispatched_child,
            attempt_store=attempts,
            attempt_id=attempt_id,
            reservation_token=reservation.reservation_token,
            child_job_id=child_job_id,
        )
        assert fault_seen.wait(5), "bind did not reach the injected durability failure"
        observer = pool.submit(
            module.reserve_dispatch,
            attempt_store=attempts,
            attempt_id=attempt_id,
            intent_revision=11,
            execution_revision=EXECUTION_REVISION,
        )
        assert observer_lock_attempt.wait(5), "reserve observer did not reach the serialized transition read"
        assert not observer.done(), "reserve observer bypassed the transition lock"
        release_fault.set()

        bind_result = binder.result(timeout=5)
        observer_result = observer.result(timeout=5)

    assert bind_result.code == "RECONCILE_REQUIRED"
    assert observer_result.code == "RECONCILE_REQUIRED"
    assert observer_result.code != "ALREADY_DISPATCHED"
    record_path = module._attempt_record_path(attempts.resolve(), attempt_id)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["state"] == "dispatch_ambiguous"
    assert record["child_job_id"] == child_job_id


def test_same_child_bind_observer_cannot_promote_failed_fsync_to_already_dispatched(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_orchestrator()
    attempts = tmp_path / "attempts"
    attempt_id = "attempt-round4-bind-observer"
    child_job_id = "child-round4-bind-observer"
    reservation = _reserve(module, attempts, attempt_id)
    fault_seen, observer_lock_attempt, release_fault = _pause_failed_dispatched_sync(
        module, attempt_id, monkeypatch
    )

    bind_args = {
        "attempt_store": attempts,
        "attempt_id": attempt_id,
        "reservation_token": reservation.reservation_token,
        "child_job_id": child_job_id,
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        binder = pool.submit(module.bind_dispatched_child, **bind_args)
        assert fault_seen.wait(5), "bind did not reach the injected durability failure"
        observer = pool.submit(module.bind_dispatched_child, **bind_args)
        assert observer_lock_attempt.wait(5), "same-child bind did not reach the serialized transition read"
        assert not observer.done(), "same-child bind bypassed the transition lock"
        release_fault.set()

        bind_result = binder.result(timeout=5)
        observer_result = observer.result(timeout=5)

    assert bind_result.code == "RECONCILE_REQUIRED"
    assert observer_result.code == "RECONCILE_REQUIRED"
    assert observer_result.code != "ALREADY_DISPATCHED"
    record_path = module._attempt_record_path(attempts.resolve(), attempt_id)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["state"] == "dispatch_ambiguous"
    assert record["child_job_id"] == child_job_id

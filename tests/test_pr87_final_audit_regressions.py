"""Regressions for the final PR #87 concurrency and descriptor-read audit."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType

import pytest

from contracts import skill_distribution

ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR = ROOT / "skills/agent-task-orchestrator/tools/task_orchestrator.py"
EXECUTION_REVISION = "d" * 40


def _load_orchestrator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("task_orchestrator_final_audit", ORCHESTRATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_concurrent_child_bind_cannot_change_durable_identity(tmp_path: Path) -> None:
    module = _load_orchestrator()
    attempts = tmp_path / "attempts"
    reservation = module.reserve_dispatch(
        attempt_store=attempts,
        attempt_id="attempt-race",
        intent_revision=7,
        execution_revision=EXECUTION_REVISION,
    )
    assert reservation.allowed is True
    assert reservation.reservation_token is not None

    barrier = threading.Barrier(2)

    def bind(child_job_id: str) -> tuple[str, object]:
        barrier.wait()
        try:
            result = module.bind_dispatched_child(
                attempt_store=attempts,
                attempt_id="attempt-race",
                reservation_token=reservation.reservation_token,
                child_job_id=child_job_id,
            )
        except module.OrchestrationError as error:
            return "error", str(error)
        return "ok", result

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            future.result()
            for future in (
                executor.submit(bind, "child-a"),
                executor.submit(bind, "child-b"),
            )
        ]

    successes = [value for status, value in results if status == "ok"]
    failures = [str(value) for status, value in results if status == "error"]
    assert len(successes) == 1
    assert len(failures) == 1
    assert any(
        marker in failures[0]
        for marker in ("already in progress", "already bound to a different child job")
    )

    winner = successes[0].child_job_id
    record_path = module._attempt_record_path(attempts.resolve(), "attempt-race")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["state"] == "dispatched"
    assert record["child_job_id"] == winner

    repeated = module.bind_dispatched_child(
        attempt_store=attempts,
        attempt_id="attempt-race",
        reservation_token=reservation.reservation_token,
        child_job_id=winner,
    )
    assert repeated.code == "ALREADY_DISPATCHED"
    assert repeated.child_job_id == winner


def test_distribution_bounded_read_detects_same_size_in_place_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "payload.bin"
    original = b"a" * 128
    replacement = b"b" * len(original)
    path.write_bytes(original)
    baseline = path.stat()
    baseline_atime_ns = getattr(baseline, "st_atime_ns", int(baseline.st_atime * 1_000_000_000))
    baseline_mtime_ns = getattr(baseline, "st_mtime_ns", int(baseline.st_mtime * 1_000_000_000))

    original_read = skill_distribution.os.read
    changed = False

    def racing_read(descriptor: int, maximum: int) -> bytes:
        nonlocal changed
        data = original_read(descriptor, maximum)
        if data and not changed:
            changed = True
            try:
                with path.open("r+b") as writer:
                    writer.seek(0)
                    writer.write(replacement)
                    writer.flush()
                    os.fsync(writer.fileno())
            except PermissionError:
                pass
            os.utime(path, ns=(baseline_atime_ns, baseline_mtime_ns + 2_000_000_000))
        return data

    monkeypatch.setattr(skill_distribution.os, "read", racing_read)
    with pytest.raises(skill_distribution.DistributionError, match="changed while being read"):
        skill_distribution._read_bounded(path, 1024, label="test payload")
    assert changed is True


def test_distribution_bounded_read_rejects_non_regular_file(tmp_path: Path) -> None:
    with pytest.raises(skill_distribution.DistributionError, match="not a regular file|cannot be read"):
        skill_distribution._read_bounded(tmp_path, 1024, label="test payload")

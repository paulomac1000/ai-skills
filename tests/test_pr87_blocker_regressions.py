"""Adversarial regressions for the final PR #87 blocker review."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType

from contracts.diagnostic_reasoning import validate_diagnostic_state

ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR = ROOT / "skills/agent-task-orchestrator/tools/task_orchestrator.py"
EXECUTION_REVISION = "e" * 40


def _load_orchestrator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("task_orchestrator_blocker_regressions", ORCHESTRATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_proven_causal_refs_must_be_supporting_not_contradicting_only() -> None:
    state = {
        "observations": [
            {
                "id": "O-1",
                "evidence_ref": "ev:observation",
                "source_group": "runtime-observation",
            }
        ],
        "probes": [
            {
                "id": "P-1",
                "source_group": "independent-probe",
                "predictions": {"H-winner": "A", "H-old": "B"},
                "observed_outcome": "A",
                "evidence_ref": "ev:probe",
            }
        ],
        "hypotheses": [
            {
                "id": "H-winner",
                "status": "supported",
                "supporting_evidence": [],
                "contradicting_evidence": ["ev:observation", "ev:probe"],
            },
            {
                "id": "H-old",
                "status": "disproven",
                "supporting_evidence": [],
                "contradicting_evidence": [],
            },
        ],
        "causal_assessment": {
            "status": "proven",
            "causes": [
                {
                    "hypothesis_id": "H-winner",
                    "role": "primary",
                    "support": "proven",
                    "evidence_refs": ["ev:observation", "ev:probe"],
                }
            ],
            "unresolved_alternatives": [],
        },
    }

    findings = validate_diagnostic_state(state)
    assert any("PROVEN_EVIDENCE_NOT_BOUND_TO_HYPOTHESIS" in finding for finding in findings)


def test_discriminating_probe_must_separate_every_non_disproven_alternative() -> None:
    state = {
        "observations": [
            {
                "id": "O-1",
                "evidence_ref": "ev:observation",
                "source_group": "runtime-observation",
            }
        ],
        "probes": [
            {
                "id": "P-1",
                "source_group": "independent-probe",
                "predictions": {"H-winner": "A", "H-credible": "A", "H-old": "B"},
                "observed_outcome": "A",
                "evidence_ref": "ev:probe",
            }
        ],
        "hypotheses": [
            {
                "id": "H-winner",
                "status": "supported",
                "supporting_evidence": ["ev:observation", "ev:probe"],
                "contradicting_evidence": [],
            },
            {
                "id": "H-credible",
                "status": "active",
                "supporting_evidence": [],
                "contradicting_evidence": [],
            },
            {
                "id": "H-old",
                "status": "disproven",
                "supporting_evidence": [],
                "contradicting_evidence": [],
            },
        ],
        "causal_assessment": {
            "status": "proven",
            "causes": [
                {
                    "hypothesis_id": "H-winner",
                    "role": "primary",
                    "support": "proven",
                    "evidence_refs": ["ev:observation", "ev:probe"],
                }
            ],
            "unresolved_alternatives": [],
        },
    }

    findings = validate_diagnostic_state(state)
    assert any("PROVEN_WITHOUT_DISCRIMINATING_EVIDENCE" in finding for finding in findings)


def test_dispatch_state_publication_syncs_parent_directory(tmp_path: Path, monkeypatch) -> None:
    module = _load_orchestrator()
    attempts = tmp_path / "attempts"
    synced: list[Path] = []
    original = module._fsync_directory

    def recording_sync(path: Path) -> None:
        synced.append(path)
        original(path)

    monkeypatch.setattr(module, "_fsync_directory", recording_sync)
    reservation = module.reserve_dispatch(
        attempt_store=attempts,
        attempt_id="attempt-durable",
        intent_revision=8,
        execution_revision=EXECUTION_REVISION,
    )
    assert reservation.allowed is True
    assert reservation.reservation_token is not None
    store = attempts.resolve()
    assert store in synced

    module.bind_dispatched_child(
        attempt_store=attempts,
        attempt_id="attempt-durable",
        reservation_token=reservation.reservation_token,
        child_job_id="child-durable",
    )
    assert synced.count(store) >= 2


def test_reconcile_recovers_abandoned_legacy_bind_lock(tmp_path: Path) -> None:
    module = _load_orchestrator()
    attempts = tmp_path / "attempts"
    reservation = module.reserve_dispatch(
        attempt_store=attempts,
        attempt_id="attempt-stale-lock",
        intent_revision=8,
        execution_revision=EXECUTION_REVISION,
    )
    assert reservation.reservation_token is not None
    ambiguous = module._mark_dispatch_ambiguous(
        attempt_store=attempts,
        attempt_id="attempt-stale-lock",
        reservation_token=reservation.reservation_token,
        child_job_id="child-stale-lock",
    )
    assert ambiguous.code == "RECONCILE_REQUIRED"

    store = attempts.resolve()
    record_path = module._attempt_record_path(store, "attempt-stale-lock")
    lock_path = store / f".{record_path.name}.bind.lock"
    if lock_path.exists():
        lock_path.unlink()
    lock_path.mkdir(mode=0o700)
    stale = time.time() - module.LEGACY_BIND_LOCK_STALE_SECONDS - 5.0
    os.utime(lock_path, (stale, stale))

    reconciled = module.reconcile_dispatch(
        attempt_store=attempts,
        attempt_id="attempt-stale-lock",
        child_job_id="child-stale-lock",
    )
    assert reconciled.code == "ALREADY_DISPATCHED"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["state"] == "dispatched"
    assert record["child_job_id"] == "child-stale-lock"


def test_ambiguity_mark_and_bind_share_one_serialized_transition(tmp_path: Path) -> None:
    module = _load_orchestrator()
    attempts = tmp_path / "attempts"
    reservation = module.reserve_dispatch(
        attempt_store=attempts,
        attempt_id="attempt-transition-race",
        intent_revision=8,
        execution_revision=EXECUTION_REVISION,
    )
    assert reservation.reservation_token is not None
    barrier = threading.Barrier(2)

    def bind() -> object:
        barrier.wait()
        return module.bind_dispatched_child(
            attempt_store=attempts,
            attempt_id="attempt-transition-race",
            reservation_token=reservation.reservation_token,
            child_job_id="child-race",
        )

    def mark_ambiguous() -> object:
        barrier.wait()
        return module._mark_dispatch_ambiguous(
            attempt_store=attempts,
            attempt_id="attempt-transition-race",
            reservation_token=reservation.reservation_token,
            child_job_id="child-race",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [future.result() for future in (executor.submit(bind), executor.submit(mark_ambiguous))]

    assert {result.code for result in results} <= {"ALREADY_DISPATCHED", "RECONCILE_REQUIRED"}
    store = attempts.resolve()
    record_path = module._attempt_record_path(store, "attempt-transition-race")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["state"] == "dispatched"
    assert record["child_job_id"] == "child-race"

    repeated = module._mark_dispatch_ambiguous(
        attempt_store=attempts,
        attempt_id="attempt-transition-race",
        reservation_token=reservation.reservation_token,
        child_job_id="child-race",
    )
    assert repeated.code == "ALREADY_DISPATCHED"
    assert json.loads(record_path.read_text(encoding="utf-8"))["state"] == "dispatched"

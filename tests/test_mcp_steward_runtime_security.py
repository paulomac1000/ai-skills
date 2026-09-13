"""Adversarial regressions for generated Steward runtime authority and cancellation recovery."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "mcp-steward-architect"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _generated_runtime(tmp_path: Path) -> tuple[ModuleType, dict[str, Any], dict[str, Any], dict[str, Any]]:
    generator = _load(SKILL / "tools" / "generate_steward.py", f"runtime_security_generator_{tmp_path.name}")
    destination = tmp_path / "generated"
    generator.generate_project(
        destination,
        language="python",
        identity="security_steward",
        server_name="Security Steward",
        steward_id="security",
        profile="verification",
    )
    runtime = _load(
        destination / "src/security_steward/steward_runtime.py",
        f"generated_security_runtime_{tmp_path.name}",
    )
    profile = json.loads((destination / "src/security_steward/steward_profile.json").read_text(encoding="utf-8"))
    proof = json.loads((destination / "src/security_steward/steward_proof_recipe.json").read_text(encoding="utf-8"))
    upstream = json.loads(
        (destination / "src/security_steward/steward_upstream_capability.json").read_text(encoding="utf-8")
    )
    return runtime, profile, proof, upstream


def test_completion_gate_uses_persisted_producer_binding_and_coverage(tmp_path: Path) -> None:
    runtime, profile, proof, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "authority.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, upstream=upstream)
    job_id = steward.submit("repo", "abc", "authority-1")["jobId"]

    steward.run_once()
    steward.run_once()
    steward.run_once()
    assert steward.status(job_id)["status"] == "finalizing"
    evidence_id = steward.get(job_id)["evidence"][0]["evidenceId"]

    with store._write() as db:
        db.execute("UPDATE steward_evidence SET producer_id='forged-producer' WHERE evidence_id=?", (evidence_id,))
    evaluation = steward.completion_gate(job_id)
    assert evaluation["disposition"] == "blocked"
    assert evaluation["obligations"][0]["state"] == "unsatisfied"

    with store._write() as db:
        db.execute(
            "UPDATE steward_evidence SET producer_id='seed-provider', binding_json=? WHERE evidence_id=?",
            (
                json.dumps(
                    {"required": ["target", "candidate"], "satisfied": ["target"], "status": "partial"},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                evidence_id,
            ),
        )
    assert steward.completion_gate(job_id)["disposition"] == "blocked"

    with store._write() as db:
        db.execute(
            "UPDATE steward_evidence SET binding_json=?, coverage_json=? WHERE evidence_id=?",
            (
                json.dumps(
                    {
                        "required": ["target", "candidate"],
                        "satisfied": ["target", "candidate"],
                        "status": "complete",
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                json.dumps(
                    {"state": "partial", "required": 2, "observed": 1},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                evidence_id,
            ),
        )
    assert steward.completion_gate(job_id)["disposition"] == "blocked"


def test_stale_cancel_reconciliation_uses_original_submit_handle(tmp_path: Path) -> None:
    runtime, profile, proof, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))

    class RecordingProvider(runtime.FakeProvider):
        def __init__(self) -> None:
            self.reconcile_cancel_handles: list[str] = []

        def reconcile_cancel(self, cancellation_operation_id: str, remote_handle: str, subject: dict[str, Any]) -> str:
            self.reconcile_cancel_handles.append(remote_handle)
            return super().reconcile_cancel(cancellation_operation_id, remote_handle, subject)

    provider = RecordingProvider()
    store = runtime.StewardStore(tmp_path / "cancel.db", clock)
    steward = runtime.StewardRuntime(
        store,
        profile,
        proof,
        upstream=upstream,
        provider=provider,
        faults=runtime.FaultInjector({"after-cancel-dispatch"}),
    )
    old_job = steward.submit("repo", "abc", "cancel-old")["jobId"]
    steward.run_once()
    steward.run_once()
    submit = store.operation_for_job(old_job, "submit")
    assert submit is not None
    original_submit_handle = str(submit["remote_handle"])
    assert original_submit_handle

    steward.cancel(old_job)
    steward.run_once()
    steward.run_once()
    cancel_op = store.operation_for_job(old_job, "cancel")
    assert cancel_op is not None
    assert cancel_op["delivery"] == "delivery-unknown"
    assert cancel_op["remote_handle"] is None

    steward.submit("repo", "abc", "cancel-new")
    for _ in range(4):
        if provider.reconcile_cancel_handles:
            break
        assert steward.run_once() is True

    assert provider.reconcile_cancel_handles == [original_submit_handle]

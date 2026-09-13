"""Adversarial regressions for generated Steward runtime authority and cancellation recovery."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "mcp-steward-architect"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _generated_runtime(
    tmp_path: Path,
) -> tuple[ModuleType, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
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
    mutation = json.loads(
        (destination / "src/security_steward/steward_mutation_policy.json").read_text(encoding="utf-8")
    )
    upstream = json.loads(
        (destination / "src/security_steward/steward_upstream_capability.json").read_text(encoding="utf-8")
    )
    return runtime, profile, proof, mutation, upstream


def test_completion_gate_uses_persisted_producer_binding_and_coverage(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "authority.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream)
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
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
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
        mutation,
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


def test_result_cannot_observe_completed_before_sealed_handoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, _, _, _, _ = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "terminal-read.db", clock)
    job_id = store.admit({"id": "repo", "revision": "abc"}, "terminal-read-1")["jobId"]
    initial = store.job(job_id)
    completion = {"disposition": "eligible"}
    handoff = {
        "digest": "sha256:" + "a" * 64,
        "candidate": initial["candidate"],
    }

    original_job = store.job
    published = False

    def publish_before_job_read(requested_job_id: str) -> dict[str, Any]:
        nonlocal published
        if not published:
            store.save_terminal(
                job_id,
                completion,
                handoff,
                expected_attempt_id=initial["attemptId"],
                expected_version=initial["version"],
                mutation_decision_ref="test-admission",
            )
            published = True
        return original_job(requested_job_id)

    monkeypatch.setattr(store, "job", publish_before_job_read)

    result = store.result(job_id)

    assert published is True
    assert result["job"]["status"] == "completed"
    assert result["completion"] == completion
    assert result["handoff"] == handoff


def test_real_dispatch_gate_rejects_capability_drift_and_stale_fence_with_zero_provider_calls(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))

    class CountingProvider(runtime.FakeProvider):
        def __init__(self) -> None:
            self.dispatch_count = 0

        def dispatch(self, operation_id: str, subject: dict[str, Any]) -> str:
            self.dispatch_count += 1
            return super().dispatch(operation_id, subject)

    provider = CountingProvider()
    store = runtime.StewardStore(tmp_path / "capability-drift.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream, provider=provider)
    job_id = steward.submit("repo", "abc", "cap-drift")["jobId"]
    assert steward.run_once() is True  # durable reservation only
    drift = json.loads(json.dumps(upstream))
    drift["contract"]["revision"] = "2"
    identity = {key: drift["contract"][key] for key in ("source", "id", "revision")}
    import hashlib

    drift["contract"]["digest"] = (
        "sha256:" + hashlib.sha256(json.dumps(identity, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
    )
    steward.upstream = drift
    assert steward.run_once() is True
    assert provider.dispatch_count == 0
    assert steward.status(job_id)["status"] == "blocked"

    provider2 = CountingProvider()
    store2 = runtime.StewardStore(tmp_path / "stale-fence.db", clock)
    steward2 = runtime.StewardRuntime(store2, profile, proof, mutation, upstream=upstream, provider=provider2)
    job2 = steward2.submit("repo2", "abc", "stale-fence")["jobId"]
    steward2.run_once()
    with store2._write() as db:
        db.execute("UPDATE steward_jobs SET attempt_id='new-attempt',version=version+1 WHERE job_id=?", (job2,))
    steward2.run_once()
    assert provider2.dispatch_count == 0
    assert steward2.status(job2)["status"] == "blocked"


def test_evidence_promotion_uses_observed_binding_coverage_and_authority_without_minting(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))

    class PartialProvider(runtime.FakeProvider):
        def poll(self, remote_handle: str, subject: dict[str, Any]) -> dict[str, Any]:
            payload = super().poll(remote_handle, subject)
            payload["observation"]["authorityClass"] = "advisory"
            payload["observation"]["binding"]["satisfied"] = []
            payload["observation"]["coverage"] = {"required": 2, "observed": 1}
            return payload

    steward = runtime.StewardRuntime(
        runtime.StewardStore(tmp_path / "observed-evidence.db", clock),
        profile,
        proof,
        mutation,
        upstream=upstream,
        provider=PartialProvider(),
    )
    job_id = steward.submit("repo", "abc", "observed-evidence")["jobId"]
    for _ in range(8):
        steward.run_once()
        if steward.status(job_id)["status"] == "blocked":
            break
    evidence = steward.get(job_id)["evidence"]
    assert len(evidence) == 1
    assert evidence[0]["authorityClass"] == "advisory"
    assert evidence[0]["binding"]["status"] == "partial"
    assert evidence[0]["binding"]["satisfied"] == ["candidate"]
    assert evidence[0]["coverage"] == {"state": "partial", "required": 2, "observed": 1}
    assert steward.status(job_id)["status"] == "blocked"


def test_runtime_requires_explicit_reviewed_mutation_policy_and_upstream(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    store = runtime.StewardStore(tmp_path / "missing-design.db", runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC)))
    with pytest.raises((TypeError, ValueError)):
        runtime.StewardRuntime(store, profile, proof, mutation)  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="explicit reviewed upstream"):
        runtime.StewardRuntime(store, profile, proof, None, upstream=upstream)  # type: ignore[arg-type]

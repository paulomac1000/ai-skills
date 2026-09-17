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


def test_foreign_provider_subject_cannot_be_relabelled_as_job_evidence(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))

    class ForeignSubjectProvider(runtime.FakeProvider):
        def poll(self, remote_handle: str, subject: dict[str, Any]) -> dict[str, Any]:
            payload = super().poll(remote_handle, subject)
            payload["subject"] = {"type": "target", "id": "different-repository", "revision": "abc"}
            return payload

    steward = runtime.StewardRuntime(
        runtime.StewardStore(tmp_path / "foreign-subject.db", clock),
        profile,
        proof,
        mutation,
        upstream=upstream,
        provider=ForeignSubjectProvider(),
    )
    job_id = steward.submit("repo", "abc", "foreign-subject-1")["jobId"]
    for _ in range(8):
        if not steward.run_once():
            break
    assert steward.status(job_id)["status"] == "blocked"
    assert steward.get(job_id)["evidence"] == []


def test_evidence_freshness_binds_to_capture_time_not_dispatch_time(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    steward = runtime.StewardRuntime(
        runtime.StewardStore(tmp_path / "freshness.db", clock),
        profile,
        proof,
        mutation,
        upstream=upstream,
        provider=runtime.FakeProvider(),
    )
    job_id = steward.submit("repo", "abc", "freshness-1")["jobId"]
    dispatch_iso = clock.now().isoformat()
    assert steward.run_once() is True  # reserve submit
    assert steward.run_once() is True  # dispatch + bind remote handle (observed_at = dispatch time)
    clock.advance(400)  # exceed the 300s criterion freshness window before the result is observed
    assert steward.run_once() is True  # poll + capture + persist evidence in one pass
    evidence = steward.get(job_id)["evidence"]
    assert evidence, "expected evidence promotion after capture"
    capture_iso = clock.now().isoformat().replace("+00:00", "Z")
    for item in evidence:
        assert item["observedAt"] == capture_iso
        assert item["observedAt"] != dispatch_iso
        assert item["expiresAt"] > item["observedAt"]


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


def test_real_dispatch_gate_rejects_full_receipt_subject_lease_request_and_budget_cross_product(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)

    class CountingProvider(runtime.FakeProvider):
        def __init__(self) -> None:
            self.dispatch_count = 0

        def dispatch(self, operation_id: str, subject: dict[str, Any]) -> str:
            self.dispatch_count += 1
            return super().dispatch(operation_id, subject)

    cases = {
        "foreign-lineage": ("UPDATE external_operations SET lineage_id='foreign' WHERE job_id=?", ()),
        "foreign-generation": ("UPDATE external_operations SET generation=generation+1 WHERE job_id=?", ()),
        "foreign-attempt": ("UPDATE external_operations SET attempt_id='foreign' WHERE job_id=?", ()),
        "stale-job-version": ("UPDATE external_operations SET job_version=job_version-1 WHERE job_id=?", ()),
        "wrong-target": ("UPDATE external_operations SET target_identity='target:other:abc' WHERE job_id=?", ()),
        "wrong-candidate": (
            "UPDATE external_operations SET candidate_digest=? WHERE job_id=?",
            ("sha256:" + "7" * 64,),
        ),
        "wrong-request": ("UPDATE external_operations SET request_digest=? WHERE job_id=?", ("sha256:" + "8" * 64,)),
        "wrong-kind": ("UPDATE external_operations SET operation_kind='cancel' WHERE job_id=?", ()),
        "wrong-lease-owner": ("UPDATE steward_jobs SET lease_owner='foreign-owner' WHERE job_id=?", ()),
        "wrong-lease-fence": ("UPDATE steward_jobs SET lease_fencing_token=lease_fencing_token+1 WHERE job_id=?", ()),
        "wrong-subject": (
            "UPDATE steward_lineages SET subject_json=? WHERE current_job_id=?",
            (json.dumps({"type": "target", "id": "repo", "revision": "other"}, sort_keys=True, separators=(",", ":")),),
        ),
    }
    for name, (sql, prefix) in cases.items():
        clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
        provider = CountingProvider()
        store = runtime.StewardStore(tmp_path / f"{name}.db", clock)
        steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream, provider=provider)
        job_id = steward.submit("repo", "abc", f"idem-{name}")["jobId"]
        assert steward.run_once() is True
        with store._write() as db:
            db.execute(sql, (*prefix, job_id))
        assert steward.run_once() is True
        assert provider.dispatch_count == 0, name
        assert steward.status(job_id)["status"] == "blocked", name

    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    provider = CountingProvider()
    store = runtime.StewardStore(tmp_path / "budget-reserve.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream, provider=provider)
    job_id = steward.submit("repo", "abc", "idem-budget-reserve")["jobId"]
    assert steward.run_once() is True
    deadline = runtime._parse(steward.status(job_id)["deadlineAt"])
    clock.advance((deadline - clock.now()).total_seconds() - 1.499)
    assert steward.run_once() is True
    assert provider.dispatch_count == 0
    assert steward.status(job_id)["blockedReason"] == "mutation-admission:BudgetUnavailable"


def test_dispatch_commit_closes_toctou_and_stale_generation_reconciles_without_redispatch(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)

    class CountingProvider(runtime.FakeProvider):
        def __init__(self) -> None:
            self.dispatch_count = 0
            self.reconcile_count = 0

        def dispatch(self, operation_id: str, subject: dict[str, Any]) -> str:
            self.dispatch_count += 1
            return super().dispatch(operation_id, subject)

        def reconcile(self, operation_id: str, subject: dict[str, Any]) -> str:
            self.reconcile_count += 1
            return super().reconcile(operation_id, subject)

    provider = CountingProvider()
    steward = runtime.StewardRuntime(
        runtime.StewardStore(tmp_path / "toctou.db", runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))),
        profile,
        proof,
        mutation,
        upstream=upstream,
        provider=provider,
        faults=runtime.FaultInjector({"after-dispatch-start"}),
    )
    old_job = steward.submit("repo", "abc", "toctou-old")["jobId"]
    steward.run_once()
    steward.run_once()
    old_op = steward.get(old_job)["operations"][0]
    assert old_op["delivery"] == "delivery-unknown"
    assert old_op["mutationDecisionRef"]
    assert provider.dispatch_count == 0
    steward.submit("repo", "abc", "toctou-new")
    for _ in range(10):
        steward.run_once()
        if provider.reconcile_count == 1 and provider.dispatch_count == 1:
            break
    assert provider.reconcile_count == 1
    assert provider.dispatch_count == 1


def test_completion_rejects_persisted_authority_above_producer_ceiling(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "authority-ceiling.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream)
    job_id = steward.submit("repo", "abc", "authority-ceiling")["jobId"]
    for _ in range(8):
        steward.run_once()
        if steward.status(job_id)["status"] == "finalizing":
            break
    evidence_id = steward.get(job_id)["evidence"][0]["evidenceId"]
    with store._write() as db:
        db.execute("UPDATE steward_evidence SET authority_class='independent' WHERE evidence_id=?", (evidence_id,))
    evaluation = steward.completion_gate(job_id)
    assert evaluation["disposition"] == "blocked"
    assert evaluation["obligations"][0]["state"] == "unsatisfied"


def _supervised_parent_contract(runtime: ModuleType, *, capability_id: str, generation: int = 3) -> dict[str, Any]:
    return {
        "mode": "supervised",
        "supervisor": {"systemId": "project-steward", "principalOrInstance": "supervisor-1"},
        "work": {"parentWorkId": "parent-1", "parentRunId": "run-1", "generation": generation, "attempt": "a1"},
        "contract": {"id": "parent-contract-1", "revision": "1", "digest": "sha256:" + "0" * 64},
        "authority": {
            "delegatedCapabilities": [capability_id],
            "forbiddenCapabilities": [],
            "parentCompletionAuthority": "report_only",
            "authorityCeiling": "observed",
        },
        "policy": {"revisionOrDigest": "policy-1"},
        "budget": {"absoluteDeadline": "2026-09-13T02:00:00Z", "retryOrResourceBudgetRef": "budget-1"},
        "completion": {
            "obligationsRef": None,
            "terminalBoundary": "steward-job",
            "handoffContract": "execution-evidence-v1",
        },
    }


def test_supervised_admission_snapshots_parent_contract_and_narrows_deadline(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "supervised.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream)
    profile["authority"]["parent_completion"] = "explicit-contract-only"
    parent = _supervised_parent_contract(runtime, capability_id=str(upstream["capability_id"]))
    job_id = steward.submit("repo", "abc", "supervised-1", parent_contract=parent)["jobId"]
    job = steward.status(job_id)
    assert job["parentContract"] is not None
    assert job["parentContract"]["mode"] == "supervised"
    assert job["parentContract"]["digest"].startswith("sha256:")
    # Inherited absolute deadline (02:00Z) is later than the local 15-minute budget,
    # so the effective deadline must remain the narrower local one.
    assert job["deadlineAt"] == "2026-09-13T00:15:00Z"
    snapshot = job["obligationSet"]
    assert snapshot is not None and snapshot["obligations"]
    assert snapshot["digest"].startswith("sha256:")


def test_supervised_admission_narrows_inherited_deadline_when_tighter(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "narrow.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream)
    profile["authority"]["parent_completion"] = "explicit-contract-only"
    parent = _supervised_parent_contract(runtime, capability_id=str(upstream["capability_id"]))
    parent["budget"]["absoluteDeadline"] = "2026-09-13T00:05:00Z"
    job_id = steward.submit("repo", "abc", "narrow-1", parent_contract=parent)["jobId"]
    assert steward.status(job_id)["deadlineAt"] == "2026-09-13T00:05:00Z"


def test_parent_delegation_beyond_delegation_blocks_mutation_dispatch(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    capability_id = str(upstream["capability_id"])
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "forbidden.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream)
    profile["authority"]["parent_completion"] = "explicit-contract-only"
    parent = _supervised_parent_contract(runtime, capability_id=capability_id)
    parent["authority"]["delegatedCapabilities"] = ["some-other-capability"]
    job_id = steward.submit("repo", "abc", "forbidden-1", parent_contract=parent)["jobId"]
    for _ in range(6):
        steward.run_once()
        if steward.status(job_id)["status"] == "blocked":
            break
    status = steward.status(job_id)
    assert status["status"] == "blocked"
    assert "ParentAuthorityInsufficient" in str(status["blockedReason"])


def test_off_topic_plan_after_admission_cannot_complete(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "offtopic.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream)
    job_id = steward.submit("repo", "abc", "offtopic-1")["jobId"]
    assert steward.run_once() is True  # reserve
    assert steward.run_once() is True  # dispatch
    # Planner/model drift: the live proof recipe is rewritten to prove a different
    # topic after admission. The admitted obligation snapshot still demands the
    # original criterion, so completion must fail closed on the missing mapping.
    proof["criteria"] = [dict(proof["criteria"][0], criterion_id="different-topic", canonical_claim="different-topic")]
    assert steward.run_once() is True  # poll + capture + evidence promotion
    evaluation = steward.completion_gate(job_id)
    assert evaluation["disposition"] == "blocked"
    assert evaluation["obligationSetDigest"] is not None
    assert evaluation["obligations"][0]["id"] == "provider-result"
    assert evaluation["obligations"][0]["state"] == "unsatisfied"
    assert steward.status(job_id)["status"] != "completed"


def test_two_semantic_slots_with_identical_payloads_remain_distinct(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "slots.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream)
    job_id = steward.submit("repo", "abc", "slots-1")["jobId"]
    steward.run_once()  # reserve the default "submit" slot
    second = store.reserve_external(job_id, upstream, "submit", semantic_slot="stage-b")
    first = store.operation_for_job(job_id, "submit", "submit")
    assert first is not None and second is not None
    assert first["operation_id"] != second["operation_id"]
    assert first["request_digest"] != second["request_digest"]


def test_operation_deadline_is_durable_and_expiration_is_classified(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "deadline.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream)
    job_id = steward.submit("repo", "abc", "deadline-1")["jobId"]
    store.reserve_external(job_id, upstream, "submit")
    receipt = store.operation_for_job(job_id, "submit")
    assert receipt is not None
    assert receipt["operation_deadline_at"] == "2026-09-13T00:15:00Z"
    store.bind_dispatch(str(receipt["operation_id"]), "remote-deadline")
    # Result arrives after the durable absolute operation deadline:
    # reality is still captured, but the cause is classified, not hidden.
    clock.advance(16 * 60)
    store.capture_result(
        str(receipt["operation_id"]),
        runtime.FakeProvider().poll("remote-deadline", {"type": "target", "id": "repo", "revision": "abc"}),
    )
    receipt = store.operation_for_job(job_id, "submit")
    assert receipt is not None
    assert receipt["cancellation_cause"] == "application_deadline"
    assert receipt["operation_deadline_at"] == "2026-09-13T00:15:00Z"


def test_cancel_provenance_cause_is_bound_to_receipts(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "cause.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream)
    job_id = steward.submit("repo", "abc", "cause-1")["jobId"]
    steward.run_once()  # reserve submit
    steward.run_once()  # dispatch and bind submit
    steward.cancel(job_id, cause="service_shutdown")
    for _ in range(6):
        steward.run_once()
        if steward.status(job_id)["status"] == "cancelled":
            break
    assert steward.status(job_id)["cancellationCause"] == "service_shutdown"
    result = steward.get(job_id)
    causes = {item["operationKind"]: item.get("cancellationCause") for item in result["operations"]}
    assert causes.get("cancel") == "service_shutdown"


def test_supersession_records_parent_superseded_provenance(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "superseded-cause.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream)
    old_job = steward.submit("repo", "abc", "sup-cause-old")["jobId"]
    steward.submit("repo", "abc", "sup-cause-new")
    assert steward.status(old_job)["status"] == "superseded"
    assert steward.status(old_job)["cancellationCause"] == "parent_superseded"


def test_torn_read_decision_cannot_publish_across_generations(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "torn-read.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream)
    old_job = steward.submit("repo", "abc", "torn-read-old")["jobId"]
    # A completion decision composed at generation 1...
    steward.run_once()
    store.reserve_external(old_job, upstream, "submit")
    completion = steward.completion_gate(old_job)
    # ...and the lineage moves to generation 2 before the decision is sealed.
    steward.submit("repo", "abc", "torn-read-new")
    with pytest.raises(RuntimeError, match="stale lineage"):
        steward.completion_gate(old_job)
    with pytest.raises(RuntimeError, match="stale"):
        store.save_terminal(
            old_job,
            completion,
            {"digest": "sha256:" + "0" * 64},
            expected_attempt_id=steward.status(old_job)["attemptId"],
            expected_version=steward.status(old_job)["version"],
            mutation_decision_ref="admission-x",
            expected_read_set=completion.get("readSet"),
        )


def test_stale_completion_read_set_is_rejected_at_publication(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "stale-read-set.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream)
    job_id = steward.submit("repo", "abc", "stale-read-set")["jobId"]
    for _ in range(4):
        steward.run_once()
        if steward.status(job_id)["status"] == "finalizing":
            break
    completion = steward.completion_gate(job_id)
    assert completion["disposition"] == "eligible"
    assert completion["readSet"] is not None and completion["controllerEpoch"] >= 1
    # Deterministic barrier: a concurrent commit lands between the snapshot read
    # that composed the decision and the publication that would act on it.
    original_snapshot = store.decision_snapshot
    evidence_id = steward.get(job_id)["evidence"][0]["evidenceId"]

    def snapshot_then_concurrent_commit(job_id_arg: str) -> dict[str, Any]:
        state = original_snapshot(job_id_arg)
        with store._write() as db:
            db.execute(
                "UPDATE steward_evidence SET payload_digest=? WHERE evidence_id=?", ("sha256:" + "f" * 64, evidence_id)
            )
        return state

    store.decision_snapshot = snapshot_then_concurrent_commit
    steward.finalize_with_gate(job_id)
    status = steward.status(job_id)
    assert status["status"] == "blocked"
    assert "stale-completion-read-set" in str(status["blockedReason"])


def test_parent_forbidden_capability_blocks_dispatch_with_zero_provider_calls(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    capability_id = str(upstream["capability_id"])
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "forbidden-dispatch.db", clock)

    class CountingProvider(runtime.FakeProvider):
        def __init__(self) -> None:
            self.dispatches = 0

        def dispatch(self, operation_id: str, subject: dict[str, Any]) -> str:
            self.dispatches += 1
            return super().dispatch(operation_id, subject)

    provider = CountingProvider()
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream, provider=provider)
    profile["authority"]["parent_completion"] = "explicit-contract-only"
    parent = _supervised_parent_contract(runtime, capability_id=capability_id)
    parent["authority"]["forbiddenCapabilities"] = [capability_id]
    parent["authority"]["delegatedCapabilities"] = []
    job_id = steward.submit("repo", "abc", "forbidden-dispatch-1", parent_contract=parent)["jobId"]
    for _ in range(6):
        steward.run_once()
        if steward.status(job_id)["status"] == "blocked":
            break
    assert provider.dispatches == 0
    assert "ParentAuthorityInsufficient" in str(steward.status(job_id)["blockedReason"])


def test_empty_delegation_grants_nothing(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "empty-delegation.db", clock)

    class CountingProvider(runtime.FakeProvider):
        def __init__(self) -> None:
            self.dispatches = 0

        def dispatch(self, operation_id: str, subject: dict[str, Any]) -> str:
            self.dispatches += 1
            return super().dispatch(operation_id, subject)

    provider = CountingProvider()
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream, provider=provider)
    profile["authority"]["parent_completion"] = "explicit-contract-only"
    parent = _supervised_parent_contract(runtime, capability_id=str(upstream["capability_id"]))
    parent["authority"]["delegatedCapabilities"] = []
    job_id = steward.submit("repo", "abc", "empty-delegation-1", parent_contract=parent)["jobId"]
    for _ in range(6):
        steward.run_once()
        if steward.status(job_id)["status"] == "blocked":
            break
    assert provider.dispatches == 0
    assert "ParentAuthorityInsufficient" in str(steward.status(job_id)["blockedReason"])


def test_expired_operation_never_reaches_provider(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "expired.db", clock)

    class PendingProvider(runtime.FakeProvider):
        def __init__(self) -> None:
            self.polls = 0
            self.reconciles = 0

        def poll(self, remote_handle: str, subject: dict[str, Any]) -> dict[str, Any]:
            self.polls += 1
            return {"state": "pending", "remoteHandle": remote_handle, "subject": subject}

        def reconcile(self, operation_id: str, subject: dict[str, Any]) -> str:
            self.reconciles += 1
            return super().reconcile(operation_id, subject)

    provider = PendingProvider()
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream, provider=provider)
    job_id = steward.submit("repo", "abc", "expired-1")["jobId"]
    steward.run_once()  # reserve
    steward.run_once()  # dispatch + bind
    clock.advance(16 * 60)  # past the durable operation deadline while the result is pending
    for _ in range(6):
        if steward.status(job_id)["status"] == "blocked":
            break
        if not steward.run_once():
            break
    status = steward.status(job_id)
    polls_after_expiry = provider.polls
    assert status["status"] == "blocked"
    assert "operation-deadline-exceeded" in str(status["blockedReason"])
    receipt = store.operation_for_job(job_id, "submit")
    assert receipt is not None and receipt["cancellation_cause"] == "application_deadline"
    # Bounded closure: no further provider polling once expired.
    steward.run_once()
    assert provider.polls == polls_after_expiry


def test_weakened_live_criterion_cannot_complete_admitted_job(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "weakened.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream)
    job_id = steward.submit("repo", "abc", "weakened-1")["jobId"]
    steward.run_once()  # reserve
    steward.run_once()  # dispatch
    # Post-admission policy drift: the live criterion keeps its ID but weakens
    # required authority. The admitted snapshot binds the original semantics.
    proof["criteria"][0]["required_authority"] = "advisory"
    steward.run_once()  # poll + evidence promotion (skipped under drifted semantics)
    evaluation = steward.completion_gate(job_id)
    assert evaluation["disposition"] == "blocked"
    assert evaluation["obligations"][0]["state"] == "unsatisfied"
    assert steward.status(job_id)["status"] != "completed"


def test_second_store_process_on_same_path_fails_as_topology_conflict(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    db_path = tmp_path / "locked.db"
    owner = runtime.StewardStore(db_path, runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC)))
    assert owner._owner_lock is not None
    with pytest.raises(RuntimeError, match="STORE_LOCKED"):
        runtime.StewardStore(db_path, runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC)))


def test_tampered_obligation_snapshot_binding_fails_closed(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "tampered-snapshot.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream)
    job_id = steward.submit("repo", "abc", "tampered-snapshot-1")["jobId"]
    for _ in range(4):
        steward.run_once()
        if steward.status(job_id)["status"] == "finalizing":
            break
    # A restored/corrupted durable snapshot swaps in the CURRENT recipe digest while
    # keeping the stale stored digest; the read-time binding check must reject it.
    with store._write() as db:
        row = db.execute("SELECT obligation_set_json FROM steward_jobs WHERE job_id=?", (job_id,)).fetchone()
        snapshot = json.loads(row[0])
        snapshot["proofRecipeDigest"] = "sha256:" + "a" * 64
        canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        db.execute("UPDATE steward_jobs SET obligation_set_json=? WHERE job_id=?", (canonical, job_id))
    evaluation = steward.completion_gate(job_id)
    assert evaluation["disposition"] == "blocked"


def test_coherent_tampered_snapshot_still_fails_against_admission_digest(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "coherent-tamper.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream)
    job_id = steward.submit("repo", "abc", "coherent-tamper-1")["jobId"]
    for _ in range(4):
        steward.run_once()
        if steward.status(job_id)["status"] == "finalizing":
            break
    # Drop a mandatory obligation and recompute the EMBEDDED digest so the JSON is
    # self-consistent; the separately persisted admission-time digest still binds the
    # original contents, so the tampered snapshot must fail closed.
    with store._write() as db:
        row = db.execute("SELECT obligation_set_json FROM steward_jobs WHERE job_id=?", (job_id,)).fetchone()
        snapshot = json.loads(row[0])
        snapshot["obligations"] = []
        embedded = (
            "sha256:"
            + __import__("hashlib")
            .sha256(
                json.dumps(
                    {
                        "revision": snapshot["revision"],
                        "proofRecipeDigest": snapshot["proofRecipeDigest"],
                        "obligations": [],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            )
            .hexdigest()
        )
        snapshot["digest"] = embedded
        canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        db.execute("UPDATE steward_jobs SET obligation_set_json=? WHERE job_id=?", (canonical, job_id))
    evaluation = steward.completion_gate(job_id)
    assert evaluation["disposition"] == "blocked"


def test_cancel_after_deadline_with_captured_result_still_terminalizes(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "captured-cancel.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream)
    job_id = steward.submit("repo", "abc", "captured-cancel-1")["jobId"]
    steward.run_once()  # reserve
    steward.run_once()  # dispatch
    steward.run_once()  # poll + capture the result while still inside the deadline
    clock.advance(16 * 60)  # the deadline passes AFTER the result was captured
    steward.cancel(job_id, cause="caller_cancel")
    for _ in range(6):
        steward.run_once()
        if steward.status(job_id)["status"] in {"cancelled", "completed"}:
            break
    # The submit result was captured (local terminal closure requires no provider),
    # so cancellation must still reach a terminal state instead of hanging on blocked.
    assert steward.status(job_id)["status"] in {"cancelled", "completed"}


def test_caller_list_mutation_after_admission_never_grants_authority(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    capability_id = str(upstream["capability_id"])
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "caller-mutation.db", clock)

    class CountingProvider(runtime.FakeProvider):
        def __init__(self) -> None:
            self.dispatches = 0

        def dispatch(self, operation_id: str, subject: dict[str, Any]) -> str:
            self.dispatches += 1
            return super().dispatch(operation_id, subject)

    provider = CountingProvider()
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream, provider=provider)
    profile["authority"]["parent_completion"] = "explicit-contract-only"
    parent = _supervised_parent_contract(runtime, capability_id=capability_id)
    delegated: list[str] = []
    parent["authority"]["delegatedCapabilities"] = delegated
    job_id = steward.submit("repo", "abc", "caller-mutation-1", parent_contract=parent)["jobId"]
    # Caller mutates its own list AFTER admission, attempting to grant itself the
    # dispatch capability; the durable snapshot must be immune.
    delegated.append(capability_id)
    for _ in range(6):
        steward.run_once()
        if steward.status(job_id)["status"] == "blocked":
            break
    assert provider.dispatches == 0
    assert "ParentAuthorityInsufficient" in str(steward.status(job_id)["blockedReason"])


def test_supervised_profile_binds_configured_parent_contract_on_public_submit(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    capability_id = str(upstream["capability_id"])
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "configured-parent.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream)
    profile["authority"]["parent_completion"] = "explicit-contract-only"
    profile["parent_contract"] = {
        "system_id": "project-steward",
        "work_id": "parent-1",
        "run_id": "run-1",
        "generation": 3,
        "contract_revision": 1,
        "contract_digest": "sha256:" + "0" * 64,
        "authority_ceiling": "explicit",
        "deadline_at": "2026-09-13T00:05:00Z",
        "budget": {"max_wall_clock_ms": 3_600_000, "max_external_calls": 64},
        "handoff_contract": "execution-evidence-v1",
        "delegated_capabilities": [capability_id],
        "forbidden_capabilities": [],
        "parent_completion_authority": "report_only",
        "policy_revision_or_digest": "policy-1",
        "obligations_ref": None,
        "terminal_boundary": "steward-job",
    }
    # The public tool surface passes no parent contract; the runtime binds the
    # configured one from the profile instead of rejecting the request.
    job_id = steward.submit("repo", "abc", "configured-parent-1")["jobId"]
    job = steward.status(job_id)
    assert job["parentContract"] is not None
    assert job["parentContract"]["supervisor"]["systemId"] == "project-steward"
    assert job["deadlineAt"] == "2026-09-13T00:05:00Z"  # narrowed to the inherited budget


def test_parent_cannot_forbid_steward_local_reporting(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "local-forbidden.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream)
    profile["authority"]["parent_completion"] = "explicit-contract-only"
    parent = _supervised_parent_contract(runtime, capability_id=str(upstream["capability_id"]))
    parent["authority"]["forbiddenCapabilities"] = ["local:handoff@1"]
    job_id = steward.submit("repo", "abc", "local-forbidden-1", parent_contract=parent)["jobId"]
    for _ in range(40):
        steward.run_once()
        if steward.status(job_id)["status"] == "completed":
            break
    else:
        pytest.fail(f"supervised job with a forbidden local capability did not complete: {steward.status(job_id)}")
    result = steward.get(job_id)
    assert result["handoff"] is not None
    assert result["handoff"]["status"] == "completed"


def test_authority_bearing_contract_terms_force_readmission(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "readmission.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream)
    profile["authority"]["parent_completion"] = "explicit-contract-only"
    capability_id = str(upstream["capability_id"])
    base = {
        "system_id": "project-steward",
        "work_id": "parent-1",
        "run_id": "run-1",
        "generation": 3,
        "contract_revision": 1,
        "contract_digest": "sha256:" + "0" * 64,
        "authority_ceiling": "explicit",
        "deadline_at": "2026-09-13T00:05:00Z",
        "budget": {"max_wall_clock_ms": 3_600_000, "max_external_calls": 64},
        "handoff_contract": "execution-evidence-v1",
        "delegated_capabilities": [capability_id],
        "forbidden_capabilities": [],
        "parent_completion_authority": "report_only",
        "policy_revision_or_digest": "policy-1",
        "obligations_ref": None,
        "terminal_boundary": "steward-job",
    }
    profile["parent_contract"] = base
    first = steward.submit("repo", "abc", "readmission-1")
    assert first["duplicate"] is False
    duplicate = steward.submit("repo", "abc", "readmission-1")
    assert duplicate == {"jobId": first["jobId"], "duplicate": True}

    for changed_field, changed_value in [
        ("policy_revision_or_digest", "policy-2"),
        ("handoff_contract", "execution-evidence-v2"),
        ("obligations_ref", "obligations:2"),
        ("terminal_boundary", "supervisor-job"),
    ]:
        profile["parent_contract"] = {**base, changed_field: changed_value}
        with pytest.raises(runtime.ParentContractError) as excinfo:
            steward.submit("repo", "abc", "readmission-1")
        assert excinfo.value.outcome == "ReAdmissionRequired"

    profile["parent_contract"] = {
        **base,
        "budget": {"max_wall_clock_ms": 1_800_000, "max_external_calls": 32},
    }
    with pytest.raises(runtime.ParentContractError) as budget_exc:
        steward.submit("repo", "abc", "readmission-1")
    assert budget_exc.value.outcome == "ReAdmissionRequired"

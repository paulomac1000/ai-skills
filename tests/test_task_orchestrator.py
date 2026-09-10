from __future__ import annotations

import importlib.util
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills/agent-task-orchestrator/tools/task_orchestrator.py"
spec = importlib.util.spec_from_file_location("task_orchestrator", TOOL)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

OrchestrationError = module.OrchestrationError
EXECUTION_REVISION = "c" * 40


def _base(revision: str, *, repository: str = "owner/repo", ref: str = "feature") -> dict[str, str]:
    return {"repository": repository, "ref": ref, "revision": revision}


def _ledger() -> dict:
    return {
        "ledger_id": "ledger-1",
        "task_id": "task-1",
        "intent_revision": 4,
        "requirements": [
            {"id": "R1", "mandatory": True, "status": "satisfied", "evidence_refs": ["git:abc"]},
            {"id": "R2", "mandatory": True, "status": "pending", "evidence_refs": []},
            {"id": "R3", "mandatory": True, "status": "superseded", "evidence_refs": []},
        ],
        "required_capabilities": ["repository.write", "deployment.execute"],
        "required_execution_methods": ["protected-release"],
        "acceptance_criteria": ["tests pass", "runtime identity verified"],
        "scope": {
            "in_scope_targets": ["app-a"],
            "protected_or_out_of_scope_targets": ["service-b"],
            "allowed_side_effect_classes": ["repository-write", "deploy"],
        },
    }


def _bindings() -> dict[str, dict[str, object]]:
    def binding(*subjects: str) -> dict[str, object]:
        return {
            "intent_revision": 4,
            "execution_revision": EXECUTION_REVISION,
            "subjects": list(subjects),
        }

    return {
        "git:abc": binding("requirement:R1", "capability:repository.write"),
        "deploy:receipt": binding("requirement:R2", "capability:deployment.execute"),
        "lease:1": binding("method:protected-release"),
        "junit:1": binding("acceptance:tests pass"),
        "runtime:1": binding("acceptance:runtime identity verified"),
        "diff:empty@exact-sha": binding("output:repository-change-or-noop-proof"),
    }


def test_scope_admits_only_declared_target_and_effect() -> None:
    value = module.admit_scope(
        target="app-a",
        side_effect_class="deploy",
        in_scope_targets=["app-a"],
        protected_or_out_of_scope_targets=["service-b"],
        allowed_side_effect_classes=["repository-write", "deploy"],
    )
    assert value.allowed is True
    assert module.admit_scope(
        target="service-b",
        side_effect_class="deploy",
        in_scope_targets=["app-a", "service-b"],
        protected_or_out_of_scope_targets=["service-b"],
        allowed_side_effect_classes=["deploy"],
    ).code == "TARGET_PROTECTED_OR_OUT_OF_SCOPE"
    assert module.admit_scope(
        target="app-c",
        side_effect_class="deploy",
        in_scope_targets=["app-a"],
        protected_or_out_of_scope_targets=[],
        allowed_side_effect_classes=["deploy"],
    ).code == "TARGET_NOT_IN_SCOPE"


def test_resource_pressure_has_no_scope_bypass_api() -> None:
    with pytest.raises(TypeError):
        module.admit_scope(
            target="app-c",
            side_effect_class="deploy",
            in_scope_targets=["app-a"],
            protected_or_out_of_scope_targets=[],
            allowed_side_effect_classes=["deploy"],
            resource_pressure=True,
        )


def test_unchanged_base_is_admitted() -> None:
    decision = module.admit_base(_base("a" * 40), _base("a" * 40), base_relationship="identical")
    assert decision.admission == "BASE_UNCHANGED"


def test_symbolic_revision_is_not_an_immutable_base() -> None:
    decision = module.admit_base(_base("main"), _base("main"), base_relationship="identical")
    assert decision.admission == "BASE_UNKNOWN"


def test_descendant_requires_explicit_nonoverlap_revalidation() -> None:
    planning = _base("a" * 40)
    execution = _base("b" * 40)
    assert module.admit_base(planning, execution, base_relationship="descendant", overlapping_upstream_change=None).admission == "BASE_UNKNOWN"
    assert module.admit_base(planning, execution, base_relationship="descendant", overlapping_upstream_change=False, revalidated_assumptions=[]).admission == "BASE_UNKNOWN"
    assert module.admit_base(
        planning,
        execution,
        base_relationship="descendant",
        overlapping_upstream_change=False,
        revalidated_assumptions=["working set and authority unchanged upstream"],
    ).admission == "BASE_ADVANCED_COMPATIBLE"


@pytest.mark.parametrize("relationship", ["rebased", "diverged"])
def test_rebased_or_diverged_base_requires_replan(relationship: str) -> None:
    decision = module.admit_base(
        _base("a" * 40),
        _base("b" * 40),
        base_relationship=relationship,
        overlapping_upstream_change=False,
        revalidated_assumptions=["checked"],
    )
    assert decision.admission == "BASE_TOPOLOGY_CHANGED"


def test_repository_or_ref_change_requires_replan() -> None:
    assert module.admit_base(
        _base("a" * 40),
        _base("b" * 40, repository="other/repo"),
        base_relationship="descendant",
        overlapping_upstream_change=False,
    ).admission == "BASE_TOPOLOGY_CHANGED"
    assert module.admit_base(
        _base("a" * 40),
        _base("b" * 40, ref="other"),
        base_relationship="descendant",
        overlapping_upstream_change=False,
    ).admission == "BASE_TOPOLOGY_CHANGED"


def test_child_is_least_authority_subset() -> None:
    child = module.admit_child(
        requested_capabilities=["repository.write"],
        available_capabilities=["repository.write", "deployment.execute"],
        requested_authority=["repository.write:owner/repo"],
        parent_authority=["repository.write:owner/repo", "deploy:app-a"],
        requested_resource_domains=["repo:owner/repo"],
        parent_resource_domains=["repo:owner/repo", "deploy:app-a"],
    )
    assert child.capabilities == ("repository.write",)
    with pytest.raises(OrchestrationError, match="authority exceeds"):
        module.admit_child(
            requested_capabilities=["repository.write"],
            available_capabilities=["repository.write"],
            requested_authority=["deploy:service-b"],
            parent_authority=["repository.write:owner/repo"],
            requested_resource_domains=["repo:owner/repo"],
            parent_resource_domains=["repo:owner/repo"],
        )
    with pytest.raises(OrchestrationError, match="strict subset"):
        module.admit_child(
            requested_capabilities=["repository.write"],
            available_capabilities=["repository.write"],
            requested_authority=["repository.write:owner/repo"],
            parent_authority=["repository.write:owner/repo"],
            requested_resource_domains=["repo:owner/repo"],
            parent_resource_domains=["repo:owner/repo"],
        )


def test_dispatch_classification_never_authorizes_new_launch() -> None:
    first = module.admit_dispatch(attempt_id="attempt-1", known_attempts={})
    again = module.admit_dispatch(attempt_id="attempt-1", known_attempts={"attempt-1": "child-42"})
    assert first.allowed is False
    assert first.code == "ATOMIC_RESERVATION_REQUIRED"
    assert again.allowed is False
    assert again.code == "ALREADY_DISPATCHED"
    assert again.child_job_id == "child-42"


def test_dispatch_once_is_atomic_for_concurrent_callers(tmp_path: Path) -> None:
    attempts = tmp_path / "attempts"
    callback_count = 0
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def launch() -> str:
        nonlocal callback_count
        with lock:
            callback_count += 1
        return "child-42"

    def caller() -> object:
        barrier.wait()
        return module.dispatch_once(
            attempt_store=attempts,
            attempt_id="attempt-1",
            intent_revision=4,
            execution_revision=EXECUTION_REVISION,
            dispatch=launch,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [future.result() for future in (executor.submit(caller), executor.submit(caller))]

    assert callback_count == 1
    assert any(result.child_job_id == "child-42" for result in results)
    assert {result.code for result in results} <= {"ALREADY_DISPATCHED", "ATTEMPT_ALREADY_RESERVED"}


def test_continuation_is_delta_only_for_existing_child() -> None:
    value = module.build_continuation(
        attempt_id="attempt-1",
        child_job_id="child-42",
        continuation_delta={"new_base_revision": "b" * 40, "note": "revalidated"},
    )
    assert set(value) == {"attempt_id", "child_job_id", "continuation_delta"}
    with pytest.raises(OrchestrationError, match="forbidden replay"):
        module.build_continuation(
            attempt_id="attempt-1",
            child_job_id="child-42",
            continuation_delta={"nested": {"full_task": "repeat everything"}},
        )


def test_completed_without_work_evidence_is_suspicious() -> None:
    decision = module.classify_terminal(
        requires_work=True,
        child_disposition="completed",
        expected_outputs=["published-revision"],
    )
    assert decision.code == "COMPLETED_NO_EVIDENCE"
    assert module.classify_terminal(
        requires_work=True,
        child_disposition="completed",
        expected_outputs=["published-revision"],
        intent_revision=4,
        execution_revision=EXECUTION_REVISION,
        evidence_bindings={},
        published_revision=EXECUTION_REVISION,
    ).code == "TERMINAL_EVIDENCE_PRESENT"


def test_unbound_terminal_evidence_is_rejected() -> None:
    decision = module.classify_terminal(
        requires_work=True,
        child_disposition="completed",
        expected_outputs=["repository-change-or-noop-proof"],
        intent_revision=4,
        execution_revision=EXECUTION_REVISION,
        evidence_bindings={},
        no_change_evidence_refs=["diff:empty@exact-sha"],
    )
    assert decision.code == "COMPLETED_NO_EVIDENCE"


def test_explicit_bound_no_change_evidence_can_reconcile_legitimate_noop() -> None:
    decision = module.classify_terminal(
        requires_work=True,
        child_disposition="completed",
        expected_outputs=["repository-change-or-noop-proof"],
        intent_revision=4,
        execution_revision=EXECUTION_REVISION,
        evidence_bindings=_bindings(),
        no_change_evidence_refs=["diff:empty@exact-sha"],
    )
    assert decision.code == "TERMINAL_EVIDENCE_PRESENT"


def test_bounded_no_progress_detects_heartbeat_only_loop() -> None:
    samples = [
        {"meaningful_change": False, "evidence_refs": []},
        {"meaningful_change": False, "evidence_refs": []},
        {"meaningful_change": False, "evidence_refs": []},
    ]
    assert module.classify_progress(samples, max_consecutive_no_progress=3).code == "NO_PROGRESS_LIMIT"
    samples.append({"meaningful_change": True, "evidence_refs": ["artifact:1"]})
    assert module.classify_progress(samples, max_consecutive_no_progress=3).consecutive_no_progress == 0


def test_parent_does_not_stall_while_independent_work_exists() -> None:
    decision = module.schedule_parent(active_background_children=1, runnable_parent_work=2)
    assert decision.code == "CONTINUE_PARENT_WORK"
    assert decision.may_yield is False
    waiting = module.schedule_parent(active_background_children=1, runnable_parent_work=0)
    assert waiting.code == "WAIT_FOR_CHILD_EVIDENCE"
    assert waiting.may_yield is True


def test_parallel_writers_conflict_on_shared_resource_domain() -> None:
    assert module.resource_domains_conflict(["repo:owner/repo"], ["repo:owner/repo"]) is True
    assert module.resource_domains_conflict(["repo:owner/a"], ["repo:owner/b"]) is False


def test_parent_completion_requires_all_current_intent_evidence() -> None:
    decision = module.completion_gate(
        _ledger(),
        execution_revision=EXECUTION_REVISION,
        evidence_bindings=_bindings(),
        capability_evidence={"repository.write": ["git:abc"], "deployment.execute": []},
        method_evidence={"protected-release": []},
        acceptance_evidence={"tests pass": ["junit:1"], "runtime identity verified": []},
    )
    assert decision.completed is False
    assert "requirement:R2:pending" in decision.blockers
    assert "capability:deployment.execute:missing-evidence" in decision.blockers
    assert "method:protected-release:missing-evidence" in decision.blockers


def test_empty_ledger_cannot_false_green() -> None:
    decision = module.completion_gate(
        {},
        execution_revision=EXECUTION_REVISION,
        evidence_bindings={},
        capability_evidence={},
        method_evidence={},
        acceptance_evidence={},
    )
    assert decision.completed is False
    assert "ledger:missing:intent_revision" in decision.blockers


def test_superseded_requirement_does_not_block_but_current_requirements_do() -> None:
    ledger = _ledger()
    ledger["requirements"][1].update({"status": "satisfied", "evidence_refs": ["deploy:receipt"]})
    decision = module.completion_gate(
        ledger,
        execution_revision=EXECUTION_REVISION,
        evidence_bindings=_bindings(),
        capability_evidence={"repository.write": ["git:abc"], "deployment.execute": ["deploy:receipt"]},
        method_evidence={"protected-release": ["lease:1"]},
        acceptance_evidence={"tests pass": ["junit:1"], "runtime identity verified": ["runtime:1"]},
    )
    assert decision.completed is True


def test_handoff_is_compact_and_preserves_intent_revision_scope_and_active_child_identity() -> None:
    handoff = module.compact_handoff(
        _ledger(),
        active_children=[{"attempt_id": "attempt-1", "child_job_id": "child-42", "execution_revision": "b" * 40}],
    )
    assert handoff["intent_revision"] == 4
    assert handoff["unresolved_requirement_ids"] == ["R2"]
    assert handoff["scope"]["protected_or_out_of_scope_targets"] == ["service-b"]
    assert handoff["active_children"][0]["child_job_id"] == "child-42"
    assert "requirements" not in handoff

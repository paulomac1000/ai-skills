"""Adversarial regressions for PR #87 round-3 review findings."""

from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType

import pytest

from contracts.diagnostic_reasoning import validate_diagnostic_state, validate_diagnostic_transition

ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR = ROOT / "skills/agent-task-orchestrator/tools/task_orchestrator.py"
EXECUTION_REVISION = "e" * 40


def _load_orchestrator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("task_orchestrator_round3_regressions", ORCHESTRATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _multi_cause_state() -> dict[str, object]:
    return {
        "observations": [
            {"id": "O-primary", "evidence_ref": "ev:primary", "source_group": "runtime"},
            {"id": "O-secondary", "evidence_ref": "ev:secondary", "source_group": "secondary"},
        ],
        "probes": [
            {
                "id": "P-primary",
                "source_group": "independent-probe",
                "predictions": {"H-primary": "A", "H-secondary": "B"},
                "observed_outcome": "A",
                "evidence_ref": "ev:probe",
            }
        ],
        "hypotheses": [
            {
                "id": "H-primary",
                "status": "supported",
                "supporting_evidence": ["ev:primary", "ev:probe"],
                "contradicting_evidence": [],
            },
            {
                "id": "H-secondary",
                "status": "supported",
                "supporting_evidence": [],
                "contradicting_evidence": ["ev:secondary"],
            },
        ],
        "causal_assessment": {
            "status": "proven",
            "causes": [
                {
                    "hypothesis_id": "H-primary",
                    "role": "primary",
                    "support": "proven",
                    "evidence_refs": ["ev:primary", "ev:probe"],
                },
                {
                    "hypothesis_id": "H-secondary",
                    "role": "contributing",
                    "support": "proven",
                    "evidence_refs": ["ev:secondary"],
                },
            ],
            "unresolved_alternatives": [],
        },
    }


def test_secondary_cause_cannot_bind_contradicting_only_evidence() -> None:
    findings = validate_diagnostic_state(_multi_cause_state())
    assert any(
        "PROVEN_EVIDENCE_NOT_BOUND_TO_HYPOTHESIS: H-secondary" in finding for finding in findings
    )


@pytest.mark.parametrize("assessment_status", ["partial", "suspected"])
def test_nonproven_assessment_cause_still_requires_supporting_evidence(assessment_status: str) -> None:
    state = _multi_cause_state()
    causal = state["causal_assessment"]
    assert isinstance(causal, dict)
    causal["status"] = assessment_status
    causal["causes"] = [
        {
            "hypothesis_id": "H-secondary",
            "role": "contributing",
            "support": "possible",
            "evidence_refs": ["ev:secondary"],
        }
    ]
    findings = validate_diagnostic_state(state)
    assert any(
        "PROVEN_EVIDENCE_NOT_BOUND_TO_HYPOTHESIS: H-secondary" in finding for finding in findings
    )


def test_directory_fsync_failure_after_dispatched_replace_forces_ambiguity(tmp_path: Path, monkeypatch) -> None:
    module = _load_orchestrator()
    attempts = tmp_path / "attempts"
    original_sync = module._fsync_directory
    dispatched_sync_failures = 0

    def fail_dispatched_sync(path: Path) -> None:
        nonlocal dispatched_sync_failures
        record_path = module._attempt_record_path(path, "attempt-fsync-fault")
        if record_path.exists():
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if record.get("state") == "dispatched":
                dispatched_sync_failures += 1
                raise module.OrchestrationError("injected directory fsync failure")
        original_sync(path)

    monkeypatch.setattr(module, "_fsync_directory", fail_dispatched_sync)
    dispatched: list[str] = []

    def dispatch() -> str:
        dispatched.append("child-fsync-fault")
        return "child-fsync-fault"

    decision = module.dispatch_once(
        attempt_store=attempts,
        attempt_id="attempt-fsync-fault",
        intent_revision=9,
        execution_revision=EXECUTION_REVISION,
        dispatch=dispatch,
    )

    assert dispatched == ["child-fsync-fault"]
    assert dispatched_sync_failures == 1
    assert decision.code == "RECONCILE_REQUIRED"
    assert decision.code != "ALREADY_DISPATCHED"
    record_path = module._attempt_record_path(attempts.resolve(), "attempt-fsync-fault")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["state"] == "dispatch_ambiguous"
    assert record["child_job_id"] == "child-fsync-fault"


def _reopen_states() -> tuple[dict[str, object], dict[str, object]]:
    previous: dict[str, object] = {
        "observations": [
            {"id": "O-old", "evidence_ref": "ev:old", "source_group": "old"},
        ],
        "probes": [],
        "hypotheses": [
            {
                "id": "H-reopen",
                "status": "disproven",
                "revision": 3,
                "supporting_evidence": [],
                "contradicting_evidence": ["ev:old"],
            }
        ],
        "causal_assessment": {"status": "unknown", "causes": [], "unresolved_alternatives": []},
    }
    current = deepcopy(previous)
    observations = current["observations"]
    assert isinstance(observations, list)
    observations.append({"id": "O-new", "evidence_ref": "ev:new", "source_group": "new"})
    hypotheses = current["hypotheses"]
    assert isinstance(hypotheses, list) and isinstance(hypotheses[0], dict)
    hypotheses[0]["status"] = "active"
    hypotheses[0]["revision"] = 4
    hypotheses[0]["supporting_evidence"] = ["ev:new"]
    hypotheses[0]["reopen"] = {"from_revision": 3, "evidence_ref": "ev:new"}
    return previous, current


def test_reopen_rejects_fabricated_unregistered_evidence_ref() -> None:
    previous, current = _reopen_states()
    hypotheses = current["hypotheses"]
    assert isinstance(hypotheses, list) and isinstance(hypotheses[0], dict)
    hypotheses[0]["supporting_evidence"] = ["ev:fabricated"]
    hypotheses[0]["reopen"] = {"from_revision": 3, "evidence_ref": "ev:fabricated"}

    findings = validate_diagnostic_transition(previous, current)
    assert any("UNREGISTERED_REOPEN_EVIDENCE" in finding for finding in findings)


def test_reopen_rejects_mismatched_from_revision() -> None:
    previous, current = _reopen_states()
    hypotheses = current["hypotheses"]
    assert isinstance(hypotheses, list) and isinstance(hypotheses[0], dict)
    hypotheses[0]["reopen"] = {"from_revision": 999, "evidence_ref": "ev:new"}

    findings = validate_diagnostic_transition(previous, current)
    assert any("REOPEN_REVISION_MISMATCH" in finding for finding in findings)


def test_reopen_evidence_must_be_attached_as_supporting() -> None:
    previous, current = _reopen_states()
    hypotheses = current["hypotheses"]
    assert isinstance(hypotheses, list) and isinstance(hypotheses[0], dict)
    hypotheses[0]["supporting_evidence"] = []

    findings = validate_diagnostic_transition(previous, current)
    assert any("REOPEN_EVIDENCE_NOT_SUPPORTING" in finding for finding in findings)

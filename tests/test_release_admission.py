"""Release admission regressions: a concluded CI run is not proof of an audit.

The automatic release publishes from main when a CI run for a push to main
concludes successfully. A concluded run is not proof that the mandatory
exact-head integration audit executed: a job that is skipped, neutral, or
absent also lets the run conclude. These tests exercise the admission
verifier against the provider's own run and job records.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/verify_release_admission.py"

RELEASE_SHA = "a" * 40
OTHER_SHA = "b" * 40


def _load_script():
    spec = importlib.util.spec_from_file_location("verify_release_admission_target", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run_document(
    *,
    head_sha: str = RELEASE_SHA,
    name: str = "CI",
    event: str = "push",
    conclusion: str = "success",
) -> dict[str, object]:
    return {
        "id": 1234,
        "name": name,
        "event": event,
        "head_sha": head_sha,
        "head_branch": "main",
        "conclusion": conclusion,
    }


def _job(name: str, conclusion: str) -> dict[str, object]:
    return {"name": name, "conclusion": conclusion, "head_sha": RELEASE_SHA}


def _jobs_page(jobs: list[dict[str, object]]) -> dict[str, object]:
    return {"total_count": len(jobs), "jobs": jobs}


def _invoke(
    run: dict[str, object],
    job_pages: list[dict[str, object]],
    *,
    expected_sha: str = RELEASE_SHA,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--run-json",
            "-",
            "--jobs-json",
            "-",
            "--expected-sha",
            expected_sha,
        ],
        input=json.dumps(run) + "\n" + "\n".join(json.dumps(page) for page in job_pages) + "\n",
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_a_run_where_the_audit_executed_and_succeeded_is_accepted() -> None:
    completed = _invoke(
        _run_document(),
        [_jobs_page([_job("python", "success"), _job("exact-head", "success")])],
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "release admission: PASS" in completed.stdout


def test_a_skipped_audit_blocks_the_release() -> None:
    """T7: green other jobs with a skipped exact-head must not publish."""
    completed = _invoke(
        _run_document(),
        [_jobs_page([_job("python", "success"), _job("exact-head", "skipped")])],
    )
    assert completed.returncode == 1
    assert "RELEASE_ADMISSION_AUDIT_NOT_SUCCESSFUL" in completed.stdout
    assert "skipped" in completed.stdout


def test_a_neutral_audit_is_not_promoted_to_executed() -> None:
    """T13: a neutral required check is not evidence the audit ran."""
    completed = _invoke(
        _run_document(),
        [_jobs_page([_job("exact-head", "neutral")])],
    )
    assert completed.returncode == 1
    assert "RELEASE_ADMISSION_AUDIT_NOT_SUCCESSFUL" in completed.stdout


def test_an_absent_audit_blocks_the_release() -> None:
    completed = _invoke(
        _run_document(),
        [_jobs_page([_job("python", "success")])],
    )
    assert completed.returncode == 1
    assert "RELEASE_ADMISSION_AUDIT_ABSENT" in completed.stdout


def test_a_failed_audit_blocks_the_release() -> None:
    completed = _invoke(
        _run_document(),
        [_jobs_page([_job("exact-head", "failure")])],
    )
    assert completed.returncode == 1
    assert "RELEASE_ADMISSION_AUDIT_NOT_SUCCESSFUL" in completed.stdout


def test_an_unrelated_run_sha_is_not_evidence_for_the_published_revision() -> None:
    """T8: an older or unrelated successful run proves nothing for this SHA."""
    completed = _invoke(
        _run_document(head_sha=OTHER_SHA),
        [_jobs_page([_job("exact-head", "success")])],
    )
    assert completed.returncode == 1
    assert "RELEASE_ADMISSION_SHA_MISMATCH" in completed.stdout


def test_a_run_from_another_workflow_is_rejected() -> None:
    completed = _invoke(
        _run_document(name="Something Else"),
        [_jobs_page([_job("exact-head", "success")])],
    )
    assert completed.returncode == 1
    assert "RELEASE_ADMISSION_RUN_NOT_CI" in completed.stdout


def test_a_run_that_is_not_a_push_is_rejected() -> None:
    completed = _invoke(
        _run_document(event="pull_request"),
        [_jobs_page([_job("exact-head", "success")])],
    )
    assert completed.returncode == 1
    assert "RELEASE_ADMISSION_RUN_NOT_PUSH" in completed.stdout


def test_a_run_that_did_not_conclude_success_is_rejected() -> None:
    completed = _invoke(
        _run_document(conclusion="failure"),
        [_jobs_page([_job("exact-head", "success")])],
    )
    assert completed.returncode == 1
    assert "RELEASE_ADMISSION_RUN_NOT_SUCCESSFUL" in completed.stdout


def test_the_audit_is_found_across_paginated_job_records() -> None:
    first_page = [_job(f"matrix-{index}", "success") for index in range(30)]
    second_page = [_job("exact-head", "success")]
    completed = _invoke(_run_document(), [_jobs_page(first_page), _jobs_page(second_page)])
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_an_empty_job_record_cannot_prove_execution() -> None:
    completed = _invoke(_run_document(), [_jobs_page([])])
    assert completed.returncode == 1
    assert "RELEASE_ADMISSION_AUDIT_ABSENT" in completed.stdout


def test_the_verifier_exposes_a_typed_decision_surface() -> None:
    module = _load_script()
    decision = module.verify_admission(
        _run_document(),
        [_jobs_page([_job("exact-head", "skipped")])],
        expected_sha=RELEASE_SHA,
    )
    assert decision.accepted is False
    assert decision.reason == "RELEASE_ADMISSION_AUDIT_NOT_SUCCESSFUL"

#!/usr/bin/env python3
"""Fail closed unless the mandatory integration audit provably executed.

The automatic release publishes from main when a CI run for a push to main
concludes successfully. A concluded run is not proof that the mandatory
exact-head audit executed: a job that is skipped, neutral, failed, or absent
also lets the run conclude. This verifier reads the provider's own record of
the triggering run and demands positive evidence that the audit job executed
and succeeded on exactly the revision being published.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
DEFAULT_WORKFLOW = "CI"
DEFAULT_AUDIT_JOB = "exact-head"


@dataclass(frozen=True)
class AdmissionDecision:
    """The typed outcome of one admission check."""

    accepted: bool
    reason: str
    detail: str = ""


def _required_text(document: Mapping[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"the run record has no usable {key!r} field")
    return value


def verify_admission(
    run: Mapping[str, Any],
    job_pages: Sequence[Mapping[str, Any]],
    *,
    expected_sha: str,
    expected_workflow: str = DEFAULT_WORKFLOW,
    audit_job: str = DEFAULT_AUDIT_JOB,
) -> AdmissionDecision:
    """Decide whether the run record proves the audit executed on this SHA."""
    if FULL_SHA.fullmatch(expected_sha) is None:
        return AdmissionDecision(False, "RELEASE_ADMISSION_INPUT_INVALID", "expected SHA must be a full commit SHA")

    name = _required_text(run, "name")
    if name != expected_workflow:
        return AdmissionDecision(
            False,
            "RELEASE_ADMISSION_RUN_NOT_CI",
            f"run {name!r} is not the {expected_workflow!r} workflow",
        )

    event = _required_text(run, "event")
    if event != "push":
        return AdmissionDecision(
            False,
            "RELEASE_ADMISSION_RUN_NOT_PUSH",
            f"run event {event!r} is not a push to the integration branch",
        )

    head_sha = _required_text(run, "head_sha")
    if head_sha != expected_sha:
        return AdmissionDecision(
            False,
            "RELEASE_ADMISSION_SHA_MISMATCH",
            f"run head {head_sha} is not the published revision {expected_sha}",
        )

    conclusion = _required_text(run, "conclusion")
    if conclusion != "success":
        return AdmissionDecision(
            False,
            "RELEASE_ADMISSION_RUN_NOT_SUCCESSFUL",
            f"run conclusion is {conclusion!r}",
        )

    jobs: list[Mapping[str, Any]] = []
    for page in job_pages:
        raw_jobs = page.get("jobs")
        if not isinstance(raw_jobs, list):
            raise ValueError("a job page record has no jobs list")
        jobs.extend(item for item in raw_jobs if isinstance(item, Mapping))

    audit_jobs = [job for job in jobs if job.get("name") == audit_job]
    if not audit_jobs:
        return AdmissionDecision(
            False,
            "RELEASE_ADMISSION_AUDIT_ABSENT",
            f"no job named {audit_job!r} executed in the triggering run",
        )
    if any(job.get("conclusion") == "success" for job in audit_jobs):
        return AdmissionDecision(True, "RELEASE_ADMISSION_ACCEPTED")
    observed = sorted({str(job.get("conclusion")) for job in audit_jobs})
    return AdmissionDecision(
        False,
        "RELEASE_ADMISSION_AUDIT_NOT_SUCCESSFUL",
        f"job {audit_job!r} concluded {observed} instead of success",
    )


def _json_documents(text: str) -> list[Mapping[str, Any]]:
    """Parse a stream of whitespace-separated JSON documents, failing closed."""
    decoder = json.JSONDecoder()
    documents: list[Mapping[str, Any]] = []
    index = 0
    length = len(text)
    while index < length:
        while index < length and text[index] in " \t\r\n":
            index += 1
        if index >= length:
            break
        document, index = decoder.raw_decode(text, index)
        if not isinstance(document, Mapping):
            raise ValueError("admission input contains a non-object JSON document")
        documents.append(document)
    return documents


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-json", required=True, help="Workflow run document ('-' shares the stdin stream).")
    parser.add_argument("--jobs-json", required=True, help="Job page documents ('-' shares the stdin stream).")
    parser.add_argument("--expected-sha", required=True, help="The exact revision being published.")
    parser.add_argument("--expected-workflow", default=DEFAULT_WORKFLOW)
    parser.add_argument("--audit-job", default=DEFAULT_AUDIT_JOB)
    args = parser.parse_args(argv)

    try:
        if args.run_json == "-" and args.jobs_json == "-":
            documents = _json_documents(sys.stdin.read())
            if len(documents) < 2:
                raise ValueError("stdin must carry the run document followed by the job page documents")
            run, job_pages = documents[0], documents[1:]
        else:
            run = _json_documents(Path(args.run_json).read_text(encoding="utf-8"))[0]
            job_pages = _json_documents(Path(args.jobs_json).read_text(encoding="utf-8"))
        decision = verify_admission(
            run,
            job_pages,
            expected_sha=args.expected_sha,
            expected_workflow=args.expected_workflow,
            audit_job=args.audit_job,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: RELEASE_ADMISSION_INPUT_INVALID: {error}")
        return 1

    if decision.accepted:
        print("release admission: PASS")
        return 0
    detail = f": {decision.detail}" if decision.detail else ""
    print(f"ERROR: {decision.reason}{detail}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

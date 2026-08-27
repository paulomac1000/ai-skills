#!/usr/bin/env python3
"""Classify GitHub Actions run evidence without confusing provider failures with code results."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

RunClass = Literal[
    "executed-pass",
    "executed-fail",
    "provider-no-runner",
    "cancelled",
    "queued",
    "missing-evidence",
]


def _jobs(document: object) -> list[Mapping[str, Any]]:
    if isinstance(document, Mapping):
        raw = document.get("jobs", document.get("workflow_jobs"))
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, Mapping)]
    if isinstance(document, list):
        return [item for item in document if isinstance(item, Mapping)]
    return []


def _executed(job: Mapping[str, Any]) -> bool:
    runner_id = job.get("runner_id")
    steps = job.get("steps")
    return bool(runner_id) or (isinstance(steps, list) and bool(steps))


def classify_run(run: Mapping[str, Any], jobs_document: object) -> RunClass:
    """Return a conservative evidence class for one workflow run and its jobs."""
    jobs = _jobs(jobs_document)
    status = str(run.get("status") or "").casefold()
    conclusion = str(run.get("conclusion") or "").casefold()

    if status in {"queued", "waiting", "pending", "requested", "in_progress"}:
        return "queued"
    if conclusion in {"cancelled", "canceled", "skipped", "stale"}:
        return "cancelled"
    if conclusion == "success":
        return "executed-pass" if jobs and all(_executed(job) for job in jobs) else "missing-evidence"
    if conclusion in {"failure", "timed_out", "action_required", "startup_failure"}:
        if jobs and all(not _executed(job) for job in jobs):
            return "provider-no-runner"
        if any(_executed(job) for job in jobs):
            return "executed-fail"
        return "missing-evidence"
    return "missing-evidence"


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-json", type=Path, required=True)
    parser.add_argument("--jobs-json", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        run = _load(args.run_json)
        jobs = _load(args.jobs_json)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    if not isinstance(run, Mapping):
        parser.error("run JSON must be an object")
    result = classify_run(run, jobs)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

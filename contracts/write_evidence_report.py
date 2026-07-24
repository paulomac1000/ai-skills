#!/usr/bin/env python3
"""Write one canonical machine-readable GitHub Actions evidence report."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

FULL_SHA = re.compile(r"[0-9a-f]{40}")


def _positive(value: int, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")
    return value.strip()


def _load_claims(path: Path) -> list[Mapping[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("claims file must contain a non-empty JSON array")
    claims: list[Mapping[str, Any]] = []
    for index, claim in enumerate(payload):
        if not isinstance(claim, Mapping):
            raise ValueError(f"claim {index} must be an object")
        for field in ("kind", "subject", "result"):
            _text(claim.get(field), f"claim {index}.{field}")
        if claim.get("result") != "passed":
            raise ValueError(f"claim {index}.result must be passed")
        claims.append(dict(claim))
    return claims


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--check-run-id", required=True, type=int)
    parser.add_argument("--workflow-path", required=True)
    parser.add_argument("--workflow-name", required=True)
    parser.add_argument(
        "--event",
        required=True,
        choices=("pull_request", "push", "workflow_dispatch", "workflow_run"),
    )
    parser.add_argument("--job-name", required=True)
    parser.add_argument("--lane", required=True)
    parser.add_argument("--claims-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository = _text(args.repository, "repository")
    if repository.count("/") != 1:
        raise ValueError("repository must use owner/name")
    revision = _text(args.revision, "revision")
    if FULL_SHA.fullmatch(revision) is None:
        raise ValueError("revision must be a full lowercase commit SHA")
    workflow_path = _text(args.workflow_path, "workflow_path")
    if not workflow_path.startswith(".github/workflows/") or not workflow_path.endswith((".yml", ".yaml")):
        raise ValueError("workflow_path must identify a .github/workflows YAML file")

    report = {
        "schema_version": 1,
        "repository": repository,
        "revision": revision,
        "run_id": _positive(args.run_id, "run_id"),
        "check_run_id": _positive(args.check_run_id, "check_run_id"),
        "workflow_path": workflow_path,
        "workflow_name": _text(args.workflow_name, "workflow_name"),
        "event": args.event,
        "job_name": _text(args.job_name, "job_name"),
        "lane": _text(args.lane, "lane"),
        "claims": _load_claims(args.claims_file),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

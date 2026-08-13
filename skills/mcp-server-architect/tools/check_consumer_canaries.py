#!/usr/bin/env python3
"""Validate source-inspection adoption canaries against exact real-consumer revisions."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml
from inspect_existing_project import inspect_repository
from plan_existing_project import build_plan

REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
FULL_SHA = re.compile(r"[0-9a-f]{40}")
CANARY_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
TARGET_LEVELS = {"L1", "L2", "L3", "L4"}
PROOF_LEVEL = "source-inspection"


def _run(argv: list[str], *, cwd: Path, timeout: int = 120) -> None:
    environment = dict(os.environ)
    environment.update({"GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1"})
    for name in ("GITHUB_TOKEN", "GH_TOKEN", "CI_JOB_TOKEN", "SYSTEM_ACCESSTOKEN"):
        environment.pop(name, None)
    subprocess.run(  # noqa: S603 - fixed git executable and validated repository/SHA inputs.
        argv,
        cwd=cwd,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _materialize(repository: str, revision: str, target: Path) -> None:
    if REPOSITORY.fullmatch(repository) is None or FULL_SHA.fullmatch(revision) is None:
        raise ValueError("consumer canary requires owner/name and a full lowercase commit SHA")
    target.mkdir(parents=True, exist_ok=False)
    _run(["git", "init", "-q"], cwd=target)
    _run(
        ["git", "-c", "core.hooksPath=/dev/null", "remote", "add", "origin", f"https://github.com/{repository}.git"],
        cwd=target,
    )
    _run(
        ["git", "-c", "core.hooksPath=/dev/null", "fetch", "--depth=1", "--no-tags", "origin", revision],
        cwd=target,
    )
    _run(["git", "-c", "core.hooksPath=/dev/null", "checkout", "-q", "--detach", "FETCH_HEAD"], cwd=target)
    completed = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "HEAD"],
        cwd=target,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.stdout.strip() != revision:
        raise ValueError("materialized consumer revision does not match the canary pin")


def _lookup(document: dict[str, Any], dotted: str) -> Any:
    value: Any = document
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(dotted)
        value = value[part]
    return value


def check_catalog(catalog_path: Path, workspace: Path, *, materialize: bool) -> list[str]:
    raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        return ["consumer canary catalog must use schema_version 1"]
    canaries = raw.get("canaries")
    if not isinstance(canaries, list) or not canaries:
        return ["consumer canary catalog must contain canaries"]
    findings: list[str] = []
    for index, entry in enumerate(canaries):
        if not isinstance(entry, dict):
            findings.append(f"canaries[{index}] must be an object")
            continue
        canary_id = str(entry.get("id") or "")
        repository = str(entry.get("repository") or "")
        revision = str(entry.get("revision") or "")
        target_level = str(entry.get("target_level") or "L2")
        proof_level = str(entry.get("proof_level") or "")
        if CANARY_ID.fullmatch(canary_id) is None:
            findings.append(f"canaries[{index}].id is invalid")
            continue
        if proof_level != PROOF_LEVEL:
            findings.append(
                f"{canary_id}: cheap consumer canaries must declare proof_level={PROOF_LEVEL!r}; "
                "runtime behavior requires a separate fresh-context behavior canary"
            )
            continue
        if target_level not in TARGET_LEVELS:
            findings.append(f"{canary_id}: target_level must be one of {sorted(TARGET_LEVELS)}")
            continue
        if REPOSITORY.fullmatch(repository) is None or FULL_SHA.fullmatch(revision) is None:
            findings.append(f"canaries[{index}] must pin owner/name at an immutable full SHA")
            continue
        target = workspace / canary_id
        try:
            if not target.exists():
                if not materialize:
                    findings.append(f"{canary_id}: workspace is missing")
                    continue
                _materialize(repository, revision, target)
            discovery = inspect_repository(target)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            findings.append(f"{canary_id}: consumer materialization/inspection failed: {exc}")
            continue
        expected = entry.get("expected")
        if not isinstance(expected, dict) or not expected:
            findings.append(f"{canary_id}: expected facts are missing")
            continue
        for dotted, expected_value in sorted(expected.items()):
            try:
                observed = _lookup(discovery, dotted)
            except KeyError:
                findings.append(f"{canary_id}: expected path {dotted!r} was not discovered")
                continue
            if observed != expected_value:
                findings.append(f"{canary_id}: {dotted} expected {expected_value!r}, observed {observed!r}")

        plan = build_plan(target, target_level=target_level)
        if plan.get("format") != "ai-skills-mcp-adoption-plan":
            findings.append(f"{canary_id}: adoption planner returned an unexpected format")
        if not plan.get("applicable_rules") or not plan.get("applicable_controls"):
            findings.append(f"{canary_id}: adoption planner produced an empty applicability projection")
        if discovery["facts"]["external_upstream"] and discovery["plan"]["upstream_contract"] == "required":
            if not any("upstream-contract.yaml" in action for action in plan.get("next_actions", [])):
                findings.append(f"{canary_id}: adoption plan lost the upstream-contract discovery gate")

        discovery_report = workspace / f"{canary_id}.discovery.json"
        discovery_report.write_text(
            json.dumps(
                {"proof_level": proof_level, "discovery": discovery},
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        plan_report = workspace / f"{canary_id}.plan.json"
        plan_report.write_text(
            json.dumps(
                {"proof_level": proof_level, "plan": plan},
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path("contracts/consumer-canaries.yaml"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--no-materialize", action="store_true")
    args = parser.parse_args(argv)
    args.workspace.mkdir(parents=True, exist_ok=True)
    findings = check_catalog(args.catalog, args.workspace, materialize=not args.no_materialize)
    for finding in findings:
        print(f"ERROR: {finding}")
    print(f"consumer canary findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

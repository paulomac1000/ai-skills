#!/usr/bin/env python3
"""Write one canonical diagnostic GitHub Actions evidence report."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import yaml

FULL_SHA = re.compile(r"[0-9a-f]{40}")
CHECK_RUN = re.compile(r"/check-runs/([1-9][0-9]*)$")
API_BASE = "https://api.github.com"
EXECUTION_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")


def _positive(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")
    return value.strip()


def _sha(value: object, name: str) -> str:
    result = _text(value, name)
    if FULL_SHA.fullmatch(result) is None:
        raise ValueError(f"{name} must be a full lowercase commit SHA")
    return result


def _canonical_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _canonical_command_digest(argv: Sequence[str], working_directory: str) -> str:
    encoded = json.dumps(
        {"argv": list(argv), "working_directory": working_directory},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _junit_cases(path: Path) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(path.read_bytes())
    except ET.ParseError as exc:
        raise ValueError(f"{path}: result is not valid JUnit XML") from exc
    cases: list[dict[str, str]] = []
    seen: set[str] = set()
    for element in root.iter():
        if _tag(element) != "testcase":
            continue
        classname = str(element.attrib.get("classname") or "").strip()
        name = str(element.attrib.get("name") or "").strip()
        if not name:
            raise ValueError(f"{path}: testcase without a name")
        identity = f"{classname}::{name}" if classname else name
        if identity in seen:
            raise ValueError(f"{path}: duplicate testcase identity: {identity}")
        seen.add(identity)
        status = "passed"
        for child in element:
            child_tag = _tag(child)
            if child_tag in {"failure", "error", "skipped"}:
                status = child_tag
                break
        cases.append({"identity": identity, "status": status})
    if not cases:
        raise ValueError(f"{path}: JUnit document contains no test cases")
    if any(case["status"] in {"failure", "error"} for case in cases):
        raise ValueError(f"{path}: JUnit document contains failed or errored tests")
    return cases


def _safe_relative(value: object, name: str) -> str:
    path = _text(value, name)
    if path.startswith(("/", "\\")) or "\\" in path:
        raise ValueError(f"{name} must be a relative POSIX path")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"{name} must be a safe relative POSIX path")
    return path


def _load_plan(path: Path, profile: str | None) -> list[Mapping[str, Any]]:
    if profile is None:
        return []
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping) or document.get("format") != "ai-skills-claim-plan":
        raise ValueError("claim plan must use the canonical ai-skills-claim-plan format")
    profiles = document.get("profiles")
    if not isinstance(profiles, Mapping):
        raise ValueError("claim plan profiles must be an object")
    raw = profiles.get(profile)
    if not isinstance(raw, list):
        raise ValueError(f"claim profile {profile!r} does not exist")
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def _load_execution(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping) or document.get("format") != "ai-skills-execution-record":
        raise ValueError(f"{path}: unsupported execution record format")
    execution_id = _text(document.get("execution_id"), f"{path}.execution_id")
    if EXECUTION_ID.fullmatch(execution_id) is None:
        raise ValueError(f"{path}: invalid execution_id")
    argv = document.get("argv")
    if not isinstance(argv, list) or not argv or any(not isinstance(value, str) or not value for value in argv):
        raise ValueError(f"{path}: argv must be a non-empty string array")
    working_directory = str(document.get("working_directory") or "")
    if working_directory == ".":
        working_directory = "."
    else:
        working_directory = _safe_relative(working_directory, f"{path}.working_directory")
    expected_command_digest = _canonical_command_digest(argv, working_directory)
    if document.get("command_digest") != expected_command_digest:
        raise ValueError(f"{path}: command digest does not match argv and working directory")
    if document.get("exit_status") != 0:
        raise ValueError(f"{path}: execution did not complete successfully")
    if document.get("validation_error") is not None:
        raise ValueError(f"{path}: execution record contains a validation error")
    raw_results = document.get("results")
    if not isinstance(raw_results, list) or not raw_results:
        raise ValueError(f"{path}: execution record contains no result files")
    results: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for index, raw in enumerate(raw_results):
        if not isinstance(raw, Mapping):
            raise ValueError(f"{path}: results[{index}] must be an object")
        result_path = _safe_relative(raw.get("path"), f"{path}.results[{index}].path")
        if result_path in seen_paths:
            raise ValueError(f"{path}: duplicate result path {result_path}")
        seen_paths.add(result_path)
        candidate = Path(result_path) if working_directory == "." else Path(working_directory) / result_path
        if not candidate.is_file() or candidate.is_symlink():
            raise ValueError(f"{path}: result file {result_path} is missing or unsafe")
        digest = _canonical_digest(candidate)
        if raw.get("digest") != digest:
            raise ValueError(f"{path}: result digest does not match {result_path}")
        cases = raw.get("test_cases")
        if not isinstance(cases, list) or not cases:
            raise ValueError(f"{path}: result {result_path} contains no test cases")
        normalized_cases: list[dict[str, str]] = []
        for case_index, case in enumerate(cases):
            if not isinstance(case, Mapping):
                raise ValueError(f"{path}: test_cases[{case_index}] must be an object")
            normalized_cases.append(
                {
                    "identity": _text(case.get("identity"), f"{path}.test_cases[{case_index}].identity"),
                    "status": _text(case.get("status"), f"{path}.test_cases[{case_index}].status"),
                }
            )
        observed_cases = _junit_cases(candidate)
        if normalized_cases != observed_cases:
            raise ValueError(f"{path}: execution record test cases do not match JUnit bytes")
        results.append(
            {
                "path": result_path,
                "format": "junit",
                "digest": digest,
                "test_cases": normalized_cases,
                "summary": {
                    "tests": len(normalized_cases),
                    "passed": sum(case["status"] == "passed" for case in normalized_cases),
                    "skipped": sum(case["status"] == "skipped" for case in normalized_cases),
                    "failures": 0,
                    "errors": 0,
                },
            }
        )
    return {
        "execution_id": execution_id,
        "argv": list(argv),
        "working_directory": working_directory,
        "command_digest": expected_command_digest,
        "exit_status": 0,
        "results": results,
    }


def _load_executions(paths: Sequence[Path]) -> dict[str, dict[str, Any]]:
    executions: dict[str, dict[str, Any]] = {}
    for path in paths:
        execution = _load_execution(path)
        execution_id = str(execution["execution_id"])
        if execution_id in executions:
            raise ValueError(f"duplicate execution_id: {execution_id}")
        executions[execution_id] = execution
    if not executions:
        raise ValueError("at least one execution record is required")
    return executions


def _claim(
    raw: Mapping[str, Any],
    *,
    executions: Mapping[str, Mapping[str, Any]],
    location: str,
) -> dict[str, Any]:
    kind = _text(raw.get("kind"), f"{location}.kind")
    subject = _text(raw.get("subject"), f"{location}.subject")
    execution_id = _text(raw.get("execution_id"), f"{location}.execution_id")
    execution = executions.get(execution_id)
    if not isinstance(execution, Mapping):
        raise ValueError(f"{location}.execution_id does not identify an execution record")
    selectors = raw.get("selectors")
    if not isinstance(selectors, list) or not selectors:
        raise ValueError(f"{location}.selectors must be a non-empty array")
    selector_patterns = [_text(value, f"{location}.selectors") for value in selectors]
    result_files = raw.get("result_files")
    if result_files is None:
        result_patterns = ["*"]
    elif isinstance(result_files, list) and result_files:
        result_patterns = [_text(value, f"{location}.result_files") for value in result_files]
    else:
        raise ValueError(f"{location}.result_files must be a non-empty array")

    bindings: list[dict[str, Any]] = []
    for result in execution.get("results", []):
        if not isinstance(result, Mapping):
            continue
        result_path = str(result.get("path") or "")
        if not any(fnmatch.fnmatchcase(result_path, pattern) for pattern in result_patterns):
            continue
        selected = sorted(
            {
                str(case.get("identity"))
                for case in result.get("test_cases", [])
                if isinstance(case, Mapping)
                and case.get("status") == "passed"
                and any(fnmatch.fnmatchcase(str(case.get("identity") or ""), pattern) for pattern in selector_patterns)
            }
        )
        if selected:
            bindings.append(
                {
                    "result_path": result_path,
                    "result_digest": str(result["digest"]),
                    "test_cases": [{"identity": identity, "status": "passed"} for identity in selected],
                }
            )
    if not bindings:
        raise ValueError(f"{location} selectors matched no passed test case in execution {execution_id}")

    claim: dict[str, Any] = {
        "kind": kind,
        "subject": subject,
        "result": "passed",
        "execution_id": execution_id,
        "command_digest": str(execution["command_digest"]),
        "result_bindings": bindings,
        "exit_status": 0,
    }
    if "combination" in raw:
        claim["combination"] = raw["combination"]
    content_path = raw.get("content_path")
    if content_path is not None:
        path = Path(_text(content_path, f"{location}.content_path"))
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"{location}.content_path must identify an existing non-symlink file")
        claim["content_digest"] = _canonical_digest(path)
    commands = raw.get("commands")
    if commands is not None:
        if not isinstance(commands, list) or not commands:
            raise ValueError(f"{location}.commands must be a non-empty array")
        normalized = [_text(value, f"{location}.commands") for value in commands]
        encoded = json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        claim["commands_digest"] = f"sha256:{hashlib.sha256(encoded).hexdigest()}"
    return claim


def _api_json(path: str, token: str) -> object:
    request = Request(
        f"{API_BASE}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ai-skills-evidence-writer",
        },
    )
    with urlopen(request, timeout=20) as response:  # noqa: S310 - fixed GitHub API host.
        return json.load(response)


def _provider_metadata(args: argparse.Namespace) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    if args.provider_metadata_file is not None:
        document = json.loads(args.provider_metadata_file.read_text(encoding="utf-8"))
        if not isinstance(document, Mapping):
            raise ValueError("provider metadata file must contain an object")
        run = document.get("run")
        job = document.get("job")
        if not isinstance(run, Mapping) or not isinstance(job, Mapping):
            raise ValueError("provider metadata requires run and job objects")
        return run, job
    token = os.environ.get(args.github_token_env, "").strip()
    if not token:
        raise ValueError(f"{args.github_token_env} is required to resolve provider job identity")
    repository = args.repository
    run = _api_json(f"/repos/{repository}/actions/runs/{args.run_id}", token)
    jobs_document = _api_json(f"/repos/{repository}/actions/runs/{args.run_id}/jobs?per_page=100", token)
    if not isinstance(run, Mapping) or not isinstance(jobs_document, Mapping):
        raise ValueError("GitHub Actions metadata response has an invalid shape")
    jobs = jobs_document.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("GitHub Actions jobs response has an invalid shape")
    candidates = [job for job in jobs if isinstance(job, Mapping) and job.get("name") == args.job_name]
    if len(candidates) != 1:
        raise ValueError(f"expected exactly one current job named {args.job_name!r}, found {len(candidates)}")
    return run, candidates[0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-head-sha", required=True)
    parser.add_argument("--tested-checkout-sha", required=True)
    parser.add_argument("--merge-sha")
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--workflow-path", required=True)
    parser.add_argument("--workflow-name", required=True)
    parser.add_argument("--event", required=True, choices=("pull_request", "push", "workflow_dispatch", "workflow_run"))
    parser.add_argument("--job-name", required=True)
    parser.add_argument("--lane", required=True)
    parser.add_argument("--claims-plan", type=Path, default=Path("contracts/evidence-claim-plan.yaml"))
    parser.add_argument("--claims-profile")
    parser.add_argument("--dynamic-kind")
    parser.add_argument("--dynamic-subject")
    parser.add_argument("--dynamic-execution-id")
    parser.add_argument("--dynamic-combination-json")
    parser.add_argument("--dynamic-operating-system")
    parser.add_argument("--dynamic-architecture")
    parser.add_argument("--dynamic-runtime")
    parser.add_argument("--dynamic-version")
    parser.add_argument("--dynamic-lane")
    parser.add_argument("--dynamic-selector", action="append")
    parser.add_argument("--execution-record", required=True, action="append", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--provider-metadata-file", type=Path)
    parser.add_argument("--github-token-env", default="GITHUB_TOKEN")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository = _text(args.repository, "repository")
    if repository.count("/") != 1:
        raise ValueError("repository must use owner/name")
    source_head_sha = _sha(args.source_head_sha, "source_head_sha")
    tested_checkout_sha = _sha(args.tested_checkout_sha, "tested_checkout_sha")
    if tested_checkout_sha != source_head_sha:
        raise ValueError("tested_checkout_sha must equal source_head_sha")
    if args.merge_sha not in {None, "", source_head_sha}:
        raise ValueError("merge_sha is unsupported until it can be verified independently")
    workflow_path = _text(args.workflow_path, "workflow_path")
    if not workflow_path.startswith(".github/workflows/") or not workflow_path.endswith((".yml", ".yaml")):
        raise ValueError("workflow_path must identify a .github/workflows YAML file")

    run, job = _provider_metadata(args)
    run_id = _positive(args.run_id, "run_id")
    if run.get("id") != run_id:
        raise ValueError("provider run id does not match --run-id")
    workflow_id = _positive(run.get("workflow_id"), "workflow_id")
    provider_run_head_sha = _sha(run.get("head_sha"), "provider_run_head_sha")
    if provider_run_head_sha != source_head_sha:
        raise ValueError("provider run head_sha must equal source_head_sha")
    if run.get("path") != workflow_path or run.get("name") != args.workflow_name or run.get("event") != args.event:
        raise ValueError("provider run workflow identity does not match report arguments")
    if job.get("run_id") != run_id or job.get("name") != args.job_name:
        raise ValueError("provider job identity does not match report arguments")
    job_id = _positive(job.get("id"), "job_id")
    match = CHECK_RUN.search(str(job.get("check_run_url") or ""))
    if match is None:
        raise ValueError("provider job has no canonical check_run_url")
    check_run_id = _positive(int(match.group(1)), "check_run_id")
    actor = run.get("actor")
    if not isinstance(actor, Mapping):
        raise ValueError("provider run has no canonical actor")
    producer = {
        "provider": "github",
        "login": _text(actor.get("login"), "producer.login"),
        "id": _positive(actor.get("id"), "producer.id"),
    }

    executions = _load_executions(args.execution_record)
    raw_claims = _load_plan(args.claims_plan, args.claims_profile)
    if args.dynamic_kind or args.dynamic_subject or args.dynamic_execution_id:
        if not (args.dynamic_kind and args.dynamic_subject and args.dynamic_execution_id):
            raise ValueError("dynamic claim requires kind, subject, and execution_id")
        dynamic: dict[str, Any] = {
            "kind": args.dynamic_kind,
            "subject": args.dynamic_subject,
            "execution_id": args.dynamic_execution_id,
            "selectors": args.dynamic_selector or ["*"],
        }
        combination_values = (
            args.dynamic_operating_system,
            args.dynamic_architecture,
            args.dynamic_runtime,
            args.dynamic_version,
            args.dynamic_lane,
        )
        if args.dynamic_combination_json and any(combination_values):
            raise ValueError("use either dynamic combination JSON or individual combination fields")
        if args.dynamic_combination_json:
            combination = json.loads(args.dynamic_combination_json)
            if not isinstance(combination, Mapping):
                raise ValueError("dynamic combination must be a JSON object")
            dynamic["combination"] = dict(combination)
        elif any(combination_values):
            if not all(combination_values):
                raise ValueError("all dynamic combination fields are required together")
            dynamic["combination"] = {
                "operating_system": args.dynamic_operating_system,
                "architecture": args.dynamic_architecture,
                "runtime": args.dynamic_runtime,
                "version": args.dynamic_version,
                "lane": args.dynamic_lane,
            }
        raw_claims.append(dynamic)
    if not raw_claims:
        raise ValueError("at least one evidence claim is required")
    claims = [_claim(raw, executions=executions, location=f"claims[{index}]") for index, raw in enumerate(raw_claims)]

    results_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    execution_summaries: list[dict[str, Any]] = []
    for execution_id in sorted(executions):
        execution = executions[execution_id]
        result_digests: list[str] = []
        for result in execution["results"]:
            key = (str(result["path"]), str(result["digest"]))
            results_by_key[key] = dict(result)
            result_digests.append(str(result["digest"]))
        execution_summaries.append(
            {
                "execution_id": execution_id,
                "argv": execution["argv"],
                "working_directory": execution["working_directory"],
                "command_digest": execution["command_digest"],
                "exit_status": execution["exit_status"],
                "result_digests": sorted(result_digests),
            }
        )

    report = {
        "format": "ai-skills-evidence-report",
        "evidence_role": "diagnostic",
        "repository": repository,
        "revision": source_head_sha,
        "source_head_sha": source_head_sha,
        "tested_checkout_sha": tested_checkout_sha,
        "merge_sha": None,
        "provider_run_head_sha": provider_run_head_sha,
        "run_id": run_id,
        "job_id": job_id,
        "check_run_id": check_run_id,
        "workflow_id": workflow_id,
        "workflow_path": workflow_path,
        "workflow_name": _text(args.workflow_name, "workflow_name"),
        "event": args.event,
        "job_name": _text(args.job_name, "job_name"),
        "lane": _text(args.lane, "lane"),
        "producer": producer,
        "executions": execution_summaries,
        "results": [results_by_key[key] for key in sorted(results_by_key)],
        "claims": claims,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

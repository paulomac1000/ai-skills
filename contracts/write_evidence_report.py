#!/usr/bin/env python3
"""Write one canonical, machine-bound GitHub Actions evidence report."""

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


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _junit_cases(paths: Sequence[Path]) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    cases: list[dict[str, str]] = []
    results: list[dict[str, Any]] = []
    for path in paths:
        root = ET.fromstring(path.read_bytes())
        file_cases: list[dict[str, str]] = []
        for element in root.iter():
            if _tag(element) != "testcase":
                continue
            classname = str(element.attrib.get("classname") or "").strip()
            name = str(element.attrib.get("name") or "").strip()
            if not name:
                raise ValueError(f"{path}: testcase without a name")
            identity = f"{classname}::{name}" if classname else name
            status = "passed"
            for child in element:
                child_tag = _tag(child)
                if child_tag in {"failure", "error", "skipped"}:
                    status = child_tag
                    break
            file_cases.append({"identity": identity, "status": status, "result_path": path.as_posix()})
        if not file_cases:
            raise ValueError(f"{path}: JUnit document contains no test cases")
        failed = [case for case in file_cases if case["status"] in {"failure", "error"}]
        if failed:
            raise ValueError(f"{path}: JUnit document contains failed or errored tests")
        cases.extend(file_cases)
        results.append(
            {
                "path": path.as_posix(),
                "format": "junit",
                "digest": _canonical_digest(path),
                "summary": {
                    "tests": len(file_cases),
                    "passed": sum(case["status"] == "passed" for case in file_cases),
                    "skipped": sum(case["status"] == "skipped" for case in file_cases),
                    "failures": sum(case["status"] == "failure" for case in file_cases),
                    "errors": sum(case["status"] == "error" for case in file_cases),
                },
            }
        )
    return cases, results


def _load_plan(path: Path, profile: str | None) -> list[Mapping[str, Any]]:
    if profile is None:
        return []
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping) or document.get("schema_version") != 1:
        raise ValueError("claim plan must be a schema_version 1 object")
    profiles = document.get("profiles")
    if not isinstance(profiles, Mapping):
        raise ValueError("claim plan profiles must be an object")
    raw = profiles.get(profile)
    if not isinstance(raw, list):
        raise ValueError(f"claim profile {profile!r} does not exist")
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def _matching_cases(
    cases: Sequence[Mapping[str, str]],
    selectors: object,
    result_files: object,
    location: str,
) -> list[str]:
    if not isinstance(selectors, list) or not selectors:
        raise ValueError(f"{location}.selectors must be a non-empty array")
    patterns = [_text(value, f"{location}.selectors") for value in selectors]
    if result_files is None:
        result_patterns = ["*"]
    elif isinstance(result_files, list) and result_files:
        result_patterns = [_text(value, f"{location}.result_files") for value in result_files]
    else:
        raise ValueError(f"{location}.result_files must be a non-empty array")
    selected = sorted(
        {
            str(case["identity"])
            for case in cases
            if case.get("status") == "passed"
            and any(fnmatch.fnmatchcase(str(case.get("result_path") or ""), pattern) for pattern in result_patterns)
            and any(fnmatch.fnmatchcase(str(case.get("identity") or ""), pattern) for pattern in patterns)
        }
    )
    if not selected:
        raise ValueError(f"{location} selectors matched no passed test case")
    return selected


def _claim(
    raw: Mapping[str, Any],
    *,
    cases: Sequence[Mapping[str, str]],
    results: Sequence[Mapping[str, Any]],
    location: str,
) -> dict[str, Any]:
    kind = _text(raw.get("kind"), f"{location}.kind")
    subject = _text(raw.get("subject"), f"{location}.subject")
    command = _text(raw.get("command"), f"{location}.command")
    selected = _matching_cases(cases, raw.get("selectors"), raw.get("result_files"), location)
    result_digests = [str(result["digest"]) for result in results]
    claim: dict[str, Any] = {
        "kind": kind,
        "subject": subject,
        "result": "passed",
        "command_digest": f"sha256:{hashlib.sha256(command.encode('utf-8')).hexdigest()}",
        "result_digests": result_digests,
        "test_cases": selected,
        "exit_status": 0,
    }
    for key in ("combination",):
        if key in raw:
            claim[key] = raw[key]
    content_path = raw.get("content_path")
    if content_path is not None:
        path = Path(_text(content_path, f"{location}.content_path"))
        if not path.is_file():
            raise ValueError(f"{location}.content_path must identify an existing file")
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
    parser.add_argument(
        "--event",
        required=True,
        choices=("pull_request", "push", "workflow_dispatch", "workflow_run"),
    )
    parser.add_argument("--job-name", required=True)
    parser.add_argument("--lane", required=True)
    parser.add_argument("--claims-plan", type=Path, default=Path("contracts/evidence-claim-plan.yaml"))
    parser.add_argument("--claims-profile")
    parser.add_argument("--dynamic-kind")
    parser.add_argument("--dynamic-subject")
    parser.add_argument("--dynamic-command")
    parser.add_argument("--dynamic-combination-json")
    parser.add_argument("--dynamic-operating-system")
    parser.add_argument("--dynamic-architecture")
    parser.add_argument("--dynamic-runtime")
    parser.add_argument("--dynamic-version")
    parser.add_argument("--dynamic-lane")
    parser.add_argument("--dynamic-selector", action="append")
    parser.add_argument("--result-file", required=True, action="append", type=Path)
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
    merge_sha = None
    workflow_path = _text(args.workflow_path, "workflow_path")
    if not workflow_path.startswith(".github/workflows/") or not workflow_path.endswith((".yml", ".yaml")):
        raise ValueError("workflow_path must identify a .github/workflows YAML file")

    run, job = _provider_metadata(args)
    run_id = _positive(args.run_id, "run_id")
    if run.get("id") != run_id:
        raise ValueError("provider run id does not match --run-id")
    if run.get("workflow_id") is None:
        raise ValueError("provider run has no workflow_id")
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

    result_paths = [Path(path) for path in args.result_file]
    cases, results = _junit_cases(result_paths)
    raw_claims = _load_plan(args.claims_plan, args.claims_profile)
    if args.dynamic_kind or args.dynamic_subject or args.dynamic_command:
        if not (args.dynamic_kind and args.dynamic_subject and args.dynamic_command):
            raise ValueError("dynamic claim requires kind, subject, and command")
        dynamic: dict[str, Any] = {
            "kind": args.dynamic_kind,
            "subject": args.dynamic_subject,
            "command": args.dynamic_command,
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
    claims = [
        _claim(raw, cases=cases, results=results, location=f"claims[{index}]") for index, raw in enumerate(raw_claims)
    ]

    report = {
        "schema_version": 2,
        "repository": repository,
        "revision": source_head_sha,
        "source_head_sha": source_head_sha,
        "tested_checkout_sha": tested_checkout_sha,
        "merge_sha": merge_sha,
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
        "results": results,
        "claims": claims,
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

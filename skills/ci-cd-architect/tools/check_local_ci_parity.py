#!/usr/bin/env python3
"""Verify merge-blocking hosted gates map to faithful local entrypoints or hosted-only reasons."""

from __future__ import annotations

import argparse
import ast
import json
import os
import shlex
from pathlib import Path
from typing import Any

import yaml


def _workflow_triggers_pull_request(document: dict[str, Any]) -> bool:
    trigger = document.get("on", document.get(True))
    if isinstance(trigger, str):
        return trigger in {"pull_request", "pull_request_target"}
    if isinstance(trigger, list):
        return any(item in {"pull_request", "pull_request_target"} for item in trigger)
    if isinstance(trigger, dict):
        return any(key in trigger for key in ("pull_request", "pull_request_target"))
    return False


def _discover_merge_blocking_jobs(root: Path) -> set[str]:
    workflow_dir = root / ".github" / "workflows"
    if not workflow_dir.is_dir():
        return set()
    jobs: set[str] = set()
    for path in sorted((*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml"))):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or not _workflow_triggers_pull_request(document):
            continue
        workflow_jobs = document.get("jobs")
        if not isinstance(workflow_jobs, dict):
            raise ValueError(f"workflow jobs must be a mapping: {path.relative_to(root)}")
        for job_id, job in workflow_jobs.items():
            if not isinstance(job_id, str) or not job_id.strip() or not isinstance(job, dict):
                raise ValueError(f"invalid workflow job in {path.relative_to(root)}")
            if job.get("continue-on-error") is True:
                continue
            jobs.add(job_id)
    return jobs


def _confined_file(root: Path, reference: str) -> Path | None:
    raw = reference.split("#", 1)[0].strip()
    if not raw:
        return None
    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _entrypoint_path(root: Path, command: str) -> Path | None:
    try:
        tokens = shlex.split(command, posix=os.name != "nt")
    except ValueError:
        return None
    if not tokens:
        return None
    interpreters = {"python", "python3", "py", "bash", "sh", "pwsh", "powershell"}
    candidates = tokens[1:] if Path(tokens[0]).name.casefold() in interpreters else tokens
    for token in candidates:
        if token.startswith("-"):
            continue
        if "/" not in token and "\\" not in token and not Path(token).suffix:
            continue
        path = (root / token).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            return None
        return path
    return None


def _valid_local_entrypoint(root: Path, command: str) -> bool:
    path = _entrypoint_path(root, command)
    if path is None or not path.is_file():
        return False
    if path.suffix.casefold() == ".py":
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError):
            return False
        return True
    return os.access(path, os.X_OK)


def evaluate(policy: dict[str, Any], *, root: Path | None = None) -> dict[str, object]:
    if policy.get("schema_version") != 1:
        raise ValueError("unsupported schema_version")
    revision = policy.get("policy_revision")
    if not isinstance(revision, str) or not revision.strip():
        raise ValueError("policy_revision is required")
    gates = policy.get("gates")
    if not isinstance(gates, list) or not gates:
        raise ValueError("gates must be a non-empty list")

    missing: list[str] = []
    invalid: list[str] = []
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()

    for item in gates:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip():
            raise ValueError("each gate requires a string id")
        gate_id = item["id"]
        if gate_id in seen:
            invalid.append(gate_id)
            continue
        seen.add(gate_id)

        required = item.get("merge_blocking") is True
        local = item.get("local_entrypoint")
        hosted_only = item.get("hosted_only")
        reason = item.get("hosted_only_reason")
        policy_ref = item.get("policy_ref")
        dependency_ref = item.get("dependency_ref")

        if local is not None and (not isinstance(local, str) or not local.strip()):
            invalid.append(gate_id)
        if hosted_only not in {None, True, False}:
            invalid.append(gate_id)
        if hosted_only is True and (not isinstance(reason, str) or not reason.strip()):
            invalid.append(gate_id)
        if hosted_only is True and isinstance(local, str) and local.strip():
            invalid.append(gate_id)
        if required and not (isinstance(local, str) and local.strip()) and hosted_only is not True:
            missing.append(gate_id)
        if required and (not isinstance(policy_ref, str) or not policy_ref.strip()):
            invalid.append(gate_id)
        if (
            required
            and isinstance(local, str)
            and local.strip()
            and (not isinstance(dependency_ref, str) or not dependency_ref.strip())
        ):
            invalid.append(gate_id)

        if root is not None and required:
            safe_root = root.resolve()
            if not isinstance(policy_ref, str) or _confined_file(safe_root, policy_ref) is None:
                invalid.append(gate_id)
            if isinstance(local, str) and local.strip():
                if not _valid_local_entrypoint(safe_root, local):
                    invalid.append(gate_id)
                if not isinstance(dependency_ref, str) or _confined_file(safe_root, dependency_ref) is None:
                    invalid.append(gate_id)

        normalized.append(
            {
                "id": gate_id,
                "merge_blocking": required,
                "local_entrypoint": local,
                "hosted_only": hosted_only is True,
                "hosted_only_reason": reason,
                "policy_ref": policy_ref,
                "dependency_ref": dependency_ref,
            }
        )

    discovered: set[str] = set()
    unmapped: list[str] = []
    if root is not None:
        discovered = _discover_merge_blocking_jobs(root.resolve())
        policy_blocking = {str(item["id"]) for item in normalized if item["merge_blocking"] is True}
        unmapped = sorted(discovered - policy_blocking)

    return {
        "schema_version": 1,
        "policy_revision": revision,
        "gates": normalized,
        "discovered_merge_blocking_jobs": sorted(discovered),
        "unmapped_merge_blocking_jobs": unmapped,
        "missing_local_entrypoints": sorted(set(missing)),
        "invalid_gates": sorted(set(invalid)),
        "hosted_only_gates": sorted(item["id"] for item in normalized if item["hosted_only"]),
        "verdict": "pass" if not missing and not invalid and not unmapped else "fail",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        value = yaml.safe_load(args.policy.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("policy must be a mapping")
        result = evaluate(value, root=args.root)
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as error:
        print(json.dumps({"verdict": "fail", "error": str(error)}))
        return 2

    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

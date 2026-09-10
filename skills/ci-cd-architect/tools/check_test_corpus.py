#!/usr/bin/env python3
"""Verify intended test selection and observed execution completeness."""

from __future__ import annotations

import argparse
import fnmatch
import json
from collections.abc import Collection
from pathlib import Path
from typing import Any

import yaml

MAX_POLICY_BYTES = 256 * 1024
MAX_DISCOVERED = 100_000


def _load_policy(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if len(data) > MAX_POLICY_BYTES:
        raise ValueError("policy exceeds maximum size")
    value = yaml.safe_load(data)
    if not isinstance(value, dict):
        raise ValueError("policy must be a mapping")
    if value.get("schema_version") != 1:
        raise ValueError("unsupported schema_version")
    return value


def _confined(root: Path, value: str) -> Path:
    candidate = (root / value).resolve()
    candidate.relative_to(root.resolve())
    return candidate


def _discover(root: Path, patterns: list[str]) -> set[str]:
    files: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        if any(fnmatch.fnmatch(relative, pattern) for pattern in patterns):
            files.add(relative)
            if len(files) > MAX_DISCOVERED:
                raise ValueError("test discovery exceeds maximum supported file count")
    return files


def _read_manifest(root: Path, relative: str | None) -> set[str]:
    if relative is None:
        return set()
    path = _confined(root, relative)
    if path.is_symlink() or not path.is_file():
        raise ValueError("execution manifest must be a regular file")
    result: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        _confined(root, item)
        result.add(item)
    return result


def _paths(root: Path, values: Collection[str]) -> set[str]:
    result: set[str] = set()
    for raw in values:
        if not isinstance(raw, str) or not raw:
            raise ValueError("observed execution contains invalid path")
        _confined(root, raw)
        result.add(raw)
    return result


def evaluate(
    root: Path,
    policy: dict[str, Any],
    *,
    observed_executed: Collection[str] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    patterns = policy.get("include")
    if not isinstance(patterns, list) or not patterns or not all(isinstance(x, str) and x for x in patterns):
        raise ValueError("include must be a non-empty string list")
    mode = policy.get("mode")
    if mode not in {"automatic", "manifest"}:
        raise ValueError("mode must be automatic or manifest")
    revision = policy.get("policy_revision")
    if not isinstance(revision, str) or not revision.strip():
        raise ValueError("policy_revision is required")

    discovered = _discover(root, patterns)
    exclusions_raw = policy.get("exclusions", [])
    if not isinstance(exclusions_raw, list):
        raise ValueError("exclusions must be a list")

    exclusions: dict[str, dict[str, Any]] = {}
    for item in exclusions_raw:
        if not isinstance(item, dict):
            raise ValueError("each exclusion must be a mapping")
        path = item.get("path")
        reason = item.get("reason")
        if not isinstance(path, str) or not path or not isinstance(reason, str) or not reason.strip():
            raise ValueError("exclusion requires path and reason")
        _confined(root, path)
        if path in exclusions:
            raise ValueError(f"duplicate exclusion: {path}")
        exclusions[path] = item

    excluded_discovered = discovered & exclusions.keys()
    stale_exclusions = set(exclusions) - discovered
    expected = discovered - set(exclusions)

    if mode == "automatic":
        selected = set(expected)
    else:
        manifest = policy.get("execution_manifest")
        if not isinstance(manifest, str) or not manifest:
            raise ValueError("manifest mode requires execution_manifest")
        selected = _read_manifest(root, manifest)

    missing_selection = expected - selected
    unexpected_selection = selected - expected
    selection_drift = missing_selection | unexpected_selection | stale_exclusions

    execution_evidence = "unknown" if observed_executed is None else "observed"
    observed = set() if observed_executed is None else _paths(root, observed_executed)
    missing_execution = set() if observed_executed is None else expected - observed
    unexpected_execution = set() if observed_executed is None else observed - expected
    execution_drift = missing_execution | unexpected_execution

    if selection_drift or execution_drift:
        verdict = "fail"
    elif observed_executed is None:
        verdict = "incomplete"
    else:
        verdict = "pass"
    completeness = "complete" if verdict == "pass" else ("unknown" if verdict == "incomplete" else "drift")

    return {
        "schema_version": 1,
        "policy_revision": revision,
        "mode": mode,
        "discovered_files": len(discovered),
        "selected_files": len(selected & expected),
        "executed_files": len(observed & expected),
        "excluded_files": [
            {
                "path": path,
                "reason": str(exclusions[path]["reason"]),
                "owner": exclusions[path].get("owner"),
                "expires_at": exclusions[path].get("expires_at"),
            }
            for path in sorted(excluded_discovered)
        ],
        "stale_exclusions": sorted(stale_exclusions),
        "missing_from_selection": sorted(missing_selection),
        "unexpected_in_selection": sorted(unexpected_selection),
        "missing_from_execution": sorted(missing_execution),
        "unexpected_in_execution": sorted(unexpected_execution),
        "discovery_drift": len(selection_drift | execution_drift),
        "execution_evidence": execution_evidence,
        "completeness": completeness,
        "verdict": verdict,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--executed-manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()

    try:
        observed = None
        if args.executed_manifest:
            manifest = args.executed_manifest.resolve()
            manifest.relative_to(root)
            observed = _read_manifest(root, manifest.relative_to(root).as_posix())
        result = evaluate(root, _load_policy(args.policy), observed_executed=observed)
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as error:
        print(json.dumps({"verdict": "fail", "error": str(error)}, sort_keys=True))
        return 2

    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    if result["verdict"] == "pass":
        return 0
    return 2 if result["verdict"] == "incomplete" else 1


if __name__ == "__main__":
    raise SystemExit(main())

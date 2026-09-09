#!/usr/bin/env python3
"""Verify that repository test discovery and the authoritative execution manifest agree."""

from __future__ import annotations

import argparse
import fnmatch
import json
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
    candidate.relative_to(root)
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
    lines = path.read_text(encoding="utf-8").splitlines()
    result = {line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")}
    for item in result:
        _confined(root, item)
    return result


def evaluate(root: Path, policy: dict[str, Any]) -> dict[str, Any]:
    patterns = policy.get("include")
    if not isinstance(patterns, list) or not patterns or not all(isinstance(x, str) and x for x in patterns):
        raise ValueError("include must be a non-empty string list")
    mode = policy.get("mode")
    if mode not in {"automatic", "manifest"}:
        raise ValueError("mode must be automatic or manifest")

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
        exclusions[path] = item

    excluded_discovered = discovered & exclusions.keys()
    stale_exclusions = exclusions.keys() - discovered
    expected = discovered - exclusions.keys()

    if mode == "automatic":
        executed = set(expected)
        manifest_extra: set[str] = set()
        missing: set[str] = set()
    else:
        manifest = policy.get("execution_manifest")
        if not isinstance(manifest, str) or not manifest:
            raise ValueError("manifest mode requires execution_manifest")
        executed = _read_manifest(root, manifest)
        missing = expected - executed
        manifest_extra = executed - expected

    drift = sorted(missing | manifest_extra)
    verdict = "pass" if not drift else "fail"
    return {
        "schema_version": 1,
        "policy_revision": str(policy.get("policy_revision", "unspecified")),
        "mode": mode,
        "discovered_files": len(discovered),
        "executed_files": len(executed & expected),
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
        "missing_from_execution": sorted(missing),
        "unexpected_in_execution": sorted(manifest_extra),
        "discovery_drift": len(drift),
        "verdict": verdict,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = args.root.resolve()
    try:
        result = evaluate(root, _load_policy(args.policy))
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as error:
        print(json.dumps({"verdict": "fail", "error": str(error)}, sort_keys=True))
        return 2

    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

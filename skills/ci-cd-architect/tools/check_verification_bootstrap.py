#!/usr/bin/env python3
"""Verify verdict-affecting tools resolve from declared or immutable dependency sources."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

MAX_POLICY_BYTES = 256 * 1024
MAX_SOURCE_BYTES = 64 * 1024 * 1024
PATH_SOURCE_TYPES = {"lockfile", "manifest", "tool-version-file", "bootstrap-script"}
SOURCE_TYPES = PATH_SOURCE_TYPES | {"immutable-image"}


def _read_bounded(path: Path, maximum: int, *, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is not a regular file: {path}")
    size = path.stat().st_size
    if size > maximum:
        raise ValueError(f"{label} exceeds maximum size")
    with path.open("rb") as handle:
        data = handle.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError(f"{label} exceeds maximum size")
    if len(data) != size:
        raise ValueError(f"{label} changed while being read")
    return data


def _load(path: Path) -> dict[str, Any]:
    data = _read_bounded(path, MAX_POLICY_BYTES, label="policy")
    value = yaml.safe_load(data)
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("unsupported or invalid bootstrap policy")
    return value


def _source(root: Path, item: dict[str, Any]) -> dict[str, str]:
    dependency_id = item.get("id")
    kind = item.get("source_type")
    if kind not in SOURCE_TYPES:
        raise ValueError(f"unsupported source_type for {dependency_id}")
    source = item.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError(f"source is required for {dependency_id}")

    if kind == "immutable-image":
        if "@sha256:" not in source or len(source.rsplit("@sha256:", 1)[1]) != 64:
            raise ValueError(f"immutable image must be digest-pinned for {dependency_id}")
        digest = source.rsplit("@", 1)[1]
        if any(character not in "0123456789abcdef" for character in digest.removeprefix("sha256:")):
            raise ValueError(f"immutable image digest must be lowercase hexadecimal for {dependency_id}")
        return {"kind": kind, "source": source, "source_digest": digest}

    path = (root / source).resolve()
    path.relative_to(root)
    data = _read_bounded(path, MAX_SOURCE_BYTES, label=f"declared dependency source {source}")
    return {
        "kind": kind,
        "source": source,
        "source_digest": "sha256:" + hashlib.sha256(data).hexdigest(),
    }


def evaluate(root: Path, policy: dict[str, Any]) -> dict[str, Any]:
    root = root.resolve()
    revision = policy.get("policy_revision")
    if not isinstance(revision, str) or not revision.strip():
        raise ValueError("policy_revision is required")
    dependencies = policy.get("dependencies")
    if not isinstance(dependencies, list):
        raise ValueError("dependencies must be a list")

    seen: set[str] = set()
    resolved: list[dict[str, str]] = []
    failures: list[str] = []
    for item in dependencies:
        if not isinstance(item, dict):
            raise ValueError("each dependency must be a mapping")
        dependency_id = item.get("id")
        version = item.get("resolved_version")
        if not isinstance(dependency_id, str) or not dependency_id.strip():
            raise ValueError("dependency id is required")
        if dependency_id in seen:
            raise ValueError(f"duplicate dependency id: {dependency_id}")
        seen.add(dependency_id)

        if not isinstance(version, str) or not version.strip():
            failures.append(f"{dependency_id}:resolved-version-missing")
        if item.get("resolution") != "declared":
            failures.append(f"{dependency_id}:ambient-or-unknown-resolution")
        try:
            source = _source(root, item)
        except ValueError as error:
            failures.append(str(error))
            continue
        expected = item.get("expected_version")
        if expected is not None and expected != version:
            failures.append(f"{dependency_id}:version-mismatch")
        resolved.append({"id": dependency_id, "resolved_version": str(version or ""), **source})

    network = policy.get("network")
    if network not in {"required", "offline-capable", "none"}:
        failures.append("network-assumption-missing")
    cache = policy.get("cache")
    if cache not in {"verified", "disabled"}:
        failures.append("cache-policy-missing-or-unverified")

    return {
        "schema_version": 1,
        "policy_revision": revision,
        "declared_dependencies_only": not failures,
        "resolved_dependencies": resolved,
        "network": network,
        "cache": cache,
        "failures": sorted(set(failures)),
        "verdict": "pass" if not failures else "fail",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        result = evaluate(args.root.resolve(), _load(args.policy))
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

#!/usr/bin/env python3
"""Verify verdict-affecting tools resolve from declared or immutable dependency sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

import yaml

MAX_POLICY_BYTES = 256 * 1024
MAX_SOURCE_BYTES = 64 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024
PATH_SOURCE_TYPES = {"lockfile", "manifest", "tool-version-file", "bootstrap-script"}
SOURCE_TYPES = PATH_SOURCE_TYPES | {"immutable-image"}
DEPENDENCY_OPERATIONS = {"dependency_bootstrap", "candidate_verification", "dependency_refresh"}
CACHE_POLICIES = {"verified", "disabled", "isolated"}
UPSTREAM_RESOLUTION = {"forbidden", "mutable", "immutable"}
LOCK_MUTATION = {"forbidden", "reviewable"}
REPRODUCIBILITY_CLAIMS = {"observational", "exact"}


def _digest_bound_identity(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    marker = "sha256:"
    marker_index = value.rfind(marker)
    if marker_index <= 0:
        return None
    prefix = value[:marker_index]
    if prefix[-1] not in {"@", ":"}:
        return None
    if "?" in prefix or "#" in prefix or any(character.isspace() for character in prefix):
        return None
    digest = value[marker_index:]
    hexadecimal = digest.removeprefix(marker)
    if len(hexadecimal) != 64 or any(character not in "0123456789abcdef" for character in hexadecimal):
        return None
    if marker_index + len(digest) != len(value):
        return None
    return digest


def _safe_identity_digest(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _metadata_changed(before: os.stat_result, after: os.stat_result) -> bool:
    return (
        not os.path.samestat(before, after)
        or before.st_size != after.st_size
        or getattr(before, "st_mtime_ns", None) != getattr(after, "st_mtime_ns", None)
        or getattr(before, "st_ctime_ns", None) != getattr(after, "st_ctime_ns", None)
    )


def _read_bounded(path: Path, maximum: int, *, label: str) -> bytes:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    expected: os.stat_result | None = None
    if not nofollow:
        expected = os.lstat(path)
        if stat.S_ISLNK(expected.st_mode):
            raise ValueError(f"{label} is not a regular file: {path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0) | nofollow
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ValueError(f"{label} cannot be opened safely: {path}: {error}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"{label} is not a regular file: {path}")
        if expected is not None and not os.path.samestat(expected, metadata):
            raise ValueError(f"{label} path identity changed while opening: {path}")
        if metadata.st_size > maximum:
            raise ValueError(f"{label} exceeds maximum size")
        remaining = maximum + 1
        chunks: list[bytes] = []
        while remaining > 0:
            chunk = os.read(descriptor, min(READ_CHUNK_BYTES, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > maximum:
            raise ValueError(f"{label} exceeds maximum size")
        if len(data) != metadata.st_size or _metadata_changed(metadata, os.fstat(descriptor)):
            raise ValueError(f"{label} changed while being read")
        return data
    finally:
        os.close(descriptor)


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


def _validate_lock_operation(
    policy: dict[str, Any],
    dependencies: list[dict[str, Any]],
    cache: Any,
    failures: list[str],
) -> tuple[str, dict[str, Any] | None]:
    operation = policy.get("operation", "dependency_bootstrap")
    if operation not in DEPENDENCY_OPERATIONS:
        failures.append("dependency-operation-invalid")
        return str(operation), None
    if operation == "dependency_bootstrap":
        if cache not in {"verified", "disabled"}:
            failures.append("dependency-bootstrap-cache-must-be-verified-or-disabled")
        return operation, None

    contract = policy.get("lock_contract")
    if not isinstance(contract, dict):
        failures.append("lock-contract-missing")
        return operation, None

    lock_sources = sum(1 for item in dependencies if item.get("source_type") == "lockfile")
    if lock_sources == 0:
        failures.append("lock-source-missing")

    upstream = contract.get("upstream_resolution")
    mutation = contract.get("lock_mutation")
    reviewable_diff = contract.get("reviewable_diff")
    summary: dict[str, Any] = {
        "upstream_resolution": upstream,
        "lock_mutation": mutation,
        "reviewable_diff": reviewable_diff,
    }

    if upstream not in UPSTREAM_RESOLUTION:
        failures.append("upstream-resolution-invalid")
    if mutation not in LOCK_MUTATION:
        failures.append("lock-mutation-invalid")

    if operation == "candidate_verification":
        if cache not in {"verified", "disabled"}:
            failures.append("candidate-verification-cache-must-be-verified-or-disabled")
        if upstream != "forbidden":
            failures.append("candidate-verification-must-not-reresolve-upstream")
        if mutation != "forbidden":
            failures.append("candidate-verification-lock-mutation-forbidden")
        if reviewable_diff is not False:
            failures.append("candidate-verification-reviewable-diff-must-be-false")
        return operation, summary

    if upstream not in {"mutable", "immutable"}:
        failures.append("refresh-upstream-resolution-required")
    identity = contract.get("upstream_identity")
    if not isinstance(identity, str) or not identity.strip():
        failures.append("refresh-upstream-identity-missing")
    immutable_source_digest = _digest_bound_identity(identity) if upstream == "immutable" else None
    if upstream == "immutable" and immutable_source_digest is None:
        failures.append("immutable-upstream-identity-must-be-digest-bound")

    declared_by_id = {item.get("id"): item for item in dependencies}
    resolver_dependency_id = contract.get("resolver_dependency_id")
    resolver = declared_by_id.get(resolver_dependency_id)
    if not isinstance(resolver_dependency_id, str) or not isinstance(resolver, dict):
        failures.append("refresh-resolver-dependency-missing")
    elif resolver.get("dependency_role") != "resolver":
        failures.append("refresh-resolver-dependency-role-invalid")

    runtime_dependency_id = contract.get("runtime_dependency_id")
    runtime = declared_by_id.get(runtime_dependency_id)
    if not isinstance(runtime_dependency_id, str) or not isinstance(runtime, dict):
        failures.append("refresh-runtime-dependency-missing")
    elif runtime.get("dependency_role") != "runtime":
        failures.append("refresh-runtime-dependency-role-invalid")
    if mutation != "reviewable":
        failures.append("refresh-lock-mutation-must-be-reviewable")
    if reviewable_diff is not True:
        failures.append("refresh-reviewable-diff-required")
    if cache not in {"disabled", "isolated"}:
        failures.append("refresh-cache-must-be-disabled-or-isolated")
    reproducibility = contract.get("reproducibility_claim")
    if reproducibility not in REPRODUCIBILITY_CLAIMS:
        failures.append("refresh-reproducibility-claim-invalid")
    elif reproducibility == "exact" and upstream != "immutable":
        failures.append("mutable-upstream-cannot-claim-exact-reproducibility")
    summary["reproducibility_claim"] = reproducibility
    summary["upstream_identity_digest"] = _safe_identity_digest(identity)
    summary["immutable_source_digest"] = immutable_source_digest
    summary["resolver_dependency_id"] = resolver_dependency_id
    summary["runtime_dependency_id"] = runtime_dependency_id
    return operation, summary


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
    if cache not in CACHE_POLICIES:
        failures.append("cache-policy-missing-or-unverified")

    operation, lock_contract = _validate_lock_operation(policy, dependencies, cache, failures)

    return {
        "schema_version": 1,
        "policy_revision": revision,
        "operation": operation,
        "declared_dependencies_only": not failures,
        "resolved_dependencies": resolved,
        "network": network,
        "cache": cache,
        "lock_contract": lock_contract,
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

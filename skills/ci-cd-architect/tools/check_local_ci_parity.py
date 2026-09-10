#!/usr/bin/env python3
"""Verify merge-blocking hosted gates map to faithful local entrypoints or hosted-only reasons."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


def evaluate(policy: dict[str, Any]) -> dict[str, object]:
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
        if required and isinstance(local, str) and local.strip() and (
            not isinstance(dependency_ref, str) or not dependency_ref.strip()
        ):
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

    return {
        "schema_version": 1,
        "policy_revision": revision,
        "gates": normalized,
        "missing_local_entrypoints": sorted(set(missing)),
        "invalid_gates": sorted(set(invalid)),
        "hosted_only_gates": sorted(item["id"] for item in normalized if item["hosted_only"]),
        "verdict": "pass" if not missing and not invalid else "fail",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        value = yaml.safe_load(args.policy.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("policy must be a mapping")
        result = evaluate(value)
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

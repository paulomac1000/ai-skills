#!/usr/bin/env python3
"""Verify every merge-blocking hosted gate maps to a local entrypoint or an explicit hosted-only reason."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


def evaluate(policy: dict[str, Any]) -> dict[str, object]:
    if policy.get("schema_version") != 1:
        raise ValueError("unsupported schema_version")
    gates = policy.get("gates")
    if not isinstance(gates, list) or not gates:
        raise ValueError("gates must be a non-empty list")
    missing: list[str] = []
    invalid: list[str] = []
    normalized: list[dict[str, object]] = []
    for item in gates:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("each gate requires a string id")
        gate_id = item["id"]
        required = item.get("merge_blocking") is True
        local = item.get("local_entrypoint")
        hosted_only = item.get("hosted_only")
        reason = item.get("hosted_only_reason")
        if local is not None and (not isinstance(local, str) or not local.strip()):
            invalid.append(gate_id)
        if hosted_only not in {None, True, False}:
            invalid.append(gate_id)
        if hosted_only is True and (not isinstance(reason, str) or not reason.strip()):
            invalid.append(gate_id)
        if required and not (isinstance(local, str) and local.strip()) and hosted_only is not True:
            missing.append(gate_id)
        normalized.append({"id": gate_id, "merge_blocking": required, "local_entrypoint": local, "hosted_only": hosted_only is True, "hosted_only_reason": reason})
    return {
        "schema_version": 1,
        "policy_revision": str(policy.get("policy_revision", "unspecified")),
        "gates": normalized,
        "missing_local_entrypoints": sorted(set(missing)),
        "invalid_gates": sorted(set(invalid)),
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

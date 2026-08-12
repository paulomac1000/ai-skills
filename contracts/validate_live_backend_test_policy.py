#!/usr/bin/env python3
"""Validate fail-closed live-backend test safety policy."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

DEFAULT_SCHEMA = Path(__file__).with_name("live-backend-test-policy.schema.json")
MAX_BYTES = 128 * 1024


def _load(path: Path) -> Mapping[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("live-backend policy must be a regular non-symlink file")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError(f"live-backend policy exceeds {MAX_BYTES} bytes")
    text = path.read_text(encoding="utf-8")
    try:
        value = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"invalid live-backend policy syntax: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ValueError("live-backend policy root must be an object")
    return value


def validate_policy(path: Path, schema_path: Path = DEFAULT_SCHEMA) -> list[str]:
    try:
        schema = _load(schema_path)
        document = _load(path)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return [str(exc)]
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in sorted(
            Draft202012Validator(schema).iter_errors(document),
            key=lambda item: tuple(str(part) for part in item.absolute_path),
        )
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args(argv)
    findings = validate_policy(args.policy, args.schema)
    for finding in findings:
        print(f"ERROR: {finding}")
    print(f"live-backend policy findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

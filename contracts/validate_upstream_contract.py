#!/usr/bin/env python3
"""Validate observed upstream contracts before adapter implementation."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

DEFAULT_SCHEMA = Path(__file__).with_name("upstream-contract.schema.json")
MAX_BYTES = 512 * 1024
SECRET_KEYS = {"token", "password", "secret", "api_key", "apikey", "credential"}
SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?:access[_-]?token|api[_-]?key|apikey|password|secret|credential|token)\s*[:=]\s*([^\s,;&]+)"
)
SAFE_SECRET_REFERENCES = {"redacted", "<redacted>", "***", "env", "secret-ref"}
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _load(path: Path) -> Mapping[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("upstream contract must be a regular non-symlink file")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError(f"upstream contract exceeds {MAX_BYTES} bytes")
    text = path.read_text(encoding="utf-8")
    try:
        value = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"invalid upstream contract syntax: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ValueError("upstream contract root must be an object")
    return value


def _contains_secret_key(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if normalized in SECRET_KEYS:
                return True
            if _contains_secret_key(child):
                return True
    elif isinstance(value, list):
        return any(_contains_secret_key(item) for item in value)
    elif isinstance(value, str):
        for match in SECRET_ASSIGNMENT.finditer(value):
            secret_value = match.group(1).strip().casefold()
            if secret_value.startswith(("$", "env:", "secret-ref:")) or secret_value in SAFE_SECRET_REFERENCES:
                continue
            return True
    return False


def _validate_mutation_outcome(index: int, observation: Mapping[str, Any]) -> list[str]:
    if str(observation.get("method") or "") not in MUTATING_METHODS:
        return []
    raw = observation.get("mutation_outcome")
    if not isinstance(raw, Mapping):
        return [
            f"observations.{index}.mutation_outcome: observed mutating operations must separate completion, identity, and representation uncertainty"
        ]
    findings: list[str] = []
    completion = raw.get("completion")
    identity = raw.get("identity")
    representation = raw.get("representation")
    reconciliation_required = raw.get("reconciliation_required")
    if completion == "unknown" and reconciliation_required is not True:
        findings.append(
            f"observations.{index}.mutation_outcome.reconciliation_required: completion=unknown requires reconciliation"
        )
    if completion == "confirmed-success" and identity == "unavailable" and reconciliation_required is not True:
        findings.append(
            f"observations.{index}.mutation_outcome.reconciliation_required: confirmed success without identity requires reconciliation"
        )
    if observation.get("response_body") == "empty" and representation == "available":
        findings.append(
            f"observations.{index}.mutation_outcome.representation: an empty success response cannot claim an available representation"
        )
    return findings


def validate_contract(path: Path, schema_path: Path = DEFAULT_SCHEMA, *, require_observed: bool = False) -> list[str]:
    try:
        schema = _load(schema_path)
        document = _load(path)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return [str(exc)]
    findings = [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in sorted(
            Draft202012Validator(schema).iter_errors(document),
            key=lambda item: tuple(str(part) for part in item.absolute_path),
        )
    ]
    if findings:
        return findings
    observations = document.get("observations")
    assert isinstance(observations, list)
    seen: set[str] = set()
    for index, raw in enumerate(observations):
        assert isinstance(raw, Mapping)
        operation = str(raw.get("operation") or "")
        if operation in seen:
            findings.append(f"observations.{index}.operation: duplicate operation {operation}")
        seen.add(operation)
        if require_observed and raw.get("confidence") == "inferred":
            findings.append(
                f"observations.{index}.confidence: inferred claims cannot satisfy observed-contract acceptance"
            )
        if require_observed:
            findings.extend(_validate_mutation_outcome(index, raw))
        if _contains_secret_key(raw):
            findings.append(f"observations.{index}: secret values do not belong in upstream contract evidence")
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--require-observed", action="store_true")
    args = parser.parse_args(argv)
    findings = validate_contract(args.contract, args.schema, require_observed=args.require_observed)
    for finding in findings:
        print(f"ERROR: {finding}")
    print(f"upstream contract findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

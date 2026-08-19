#!/usr/bin/env python3
"""Validate fail-closed live-backend test safety policy."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

CONTRACTS = Path(__file__).resolve().parent
if str(CONTRACTS) not in sys.path:
    sys.path.insert(0, str(CONTRACTS))

from confined_io import ConfinedReadError, read_utf8_bounded  # noqa: E402

DEFAULT_SCHEMA = Path(__file__).with_name("live-backend-test-policy.schema.json")
MAX_BYTES = 128 * 1024


def _load(path: Path, *, label: str = "live-backend policy") -> Mapping[str, Any]:
    """Load one mapping from a stable bounded snapshot of the requested path."""
    try:
        repository_root = path.parent.resolve(strict=True)
        text, _size = read_utf8_bounded(path, repository_root, MAX_BYTES)
    except ConfinedReadError as exc:
        if exc.code == "input.too-large":
            raise ValueError(f"{label} exceeds {MAX_BYTES} bytes") from exc
        raise ValueError(f"cannot read {label} safely: {exc}") from exc
    try:
        value = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"invalid {label} syntax: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} root must be an object")
    return value


def validate_policy(
    path: Path,
    schema_path: Path = DEFAULT_SCHEMA,
    *,
    require_safe_mutations: bool = True,
) -> list[str]:
    """Validate schema shape and, by default, the destructive live-evidence safety floor."""
    try:
        schema = _load(schema_path, label="live-backend policy schema")
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
    if findings or not require_safe_mutations:
        return findings

    mutations = document.get("mutations")
    assert isinstance(mutations, Mapping)
    target_identity = mutations.get("target_identity")
    if not isinstance(target_identity, Mapping):
        findings.append(
            "mutations.target_identity: destructive live evidence requires independently verified disposable-target identity"
        )
    else:
        if target_identity.get("verified_before_mutation") is not True:
            findings.append("mutations.target_identity.verified_before_mutation: must be true")
        if target_identity.get("exclusive_disposable_environment") is not True:
            findings.append("mutations.target_identity.exclusive_disposable_environment: must be true")
        if not str(target_identity.get("proof") or "").strip():
            findings.append("mutations.target_identity.proof: a concrete target-identity proof is required")

    cleanup = mutations.get("cleanup")
    assert isinstance(cleanup, Mapping)
    if cleanup.get("preclean_after_target_verification") is not True:
        findings.append(
            "mutations.cleanup.preclean_after_target_verification: pre-clean must be impossible until target verification succeeds"
        )
    strategies = cleanup.get("strategies")
    if not isinstance(strategies, list) or not strategies:
        findings.append("mutations.cleanup.strategies: at least one explicit cleanup strategy is required")
        strategies = []
    if mutations.get("unique_namespace") is True and "unique-namespace" not in strategies:
        findings.append(
            "mutations.cleanup.strategies: unique_namespace=true requires the unique-namespace cleanup strategy"
        )
    if mutations.get("unique_namespace") is False and "verified-baseline-difference" not in strategies:
        findings.append(
            "mutations.cleanup.strategies: resources without a safe namespace require verified-baseline-difference cleanup"
        )
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument(
        "--structural-only",
        action="store_true",
        help="Validate schema shape only; acceptance and discovery use the default strict mutation checks.",
    )
    args = parser.parse_args(argv)
    findings = validate_policy(
        args.policy,
        args.schema,
        require_safe_mutations=not args.structural_only,
    )
    for finding in findings:
        print(f"ERROR: {finding}")
    print(f"live-backend policy findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

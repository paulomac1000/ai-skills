#!/usr/bin/env python3
"""Validate provider-neutral evidence records and maturity ceilings."""

from __future__ import annotations

import argparse
import json
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

DEFAULT_SCHEMA = Path(__file__).with_name("evidence-provider.schema.json")
DEFAULT_PROFILES = Path(__file__).with_name("evidence-profiles.yaml")
MAX_DOCUMENT_BYTES = 512 * 1024
LEVELS = {"L1": 1, "L2": 2, "L3": 3, "L4": 4}


def _load_mapping(path: Path) -> Mapping[str, Any]:
    if path.is_symlink():
        raise ValueError(f"{path}: must not be a symlink")
    try:
        metadata = path.stat()
    except OSError as exc:
        raise ValueError(f"{path}: cannot inspect file: {exc}") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{path}: must be a regular file")
    if metadata.st_size > MAX_DOCUMENT_BYTES:
        raise ValueError(f"{path}: exceeds {MAX_DOCUMENT_BYTES} bytes")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"{path}: must be readable UTF-8: {exc}") from exc
    try:
        value = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"{path}: invalid structured data: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"{path}: root must be an object")
    return value


def validate_record(
    record_path: Path,
    *,
    target_level: str,
    deployment_profiles: frozenset[str] = frozenset(),
    schema_path: Path = DEFAULT_SCHEMA,
    profiles_path: Path = DEFAULT_PROFILES,
) -> list[str]:
    """Return schema, profile, and maturity findings for one evidence record."""
    try:
        record = _load_mapping(record_path)
        schema = _load_mapping(schema_path)
        profile_contract = _load_mapping(profiles_path)
    except ValueError as exc:
        return [str(exc)]

    findings = [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in sorted(
            Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(record),
            key=lambda item: tuple(str(part) for part in item.absolute_path),
        )
    ]
    if target_level not in LEVELS:
        return [*findings, f"unknown target maturity: {target_level}"]

    profile_name = record.get("profile")
    profiles = profile_contract.get("profiles")
    if not isinstance(profile_name, str) or not isinstance(profiles, Mapping):
        return findings
    profile = profiles.get(profile_name)
    if not isinstance(profile, Mapping):
        findings.append(f"profile: unknown evidence profile {profile_name!r}")
        return findings
    maximum = profile.get("maximum_maturity")
    if not isinstance(maximum, str) or maximum not in LEVELS:
        findings.append(f"profile {profile_name}: invalid maturity ceiling")
    elif LEVELS[target_level] > LEVELS[maximum]:
        findings.append(f"profile {profile_name}: cannot approve {target_level}; maximum is {maximum}")

    escalation = profile_contract.get("escalation")
    if isinstance(escalation, Mapping):
        for deployment_profile in sorted(deployment_profiles):
            required_profile = escalation.get(deployment_profile)
            if isinstance(required_profile, str) and profile_name != required_profile:
                findings.append(
                    f"deployment profile {deployment_profile!r} requires evidence profile {required_profile!r}"
                )
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    parser.add_argument("--target-level", required=True, choices=tuple(LEVELS))
    parser.add_argument("--deployment-profile", action="append", default=[])
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    args = parser.parse_args(argv)
    findings = validate_record(
        args.record,
        target_level=args.target_level,
        deployment_profiles=frozenset(args.deployment_profile),
        schema_path=args.schema,
        profiles_path=args.profiles,
    )
    for finding in findings:
        print(f"ERROR: {finding}")
    print(f"evidence provider findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

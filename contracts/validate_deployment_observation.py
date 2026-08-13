#!/usr/bin/env python3
"""Validate live/deployment observations without treating unavailable prerequisites as passes."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

DEFAULT_SCHEMA = Path(__file__).with_name("deployment-observation.schema.json")
MAX_BYTES = 512 * 1024


def _load(path: Path) -> object:
    if path.is_symlink() or not path.is_file():
        raise ValueError("deployment observation must be a regular non-symlink file")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError(f"deployment observation exceeds {MAX_BYTES} bytes")
    text = path.read_text(encoding="utf-8")
    if path.suffix.casefold() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def validate_observation(path: Path, schema_path: Path = DEFAULT_SCHEMA) -> list[str]:
    """Return schema and temporal-integrity findings for one deployment observation."""
    try:
        document = _load(path)
        schema = _load(schema_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError, ValueError) as exc:
        return [f"cannot load deployment observation: {exc}"]
    if not isinstance(schema, Mapping):
        return ["deployment observation schema root must be an object"]
    validator = Draft202012Validator(dict(schema), format_checker=FormatChecker())
    findings = [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(
            validator.iter_errors(document),
            key=lambda item: tuple(str(part) for part in item.absolute_path),
        )
    ]
    if findings or not isinstance(document, Mapping):
        return findings
    result = document.get("result")
    if isinstance(result, Mapping) and result.get("status") in {"passed", "failed"}:
        started = result.get("started_at")
        completed = result.get("completed_at")
        if isinstance(started, str) and isinstance(completed, str):
            try:
                started_text = started[:-1] + "+00:00" if started.endswith("Z") else started
                completed_text = completed[:-1] + "+00:00" if completed.endswith("Z") else completed
                started_at = datetime.fromisoformat(started_text)
                completed_at = datetime.fromisoformat(completed_text)
            except ValueError as exc:
                findings.append(f"result timestamps must be valid ISO 8601 date-times: {exc}")
            else:
                if started_at.tzinfo is None or completed_at.tzinfo is None:
                    findings.append("result timestamps must include a timezone offset")
                elif completed_at < started_at:
                    findings.append("result.completed_at must not precede result.started_at")
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observation", type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args(argv)
    findings = validate_observation(args.observation, args.schema)
    for finding in findings:
        print(f"ERROR: {finding}")
    print(f"deployment observation findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

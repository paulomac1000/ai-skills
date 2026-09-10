#!/usr/bin/env python3
"""Validate verification receipts structurally and semantically."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

CONTRACTS = Path(__file__).resolve().parent
DEFAULT_SCHEMA = CONTRACTS / "verification-receipt.schema.json"
MAX_RECEIPT_BYTES = 2 * 1024 * 1024


class VerificationReceiptError(ValueError):
    """Raised when a verification receipt overstates its evidence."""


def _load_mapping(path: Path, *, max_bytes: int = MAX_RECEIPT_BYTES) -> Mapping[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise VerificationReceiptError(f"not a regular file: {path}")
    try:
        size = path.stat().st_size
    except OSError as error:
        raise VerificationReceiptError(f"file cannot be inspected: {path}: {error}") from error
    if size > max_bytes:
        raise VerificationReceiptError(f"file exceeds {max_bytes} bytes: {path}")
    try:
        with path.open("rb") as handle:
            data = handle.read(max_bytes + 1)
    except OSError as error:
        raise VerificationReceiptError(f"file cannot be read: {path}: {error}") from error
    if len(data) > max_bytes:
        raise VerificationReceiptError(f"file exceeds {max_bytes} bytes: {path}")
    if len(data) != size:
        raise VerificationReceiptError(f"file changed while being read: {path}")
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerificationReceiptError(f"invalid UTF-8 JSON: {path}") from error
    if not isinstance(value, Mapping):
        raise VerificationReceiptError(f"JSON root must be an object: {path}")
    return value


def _non_negative_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise VerificationReceiptError(f"{field} must be a non-negative integer")
    return value


def validate_receipt_semantics(receipt: Mapping[str, Any]) -> list[str]:
    """Return deterministic semantic findings that JSON Schema arithmetic cannot express."""
    findings: list[str] = []
    corpus = receipt.get("test_corpus")
    if not isinstance(corpus, Mapping):
        return ["test_corpus must be an object"]

    try:
        discovered = _non_negative_int(corpus.get("discovered_files"), "test_corpus.discovered_files")
        executed = _non_negative_int(corpus.get("executed_files"), "test_corpus.executed_files")
        accounted = _non_negative_int(corpus.get("accounted_files"), "test_corpus.accounted_files")
    except VerificationReceiptError as error:
        return [str(error)]

    excluded = corpus.get("excluded_files")
    if not isinstance(excluded, Sequence) or isinstance(excluded, (str, bytes, bytearray)):
        return ["test_corpus.excluded_files must be an array"]

    paths: set[str] = set()
    for item in excluded:
        if not isinstance(item, Mapping):
            findings.append("test_corpus.excluded_files entries must be objects")
            continue
        path = item.get("path")
        if not isinstance(path, str) or not path:
            findings.append("test_corpus exclusion path must be non-empty")
            continue
        if path in paths:
            findings.append(f"duplicate test-corpus exclusion: {path}")
            continue
        paths.add(path)

    computed = executed + len(paths)
    if accounted != computed:
        findings.append("test_corpus.accounted_files must equal executed_files plus unique excluded_files")
    if accounted > discovered:
        findings.append("test_corpus accounts for more files than were discovered")

    if receipt.get("verdict") == "pass":
        if accounted != discovered:
            findings.append("pass requires every discovered file to be executed or explicitly excluded")
        if corpus.get("execution_evidence") != "observed":
            findings.append("pass requires observed execution evidence")
        if corpus.get("completeness") != "complete":
            findings.append("pass requires complete test-corpus evidence")
        if corpus.get("discovery_drift") != 0:
            findings.append("pass requires zero test discovery/execution drift")
    return sorted(set(findings))


def validate_receipt(
    receipt: Mapping[str, Any],
    *,
    schema: Mapping[str, Any] | None = None,
) -> list[str]:
    """Return schema and semantic findings for one receipt."""
    active_schema = schema or _load_mapping(DEFAULT_SCHEMA)
    resources: list[tuple[str, Resource[Any]]] = []
    for path in CONTRACTS.glob("*.schema.json"):
        candidate = _load_mapping(path)
        schema_id = candidate.get("$id")
        if isinstance(schema_id, str) and schema_id:
            resources.append((schema_id, Resource.from_contents(candidate)))
    validator = Draft202012Validator(
        active_schema,
        registry=Registry().with_resources(resources),
        format_checker=FormatChecker(),
    )
    findings = [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in sorted(
            validator.iter_errors(receipt),
            key=lambda item: tuple(str(part) for part in item.absolute_path),
        )
    ]
    findings.extend(validate_receipt_semantics(receipt))
    return sorted(set(findings))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = _load_mapping(args.receipt)
        findings = validate_receipt(receipt)
    except (OSError, VerificationReceiptError) as error:
        print(f"ERROR: {error}")
        return 2
    for finding in findings:
        print(f"ERROR: {finding}")
    print(f"verification receipt findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

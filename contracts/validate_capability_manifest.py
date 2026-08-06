#!/usr/bin/env python3
"""Validate language-neutral MCP capability manifests."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

DEFAULT_SCHEMA = Path(__file__).with_name("capability-manifest.schema.json")
MAX_MANIFEST_BYTES = 256 * 1024
_REQUIRED_APPROVAL_BINDINGS = {
    "principal",
    "capability",
    "target",
    "arguments-digest",
    "expires-at",
}


def _load_mapping(path: Path) -> Mapping[str, Any]:
    if path.is_symlink():
        raise ValueError("manifest must not be a symlink")
    if not path.is_file():
        raise ValueError("manifest must be a regular file")
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError(f"manifest exceeds {MAX_MANIFEST_BYTES} bytes")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("manifest must be UTF-8") from exc
    try:
        value = (
            json.loads(text)
            if path.suffix.lower() == ".json"
            else yaml.safe_load(text)
        )
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"invalid manifest syntax: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ValueError("manifest root must be an object")
    return value


def _semantic_findings(manifest: Mapping[str, Any]) -> list[str]:
    findings: list[str] = []
    operation = manifest.get("operation_kind")
    active_state = manifest.get("active_state")
    raw_extensions = manifest.get("extensions", {})
    extensions = raw_extensions if isinstance(raw_extensions, Mapping) else {}

    if active_state != "active":
        findings.append(
            "only active capability manifests may be registered or invoked"
        )

    if operation in {"write", "destructive"}:
        for flag in ("retryable", "idempotent", "reversible"):
            if (
                manifest.get(flag) is True
                and f"{flag}_rationale" not in extensions
            ):
                findings.append(
                    f"extensions.{flag}_rationale is required when a "
                    f"{operation} capability sets {flag}=true"
                )

    if manifest.get("requires_confirmation") is True:
        approval = manifest.get("approval")
        if not isinstance(approval, Mapping):
            findings.append(
                "approval record policy is required for "
                "confirmation-protected capabilities"
            )
        else:
            raw_binds = approval.get("binds", [])
            binds = set(raw_binds) if isinstance(raw_binds, list) else set()
            missing = sorted(_REQUIRED_APPROVAL_BINDINGS - binds)
            if missing:
                findings.append(f"approval.binds is missing {missing}")
    return findings


def validate_manifest(
    path: Path,
    schema_path: Path = DEFAULT_SCHEMA,
) -> list[str]:
    """Return deterministic schema and semantic findings for one manifest."""
    try:
        schema = _load_mapping(schema_path)
        manifest = _load_mapping(path)
    except (OSError, ValueError) as exc:
        return [str(exc)]

    findings = [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: "
        f"{error.message}"
        for error in sorted(
            Draft202012Validator(schema).iter_errors(manifest),
            key=lambda item: tuple(str(part) for part in item.absolute_path),
        )
    ]
    findings.extend(_semantic_findings(manifest))
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs="+", type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args(argv)

    total = 0
    for path in args.manifests:
        findings = validate_manifest(path, args.schema)
        total += len(findings)
        for finding in findings:
            print(f"ERROR: {path}: {finding}")
    print(f"capability manifest findings: {total}")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())

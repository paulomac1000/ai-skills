#!/usr/bin/env python3
"""Validate one already-bound trusted-source lock document without reopening its source path."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import validate_trusted_executable_sources as trusted_sources
import yaml
from jsonschema import Draft202012Validator


def parse_document(text: str, *, suffix: str) -> Mapping[str, Any]:
    """Parse a lock snapshot whose bytes have already been read from a trusted descriptor."""
    try:
        value = json.loads(text) if suffix.lower() == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"invalid trusted source lock syntax: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ValueError("trusted source lock root must be an object")
    return value


def validate_document(
    document: Mapping[str, Any],
    *,
    repository_root: Path,
    authority_roots: Mapping[str, Path] | None = None,
    require_authority: bool = False,
    schema_path: Path = trusted_sources.DEFAULT_SCHEMA,
) -> list[str]:
    """Validate one in-memory lock document against immutable authority checkouts."""
    try:
        schema = trusted_sources._load(schema_path)
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

    roots = dict(authority_roots or {})
    sources = document.get("sources")
    assert isinstance(sources, list)
    seen: set[str] = set()
    repository_root = repository_root.resolve(strict=True)
    for index, raw_source in enumerate(sources):
        assert isinstance(raw_source, Mapping)
        source_id = str(raw_source["id"])
        if source_id in seen:
            findings.append(f"sources.{index}.id: duplicate source id {source_id}")
        seen.add(source_id)
        authority_root = roots.get(source_id)
        if require_authority and authority_root is None:
            findings.append(f"sources.{index}: authority checkout is required for {source_id}")
        if raw_source.get("credential_access") != "none" and authority_root is None:
            findings.append(
                f"sources.{index}: credential-bearing trusted source {source_id} requires an authority checkout"
            )
        authority_identity_valid = authority_root is not None
        if authority_root is not None:
            try:
                trusted_sources._verify_authority_identity(
                    authority_root,
                    str(raw_source["repository"]),
                    str(raw_source["revision"]),
                )
            except ValueError as exc:
                authority_identity_valid = False
                findings.append(f"sources.{index}: {exc}")
        files = raw_source["files"]
        assert isinstance(files, list)
        for file_index, raw_file in enumerate(files):
            assert isinstance(raw_file, Mapping)
            expected = str(raw_file["sha256"])
            local_path = raw_file.get("local_path")
            if isinstance(local_path, str):
                try:
                    local = trusted_sources._safe_file(repository_root, local_path, "local_path")
                except ValueError as exc:
                    findings.append(f"sources.{index}.files.{file_index}: {exc}")
                else:
                    if trusted_sources._digest(local) != expected:
                        findings.append(
                            f"sources.{index}.files.{file_index}: local vendored digest does not match lock"
                        )
            if authority_root is not None and authority_identity_valid:
                try:
                    payload = trusted_sources._git_blob(
                        authority_root,
                        str(raw_source["revision"]),
                        str(raw_file["authority_path"]),
                    )
                except ValueError as exc:
                    findings.append(f"sources.{index}.files.{file_index}: {exc}")
                else:
                    if trusted_sources._digest_bytes(payload) != expected:
                        findings.append(f"sources.{index}.files.{file_index}: authority digest does not match lock")
    findings.extend(f"authority checkout has no lock entry: {source_id}" for source_id in sorted(set(roots) - seen))
    return findings

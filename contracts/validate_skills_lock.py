#!/usr/bin/env python3
"""Validate an immutable ai-skills consumer lock against optional local skill sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from jsonschema import Draft202012Validator

DEFAULT_SCHEMA = Path(__file__).with_name("ai-skills-lock.schema.json")
MAX_LOCK_BYTES = 256 * 1024
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MOVING_REVISIONS = {"main", "master", "head", "latest", "stable", "develop", "development"}
DEPRECATED_SKILL_NAMES = {"precommitcheck", "mcp-architect", "cicd-architect"}
SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _read_regular_utf8(path: Path, maximum: int) -> str:
    if path.is_symlink():
        raise ValueError("path must not be a symlink")
    try:
        metadata = path.stat()
    except OSError as exc:
        raise ValueError(f"cannot inspect path: {exc}") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("path must be a regular file")
    if metadata.st_size > maximum:
        raise ValueError(f"path exceeds {maximum} bytes")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"path must be readable UTF-8: {exc}") from exc


def _load_mapping(path: Path, maximum: int = MAX_LOCK_BYTES) -> Mapping[str, Any]:
    text = _read_regular_utf8(path, maximum)
    try:
        value = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"invalid structured data: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ValueError("document root must be an object")
    return value


def _safe_source(root: Path, raw: str) -> Path:
    if not raw or "\\" in raw:
        raise ValueError("normative entrypoint must use a non-empty POSIX path")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("normative entrypoint must remain inside skills root")
    try:
        current = root.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"cannot resolve skills root: {exc}") from exc
    for part in pure.parts:
        current /= part
        if not os.path.lexists(current):
            raise ValueError("normative entrypoint does not exist")
        try:
            mode = current.lstat().st_mode
        except OSError as exc:
            raise ValueError(f"cannot inspect normative entrypoint: {exc}") from exc
        if stat.S_ISLNK(mode):
            raise ValueError("normative entrypoint must not contain symlinks")
    _read_regular_utf8(current, MAX_SOURCE_BYTES)
    return current


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                value.update(chunk)
    except OSError as exc:
        raise ValueError(f"cannot hash normative source: {exc}") from exc
    return f"sha256:{value.hexdigest()}"


def validate_lock(
    lock_path: Path,
    schema_path: Path = DEFAULT_SCHEMA,
    skills_root: Path | None = None,
) -> list[str]:
    """Return deterministic schema, identity, and optional source findings."""
    try:
        schema = _load_mapping(schema_path)
        lock = _load_mapping(lock_path)
    except (OSError, ValueError) as exc:
        return [str(exc)]

    findings = [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in sorted(
            Draft202012Validator(schema).iter_errors(lock),
            key=lambda item: tuple(str(part) for part in item.absolute_path),
        )
    ]
    revision = lock.get("revision")
    if isinstance(revision, str) and revision.casefold() in MOVING_REVISIONS:
        findings.append("revision must be an immutable full commit SHA, not a moving ref")

    skills = lock.get("skills")
    if not isinstance(skills, Mapping):
        return findings
    for skill_name, raw_entry in skills.items():
        location = f"skills.{skill_name}"
        if not isinstance(skill_name, str) or not SKILL_NAME.fullmatch(skill_name):
            findings.append(f"{location}: invalid skill name")
            continue
        if skill_name in DEPRECATED_SKILL_NAMES:
            findings.append(f"{location}: deprecated or ambiguous skill name")
        if not isinstance(raw_entry, Mapping):
            continue
        version = raw_entry.get("version")
        if not isinstance(version, str) or not version.strip():
            findings.append(f"{location}.version: must be a non-empty string")
        skill_revision = raw_entry.get("revision")
        if isinstance(revision, str) and isinstance(skill_revision, str) and skill_revision != revision:
            findings.append(f"{location}.revision: must equal repository revision")
        entrypoint = raw_entry.get("normative_entrypoint")
        expected_prefix = f"skills/{skill_name}/"
        if isinstance(entrypoint, str) and not entrypoint.startswith(expected_prefix):
            findings.append(f"{location}.normative_entrypoint: must belong to the locked skill")
        if skills_root is None or not isinstance(entrypoint, str):
            continue
        try:
            source = _safe_source(skills_root, entrypoint)
            manifest = _load_mapping(
                skills_root / "skills" / skill_name / "manifest.yaml"
            )
            source_digest = _digest(source)
        except (OSError, ValueError) as exc:
            findings.append(f"{location}: {exc}")
            continue
        if version != manifest.get("version"):
            findings.append(f"{location}.version: does not match local manifest")
        manifest_entrypoint = manifest.get("normative_entrypoint")
        if entrypoint != f"skills/{skill_name}/{manifest_entrypoint}":
            findings.append(f"{location}.normative_entrypoint: does not match local manifest")
        expected_digest = raw_entry.get("content_digest")
        if isinstance(expected_digest, str) and expected_digest != source_digest:
            findings.append(f"{location}.content_digest: does not match normative source")
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lock", type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--skills-root", type=Path)
    args = parser.parse_args(argv)
    findings = validate_lock(args.lock, args.schema, args.skills_root)
    for finding in findings:
        print(f"ERROR: {finding}")
    print(f"skills lock findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

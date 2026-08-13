#!/usr/bin/env python3
"""Validate immutable executable-source pins and optional vendored copies."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

DEFAULT_SCHEMA = Path(__file__).with_name("trusted-executable-sources.schema.json")
MAX_LOCK_BYTES = 512 * 1024
MAX_SOURCE_BYTES = 8 * 1024 * 1024
GITHUB_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _load(path: Path) -> Mapping[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("trusted source lock must be a regular non-symlink file")
    if path.stat().st_size > MAX_LOCK_BYTES:
        raise ValueError(f"trusted source lock exceeds {MAX_LOCK_BYTES} bytes")
    text = path.read_text(encoding="utf-8")
    try:
        value = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"invalid trusted source lock syntax: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ValueError("trusted source lock root must be an object")
    return value


def _safe_file(root: Path, raw: str, name: str) -> Path:
    if not raw or "\\" in raw:
        raise ValueError(f"{name} must use a non-empty POSIX relative path")
    relative = Path(raw)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"{name} must stay inside its checkout root")
    root = root.resolve(strict=True)
    current = root
    for part in relative.parts:
        current /= part
        if os.path.lexists(current) and current.is_symlink():
            raise ValueError(f"{name} must not contain symlink components: {raw}")
    try:
        candidate = root.joinpath(*relative.parts).resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"{name} does not exist: {raw}") from exc
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{name} must stay inside its checkout root") from exc
    metadata = candidate.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{name} must be a regular non-symlink file: {raw}")
    if metadata.st_size > MAX_SOURCE_BYTES:
        raise ValueError(f"{name} exceeds {MAX_SOURCE_BYTES} bytes: {raw}")
    return candidate


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed git executable and argument vector.
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise ValueError(detail)
    return completed.stdout.strip()


def _repository_from_remote(value: str) -> str:
    remote = value.strip()
    prefixes = ("https://github.com/", "http://github.com/", "ssh://git@github.com/")
    for prefix in prefixes:
        if remote.startswith(prefix):
            remote = remote[len(prefix) :]
            break
    else:
        if remote.startswith("git@github.com:"):
            remote = remote[len("git@github.com:") :]
        else:
            raise ValueError("authority origin must be a GitHub owner/name remote")
    remote = remote.rstrip("/")
    if remote.endswith(".git"):
        remote = remote[:-4]
    if GITHUB_REPOSITORY.fullmatch(remote) is None:
        raise ValueError("authority origin must resolve to GitHub owner/name")
    return remote


def _verify_authority_identity(root: Path, repository: str, revision: str) -> None:
    try:
        top_level = Path(_git(root, "rev-parse", "--show-toplevel")).resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise ValueError(f"authority checkout is not a verifiable git checkout: {exc}") from exc
    if top_level != root.resolve(strict=True):
        raise ValueError("authority root must be the git checkout top level")
    head = _git(root, "rev-parse", "HEAD")
    if head != revision:
        raise ValueError(f"authority checkout HEAD {head!r} does not match locked revision {revision!r}")
    actual_repository = _repository_from_remote(_git(root, "remote", "get-url", "origin"))
    if actual_repository.casefold() != repository.casefold():
        raise ValueError(
            f"authority checkout repository {actual_repository!r} does not match locked repository {repository!r}"
        )


def _authority_roots(values: Sequence[str]) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for raw in values:
        source_id, separator, path = raw.partition("=")
        if not separator or not source_id or not path or source_id in roots:
            raise ValueError("--authority-root must use unique SOURCE_ID=PATH values")
        lexical = Path(path)
        if lexical.is_symlink():
            raise ValueError(f"authority root must not be a symlink: {path}")
        candidate = lexical.resolve(strict=True)
        if not candidate.is_dir():
            raise ValueError(f"authority root is not a directory: {path}")
        roots[source_id] = candidate
    return roots


def validate_lock(
    path: Path,
    *,
    repository_root: Path,
    authority_roots: Mapping[str, Path] | None = None,
    require_authority: bool = False,
    schema_path: Path = DEFAULT_SCHEMA,
) -> list[str]:
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
                _verify_authority_identity(
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
                    local = _safe_file(repository_root, local_path, "local_path")
                except ValueError as exc:
                    findings.append(f"sources.{index}.files.{file_index}: {exc}")
                else:
                    if _digest(local) != expected:
                        findings.append(
                            f"sources.{index}.files.{file_index}: local vendored digest does not match lock"
                        )
            if authority_root is not None and authority_identity_valid:
                try:
                    authority = _safe_file(
                        authority_root,
                        str(raw_file["authority_path"]),
                        "authority_path",
                    )
                except ValueError as exc:
                    findings.append(f"sources.{index}.files.{file_index}: {exc}")
                else:
                    if _digest(authority) != expected:
                        findings.append(f"sources.{index}.files.{file_index}: authority digest does not match lock")
    unknown_roots = sorted(set(roots) - seen)
    findings.extend(f"authority checkout has no lock entry: {source_id}" for source_id in unknown_roots)
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lock", type=Path)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--authority-root", action="append", default=[])
    parser.add_argument("--require-authority", action="store_true")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args(argv)
    try:
        roots = _authority_roots(args.authority_root)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    findings = validate_lock(
        args.lock,
        repository_root=args.repository_root,
        authority_roots=roots,
        require_authority=args.require_authority,
        schema_path=args.schema,
    )
    for finding in findings:
        print(f"ERROR: {finding}")
    print(f"trusted executable source findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

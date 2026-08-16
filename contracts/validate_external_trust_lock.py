#!/usr/bin/env python3
"""Bind a candidate trust lock to authority coordinates supplied outside the candidate checkout."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import validate_trusted_executable_sources as trusted_sources  # noqa: E402
from confined_io import confined_regular_file  # noqa: E402

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def validate_external_lock(
    lock_relative: str,
    *,
    candidate_root: Path,
    authority_root: Path,
    source_id: str,
    expected_repository: str,
    expected_revision: str,
    required_authority_paths: Sequence[str] = (),
) -> list[str]:
    """Validate lock bytes and prove its authority declaration equals external coordinates."""
    if trusted_sources.GITHUB_REPOSITORY.fullmatch(expected_repository) is None:
        return ["expected authority repository must use GitHub owner/name syntax"]
    if FULL_SHA.fullmatch(expected_revision) is None:
        return ["expected authority revision must be a full lowercase 40-character commit SHA"]
    try:
        lock_path = confined_regular_file(candidate_root, lock_relative)
        document = trusted_sources._load(lock_path)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return [str(exc)]
    if not isinstance(document, Mapping):
        return ["candidate trust lock must contain a mapping"]
    raw_sources = document.get("sources")
    if not isinstance(raw_sources, list):
        return ["candidate trust lock has no sources list"]
    matches = [source for source in raw_sources if isinstance(source, Mapping) and source.get("id") == source_id]
    if len(matches) != 1:
        return [f"candidate trust lock must contain exactly one source id {source_id!r}"]
    source: Mapping[str, Any] = matches[0]
    findings: list[str] = []
    if str(source.get("repository")) != expected_repository:
        findings.append(f"source {source_id!r} repository does not match externally supplied authority repository")
    if str(source.get("revision")) != expected_revision:
        findings.append(f"source {source_id!r} revision does not match externally supplied authority revision")
    raw_files = source.get("files")
    actual_paths: set[str] = set()
    if isinstance(raw_files, list):
        actual_paths = {
            str(item["authority_path"])
            for item in raw_files
            if isinstance(item, Mapping) and isinstance(item.get("authority_path"), str)
        }
    for required in sorted(set(required_authority_paths)):
        if required not in actual_paths:
            findings.append(f"source {source_id!r} is missing required trusted executable {required!r}")
    if findings:
        return findings
    return trusted_sources.validate_lock(
        lock_path,
        repository_root=candidate_root,
        authority_roots={source_id: authority_root},
        require_authority=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lock", help="Repository-relative lock path inside the candidate checkout")
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--authority-root", type=Path, required=True)
    parser.add_argument("--source-id", default="ai-skills")
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--require-authority-path", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        candidate_root = args.candidate_root.resolve(strict=True)
        authority_root = args.authority_root.resolve(strict=True)
        findings = validate_external_lock(
            args.lock,
            candidate_root=candidate_root,
            authority_root=authority_root,
            source_id=args.source_id,
            expected_repository=args.expected_repository,
            expected_revision=args.expected_revision,
            required_authority_paths=args.require_authority_path,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    for finding in findings:
        print(f"ERROR: {finding}")
    print(f"external trust-lock findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

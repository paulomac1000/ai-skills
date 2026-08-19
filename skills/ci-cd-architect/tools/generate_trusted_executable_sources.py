#!/usr/bin/env python3
"""Generate a trusted-executable source lock from an immutable authority checkout."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml

TOOLS = Path(__file__).resolve().parent
REPOSITORY_ROOT = TOOLS.parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from contracts import validate_trusted_executable_sources as trusted_sources  # noqa: E402

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def generate_lock(
    authority_root: Path,
    *,
    source_id: str,
    role: str,
    repository: str,
    revision: str,
    credential_access: str,
    authority_paths: Sequence[str],
) -> dict[str, object]:
    """Return a deterministic lock after verifying checkout identity and tracked immutable bytes."""
    lexical = authority_root
    if lexical.is_symlink():
        raise ValueError("authority root must not be a symlink")
    root = lexical.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("authority root must be a directory")
    if trusted_sources.GITHUB_REPOSITORY.fullmatch(repository) is None:
        raise ValueError("repository must use GitHub owner/name syntax")
    if FULL_SHA.fullmatch(revision) is None:
        raise ValueError("revision must be a full lowercase 40-character commit SHA")
    if not authority_paths:
        raise ValueError("at least one --authority-path is required")

    trusted_sources._verify_authority_identity(root, repository, revision)
    files: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_path in sorted(authority_paths):
        if raw_path in seen:
            raise ValueError(f"duplicate authority path: {raw_path}")
        seen.add(raw_path)
        authority_payload = trusted_sources._git_blob(root, revision, raw_path)
        files.append(
            {
                "authority_path": raw_path,
                "sha256": trusted_sources._digest_bytes(authority_payload),
            }
        )

    return {
        "schema_version": 1,
        "sources": [
            {
                "id": source_id,
                "role": role,
                "repository": repository,
                "revision": revision,
                "credential_access": credential_access,
                "files": files,
            }
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authority-root", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--source-id", default="ai-skills")
    parser.add_argument(
        "--role",
        choices=("auditor", "evidence-collector", "vendored-validator", "provider-correlator"),
        default="auditor",
    )
    parser.add_argument("--credential-access", choices=("none", "read-only-provider"), default="none")
    parser.add_argument("--authority-path", action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        document = generate_lock(
            args.authority_root,
            source_id=args.source_id,
            role=args.role,
            repository=args.repository,
            revision=args.revision,
            credential_access=args.credential_access,
            authority_paths=args.authority_path,
        )
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        parser.error(str(exc))
    rendered = yaml.safe_dump(document, sort_keys=False)
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        if args.output.is_symlink():
            parser.error("--output must not be a symlink")
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate final adoption from an externally pinned verifier/claim-catalog authority."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import validate_adoption as adoption  # noqa: E402
import validate_trusted_executable_sources as trusted_sources  # noqa: E402
from confined_io import confined_regular_file  # noqa: E402
from evidence import GitHubEvidenceVerifier  # noqa: E402

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
GITHUB_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024


def _parse_mapping(path: Path, relative: str, *, json_only: bool = False) -> Mapping[str, Any]:
    if path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ValueError(f"input exceeds {MAX_DOCUMENT_BYTES} bytes: {relative}")
    text = path.read_text(encoding="utf-8")
    value = json.loads(text) if json_only else yaml.safe_load(text)
    if not isinstance(value, Mapping):
        raise ValueError(f"input must contain a mapping: {relative}")
    return value


def _load_mapping(root: Path, relative: str, *, json_only: bool = False) -> Mapping[str, Any]:
    return _parse_mapping(confined_regular_file(root, relative), relative, json_only=json_only)


def _load_authority_mapping(root: Path, relative: str, *, json_only: bool = False) -> Mapping[str, Any]:
    """Load policy only from tracked, clean bytes in the verified authority checkout."""
    return _parse_mapping(trusted_sources._authority_file(root, relative), relative, json_only=json_only)


def _external_authority(repository: str, revision: str, workflow_path: str) -> dict[str, str]:
    if GITHUB_REPOSITORY.fullmatch(repository) is None:
        raise ValueError("authority repository must use GitHub owner/name syntax")
    if FULL_SHA.fullmatch(revision) is None:
        raise ValueError("authority revision must be a full lowercase 40-character commit SHA")
    if not workflow_path.startswith(".github/workflows/") or ".." in Path(workflow_path).parts:
        raise ValueError("authority workflow path must stay under .github/workflows")
    return {
        "verifier_repository": repository,
        "verifier_revision": revision,
        "claim_catalog_repository": repository,
        "claim_catalog_revision": revision,
        "workflow_path": workflow_path,
    }


def validate_external_adoption(
    assessment: Mapping[str, Any],
    *,
    candidate_root: Path,
    authority_root: Path,
    authority_repository: str,
    authority_revision: str,
    authority_workflow_path: str,
    token: str,
    as_of: date,
) -> list[adoption.Finding]:
    """Run the normal adoption validator while binding approval to external authority coordinates."""
    expected = _external_authority(authority_repository, authority_revision, authority_workflow_path)
    observed = assessment.get("acceptance_authority")
    if not isinstance(observed, Mapping) or dict(observed) != expected:
        return [
            adoption.Finding(
                "acceptance_authority",
                "must exactly match the externally supplied verifier repository, revision, claim catalog, and workflow path",
            )
        ]

    # The authority checkout must be independently identified before any policy bytes
    # from it can influence the adoption decision. Each policy file is then required
    # to be tracked and clean at that locked revision.
    trusted_sources._verify_authority_identity(authority_root, authority_repository, authority_revision)
    catalog = _load_authority_mapping(authority_root, "contracts/rule-catalog.yaml")
    atomic_catalog = _load_authority_mapping(authority_root, "contracts/atomic-claim-catalog.yaml")
    schema = _load_authority_mapping(authority_root, "contracts/adoption-assessment.schema.json", json_only=True)

    skill = assessment.get("skill")
    if isinstance(skill, Mapping):
        skill_name = skill.get("name")
        if isinstance(skill_name, str) and skill_name:
            trusted_sources._authority_file(authority_root, f"skills/{skill_name}/manifest.yaml")

    skills_root = authority_root / "skills"
    verifier = GitHubEvidenceVerifier(token)
    verifier.acceptance_authority = expected
    return adoption.validate_document(
        assessment,
        catalog,
        skills_root,
        atomic_catalog=atomic_catalog,
        require_approval=True,
        as_of=as_of,
        schema=schema,
        repository_root=candidate_root,
        evidence_verifier=verifier,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assessment", help="Repository-relative assessment path inside the candidate checkout")
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--authority-root", type=Path, required=True)
    parser.add_argument("--authority-repository", required=True)
    parser.add_argument("--authority-revision", required=True)
    parser.add_argument("--authority-workflow-path", required=True)
    parser.add_argument("--github-token-env", default="GITHUB_TOKEN")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args(argv)
    token = os.environ.get(args.github_token_env, "")
    if not token:
        parser.error(f"provider token environment variable {args.github_token_env} is not set")
    try:
        candidate_root = args.candidate_root.resolve(strict=True)
        authority_root = args.authority_root.resolve(strict=True)
        assessment = _load_mapping(candidate_root, args.assessment)
        findings = validate_external_adoption(
            assessment,
            candidate_root=candidate_root,
            authority_root=authority_root,
            authority_repository=args.authority_repository,
            authority_revision=args.authority_revision,
            authority_workflow_path=args.authority_workflow_path,
            token=token,
            as_of=args.as_of,
        )
    except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
        print(f"ERROR: external adoption validation could not start: {exc}", file=sys.stderr)
        return 1
    for finding in findings:
        print(finding, file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

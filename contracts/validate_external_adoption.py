#!/usr/bin/env python3
"""Validate final adoption from an externally pinned verifier/claim-catalog authority."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, build_opener

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import validate_adoption as adoption  # noqa: E402
import validate_trusted_executable_sources as trusted_sources  # noqa: E402
from confined_io import ConfinedReadError, confined_regular_file, read_utf8_bounded  # noqa: E402
from evidence import GitHubEvidenceVerifier  # noqa: E402

from contracts import rule_applicability  # noqa: E402

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
GITHUB_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_IMPLEMENTATION_BYTES = 8 * 1024 * 1024
MAX_PROVIDER_RESPONSE_BYTES = 2 * 1024 * 1024


class _RejectRedirects(HTTPRedirectHandler):
    """Reject metadata redirects so repository identity cannot drift during final acceptance."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _ExternalGitHubEvidenceVerifier(GitHubEvidenceVerifier):
    """Final-acceptance verifier that refuses redirects for GitHub provider metadata."""

    def _get_json(self, path: str) -> object:
        cached = self._cache.get(path)
        if cached is not None:
            return cached
        opener = build_opener(_RejectRedirects())
        try:
            with opener.open(self._api_request(path), timeout=self._timeout_seconds) as response:  # noqa: S310
                raw = response.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            if 300 <= exc.code < 400:
                exc.close()
                raise ValueError(f"GitHub provider metadata redirect is not accepted for {path}") from exc
            raise
        if len(raw) > MAX_PROVIDER_RESPONSE_BYTES:
            raise ValueError(f"GitHub provider metadata response exceeds the size limit for {path}")
        payload = json.loads(raw)
        if not isinstance(payload, (Mapping, list)):
            raise ValueError(f"GitHub API returned an unsupported payload for {path}")
        self._cache[path] = payload
        return payload


def _mapping_from_text(text: str, relative: str, *, json_only: bool = False) -> Mapping[str, Any]:
    value = json.loads(text) if json_only else yaml.safe_load(text)
    if not isinstance(value, Mapping):
        raise ValueError(f"input must contain a mapping: {relative}")
    return value


def _parse_mapping(
    path: Path,
    repository_root: Path,
    relative: str,
    *,
    json_only: bool = False,
) -> Mapping[str, Any]:
    try:
        text, _size = read_utf8_bounded(path, repository_root, MAX_DOCUMENT_BYTES)
    except ConfinedReadError as exc:
        if exc.code == "input.too-large":
            raise ValueError(f"input exceeds {MAX_DOCUMENT_BYTES} bytes: {relative}") from exc
        raise ValueError(f"input cannot be read safely: {relative}: {exc}") from exc
    return _mapping_from_text(text, relative, json_only=json_only)


def _load_mapping(root: Path, relative: str, *, json_only: bool = False) -> Mapping[str, Any]:
    return _parse_mapping(
        confined_regular_file(root, relative),
        root,
        relative,
        json_only=json_only,
    )


def _load_candidate_mapping(
    root: Path,
    revision: str,
    relative: str,
    *,
    json_only: bool = False,
) -> Mapping[str, Any]:
    """Load candidate policy from the immutable Git object bound by the external revision."""
    try:
        text = trusted_sources._authority_text(
            root,
            revision,
            relative,
            max_bytes=MAX_DOCUMENT_BYTES,
        )
    except ValueError as exc:
        raise ValueError(f"candidate input is not readable from the immutable Git object {relative}: {exc}") from exc
    return _mapping_from_text(text, relative, json_only=json_only)


def _load_authority_mapping(
    root: Path,
    revision: str,
    relative: str,
    *,
    json_only: bool = False,
) -> Mapping[str, Any]:
    """Load authority policy directly from the immutable Git object, not mutable worktree bytes."""
    text = trusted_sources._authority_text(
        root,
        revision,
        relative,
        max_bytes=MAX_DOCUMENT_BYTES,
    )
    return _mapping_from_text(text, relative, json_only=json_only)


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


def _external_candidate(repository: str, revision: str) -> tuple[str, str]:
    if GITHUB_REPOSITORY.fullmatch(repository) is None:
        raise ValueError("candidate repository must use GitHub owner/name syntax")
    if FULL_SHA.fullmatch(revision) is None:
        raise ValueError("candidate revision must be a full lowercase 40-character commit SHA")
    return repository, revision


def _candidate_assessment_binding(
    assessment: Mapping[str, Any],
    repository: str,
    revision: str,
) -> list[adoption.Finding]:
    observed = assessment.get("repository")
    if not isinstance(observed, Mapping):
        return [adoption.Finding("repository", "must match the externally supplied candidate repository and revision")]
    findings: list[adoption.Finding] = []
    if observed.get("name") != repository:
        findings.append(adoption.Finding("repository.name", "must equal the externally supplied candidate repository"))
    if observed.get("revision") != revision:
        findings.append(
            adoption.Finding("repository.revision", "must equal the externally supplied candidate revision")
        )
    return findings


def _preflight_candidate_implementation_files(
    assessment: Mapping[str, Any],
    candidate_root: Path,
    candidate_revision: str,
    implementation_payloads: dict[str, str] | None = None,
) -> list[adoption.Finding]:
    """Capture implementation bytes from the immutable candidate Git object."""
    findings: list[adoption.Finding] = []
    applicability = assessment.get("applicability")
    if not isinstance(applicability, list):
        return findings
    for entry_index, raw_entry in enumerate(applicability):
        if not isinstance(raw_entry, Mapping) or raw_entry.get("status") != "applicable":
            continue
        implementations = raw_entry.get("implementation")
        if not isinstance(implementations, list):
            continue
        for implementation_index, raw_implementation in enumerate(implementations):
            if not isinstance(raw_implementation, Mapping):
                continue
            raw_path = raw_implementation.get("path")
            if not isinstance(raw_path, str) or not raw_path:
                continue
            location = f"applicability[{entry_index}].implementation[{implementation_index}].path"
            try:
                content = trusted_sources._authority_text(
                    candidate_root,
                    candidate_revision,
                    raw_path,
                    max_bytes=MAX_IMPLEMENTATION_BYTES,
                )
            except ValueError as exc:
                message = str(exc)
                if "exceeds" in message and str(MAX_IMPLEMENTATION_BYTES) in message:
                    findings.append(
                        adoption.Finding(
                            location,
                            f"implementation file exceeds {MAX_IMPLEMENTATION_BYTES} bytes",
                        )
                    )
                else:
                    findings.append(
                        adoption.Finding(
                            location,
                            f"implementation file cannot be read from immutable candidate Git object: {exc}",
                        )
                    )
                continue
            if implementation_payloads is not None:
                implementation_payloads[raw_path] = content
    return findings


def validate_external_adoption(
    assessment: Mapping[str, Any],
    *,
    candidate_root: Path,
    candidate_repository: str,
    candidate_revision: str,
    authority_root: Path,
    authority_repository: str,
    authority_revision: str,
    authority_workflow_path: str,
    token: str,
    as_of: date,
) -> list[adoption.Finding]:
    """Run adoption validation while binding both candidate and authority to external immutable coordinates."""
    expected_candidate_repository, expected_candidate_revision = _external_candidate(
        candidate_repository,
        candidate_revision,
    )
    trusted_sources._verify_candidate_identity(
        candidate_root,
        expected_candidate_repository,
        expected_candidate_revision,
    )
    candidate_findings = _candidate_assessment_binding(
        assessment,
        expected_candidate_repository,
        expected_candidate_revision,
    )
    if candidate_findings:
        return candidate_findings

    expected = _external_authority(authority_repository, authority_revision, authority_workflow_path)
    observed = assessment.get("acceptance_authority")
    if not isinstance(observed, Mapping) or dict(observed) != expected:
        return [
            adoption.Finding(
                "acceptance_authority",
                "must exactly match the externally supplied verifier repository, revision, claim catalog, and workflow path",
            )
        ]

    trusted_sources._verify_authority_identity(authority_root, authority_repository, authority_revision)
    catalog = _load_authority_mapping(authority_root, authority_revision, "contracts/rule-catalog.yaml")
    atomic_catalog = _load_authority_mapping(
        authority_root,
        authority_revision,
        "contracts/atomic-claim-catalog.yaml",
    )
    schema = _load_authority_mapping(
        authority_root,
        authority_revision,
        "contracts/adoption-assessment.schema.json",
        json_only=True,
    )

    skill = assessment.get("skill")
    skill_name = skill.get("name") if isinstance(skill, Mapping) else None
    manifest_text: str | None = None
    if isinstance(skill_name, str) and skill_name:
        manifest_text = trusted_sources._authority_text(
            authority_root,
            authority_revision,
            f"skills/{skill_name}/manifest.yaml",
            max_bytes=MAX_DOCUMENT_BYTES,
        )

    implementation_payloads: dict[str, str] = {}
    implementation_findings = _preflight_candidate_implementation_files(
        assessment,
        candidate_root,
        expected_candidate_revision,
        implementation_payloads,
    )
    if implementation_findings:
        return implementation_findings

    test_payloads: dict[str, str] = {}

    def immutable_test_source(relative: str) -> str:
        cached = test_payloads.get(relative)
        if cached is not None:
            return cached
        content = trusted_sources._authority_text(
            candidate_root,
            expected_candidate_revision,
            relative,
            max_bytes=MAX_IMPLEMENTATION_BYTES,
        )
        test_payloads[relative] = content
        return content

    verifier = _ExternalGitHubEvidenceVerifier(token)
    verifier.acceptance_authority = expected
    with tempfile.TemporaryDirectory(prefix="ai-skills-authority-") as temporary:
        skills_root = Path(temporary) / "skills"
        if isinstance(skill_name, str) and manifest_text is not None:
            manifest_path = skills_root / skill_name / "manifest.yaml"
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(manifest_text, encoding="utf-8", newline="\n")
        with rule_applicability.test_case_source_loader(immutable_test_source):
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
                implementation_payloads=implementation_payloads,
            )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assessment", help="Repository-relative assessment path inside the candidate checkout")
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--candidate-repository", required=True)
    parser.add_argument("--candidate-revision", required=True)
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
        candidate_repository, candidate_revision = _external_candidate(
            args.candidate_repository,
            args.candidate_revision,
        )
        trusted_sources._verify_candidate_identity(
            candidate_root,
            candidate_repository,
            candidate_revision,
        )
        assessment = _load_candidate_mapping(candidate_root, candidate_revision, args.assessment)
        findings = validate_external_adoption(
            assessment,
            candidate_root=candidate_root,
            candidate_repository=candidate_repository,
            candidate_revision=candidate_revision,
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

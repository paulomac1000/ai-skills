"""Regressions for immutable authority-schema binding in external trust-lock validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from contracts import validate_external_trust_lock as external_lock


def test_external_lock_validates_against_schema_from_pinned_authority_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = tmp_path / "candidate"
    authority = tmp_path / "authority"
    candidate.mkdir()
    authority.mkdir()
    candidate_revision = "b" * 40
    authority_revision = "a" * 40
    lock_relative = "contracts/trusted-executable-sources.lock.yaml"
    lock_document = {
        "schema_version": 1,
        "sources": [
            {
                "id": "ai-skills",
                "role": "policy-authority",
                "repository": "owner/authority",
                "revision": authority_revision,
                "credential_access": "none",
                "files": [],
            }
        ],
    }
    immutable_schema = {
        "type": "object",
        "properties": {"schema_version": {"const": 2}},
        "required": ["schema_version"],
    }
    reads: list[tuple[Path, str, str]] = []

    monkeypatch.setattr(external_lock.trusted_sources, "_verify_candidate_identity", lambda *_args: None)
    monkeypatch.setattr(external_lock.trusted_sources, "_verify_authority_identity", lambda *_args: None)

    def immutable_text(root: Path, revision: str, relative: str, *, max_bytes: int) -> str:
        reads.append((root, revision, relative))
        assert max_bytes == external_lock.trusted_sources.MAX_LOCK_BYTES
        if root == candidate:
            assert revision == candidate_revision
            assert relative == lock_relative
            return yaml.safe_dump(lock_document, sort_keys=False)
        assert root == authority
        assert revision == authority_revision
        assert relative == external_lock.TRUST_LOCK_SCHEMA_PATH
        return json.dumps(immutable_schema)

    monkeypatch.setattr(external_lock.trusted_sources, "_authority_text", immutable_text)

    def forbidden_fallback(*_args, **_kwargs):
        raise AssertionError(
            "mutable worktree schema must not be able to authorize an invalid immutable-schema document"
        )

    monkeypatch.setattr(external_lock.trusted_lock_snapshot, "validate_document", forbidden_fallback)

    findings = external_lock.validate_external_lock(
        lock_relative,
        candidate_root=candidate,
        candidate_repository="owner/candidate",
        candidate_revision=candidate_revision,
        authority_root=authority,
        source_id="ai-skills",
        expected_repository="owner/authority",
        expected_revision=authority_revision,
    )

    assert findings
    assert any("schema_version" in finding and "2" in finding for finding in findings)
    assert reads == [
        (candidate, candidate_revision, lock_relative),
        (authority, authority_revision, external_lock.TRUST_LOCK_SCHEMA_PATH),
    ]

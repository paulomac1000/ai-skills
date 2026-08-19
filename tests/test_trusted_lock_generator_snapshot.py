"""Regression coverage for immutable authority bytes used by trust-lock generation."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "skills/ci-cd-architect/tools/generate_trusted_executable_sources.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("trusted_lock_generator_snapshot", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_generator_hashes_immutable_git_blob_instead_of_authority_worktree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = _load_generator()
    authority = tmp_path / "authority"
    authority.mkdir()
    revision = "a" * 40
    payload = b"immutable authority bytes\n"

    monkeypatch.setattr(generator.trusted_sources, "_verify_authority_identity", lambda *_args: None)

    def git_blob(root: Path, locked_revision: str, raw_path: str) -> bytes:
        assert root == authority.resolve()
        assert locked_revision == revision
        assert raw_path == "contracts/verifier.py"
        return payload

    def forbidden_worktree_read(*_args):
        raise AssertionError("lock generation must not derive authority bytes from the mutable worktree")

    monkeypatch.setattr(generator.trusted_sources, "_git_blob", git_blob)
    monkeypatch.setattr(generator.trusted_sources, "_authority_file", forbidden_worktree_read)
    monkeypatch.setattr(generator.trusted_sources, "_digest", forbidden_worktree_read)

    document = generator.generate_lock(
        authority,
        source_id="validator",
        role="vendored-validator",
        repository="owner/trusted",
        revision=revision,
        credential_access="none",
        authority_paths=["contracts/verifier.py"],
    )

    source = document["sources"][0]
    assert source["files"] == [
        {
            "authority_path": "contracts/verifier.py",
            "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
        }
    ]

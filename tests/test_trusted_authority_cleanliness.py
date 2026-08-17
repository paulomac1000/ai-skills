"""Regression coverage for trusted authority checkout cleanliness."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest
import yaml

from contracts.validate_trusted_executable_sources import _authority_file, _git_environment, validate_lock


def _git(path: Path, *args: str, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed git executable and test-owned argv.
        [
            "git",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-C",
            str(path),
            *args,
        ],
        env=_git_environment(),
        check=True,
        capture_output=capture_output,
        text=True,
        timeout=30,
    )


def _authority_checkout(path: Path) -> str:
    path.mkdir()
    (path / "trusted.py").write_text("original\n", encoding="utf-8")
    _git(path, "init", "-q")
    _git(path, "config", "user.name", "Test")
    _git(path, "config", "user.email", "test@example.invalid")
    _git(path, "remote", "add", "origin", "https://github.com/owner/trusted.git")
    _git(path, "add", "trusted.py")
    _git(path, "commit", "-q", "-m", "fixture")
    return _git(path, "rev-parse", "HEAD", capture_output=True).stdout.strip()


def _write_lock(repository: Path, revision: str, authority_path: str, content: bytes) -> Path:
    lock = {
        "schema_version": 1,
        "sources": [
            {
                "id": "validator",
                "role": "vendored-validator",
                "repository": "owner/trusted",
                "revision": revision,
                "credential_access": "none",
                "files": [
                    {
                        "authority_path": authority_path,
                        "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
                    }
                ],
            }
        ],
    }
    path = repository / "trusted-executable-sources.lock.yaml"
    path.write_text(yaml.safe_dump(lock), encoding="utf-8")
    return path


def test_authority_digest_rejects_dirty_tracked_bytes_even_when_the_lock_matches_them(tmp_path: Path) -> None:
    repository = tmp_path / "consumer"
    repository.mkdir()
    authority = tmp_path / "authority"
    revision = _authority_checkout(authority)
    dirty = b"attacker-controlled working tree\n"
    (authority / "trusted.py").write_bytes(dirty)
    lock = _write_lock(repository, revision, "trusted.py", dirty)

    findings = validate_lock(
        lock,
        repository_root=repository,
        authority_roots={"validator": authority},
        require_authority=True,
    )

    assert any("authority checkout must be pristine at the locked revision" in finding for finding in findings)


def test_authority_digest_rejects_untracked_file_even_when_the_lock_matches_it(tmp_path: Path) -> None:
    repository = tmp_path / "consumer"
    repository.mkdir()
    authority = tmp_path / "authority"
    revision = _authority_checkout(authority)
    untracked = b"untracked bytes\n"
    (authority / "untracked.py").write_bytes(untracked)
    lock = _write_lock(repository, revision, "untracked.py", untracked)

    findings = validate_lock(
        lock,
        repository_root=repository,
        authority_roots={"validator": authority},
        require_authority=True,
    )

    assert any("authority checkout must be pristine at the locked revision" in finding for finding in findings)
    with pytest.raises(ValueError, match="authority_path must be tracked at the locked revision"):
        _authority_file(authority, "untracked.py")


def test_authority_identity_rejects_dirty_unlisted_tracked_bytes(tmp_path: Path) -> None:
    repository = tmp_path / "consumer"
    repository.mkdir()
    authority = tmp_path / "authority"
    _authority_checkout(authority)
    helper = authority / "helper.py"
    helper.write_text("original helper\n", encoding="utf-8")
    _git(authority, "add", "helper.py")
    _git(authority, "commit", "-q", "-m", "add helper")
    revision = _git(authority, "rev-parse", "HEAD", capture_output=True).stdout.strip()
    helper.write_text("tampered helper\n", encoding="utf-8")
    lock = _write_lock(repository, revision, "trusted.py", b"original\n")

    findings = validate_lock(
        lock,
        repository_root=repository,
        authority_roots={"validator": authority},
        require_authority=True,
    )

    assert any("authority checkout must be pristine at the locked revision" in finding for finding in findings)


def test_authority_identity_rejects_ignored_untracked_bytes(tmp_path: Path) -> None:
    repository = tmp_path / "consumer"
    repository.mkdir()
    authority = tmp_path / "authority"
    _authority_checkout(authority)
    (authority / ".gitignore").write_text("ignored_helper.py\n", encoding="utf-8")
    _git(authority, "add", ".gitignore")
    _git(authority, "commit", "-q", "-m", "ignore helper")
    revision = _git(authority, "rev-parse", "HEAD", capture_output=True).stdout.strip()
    (authority / "ignored_helper.py").write_text("ignored but executable\n", encoding="utf-8")
    lock = _write_lock(repository, revision, "trusted.py", b"original\n")

    findings = validate_lock(
        lock,
        repository_root=repository,
        authority_roots={"validator": authority},
        require_authority=True,
    )

    assert any("authority checkout must be pristine at the locked revision" in finding for finding in findings)

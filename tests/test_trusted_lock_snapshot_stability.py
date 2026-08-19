"""Adversarial regressions for trusted-lock byte-snapshot semantics."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from contracts import validate_trusted_executable_sources as trusted_sources


def _document(local_path: str, payload: bytes) -> dict[str, object]:
    return {
        "schema_version": 1,
        "sources": [
            {
                "id": "validator",
                "role": "vendored-validator",
                "repository": "owner/trusted",
                "revision": "a" * 40,
                "credential_access": "none",
                "files": [
                    {
                        "authority_path": "validator.py",
                        "local_path": local_path,
                        "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
                    }
                ],
            }
        ],
    }


def test_vendored_digest_is_bound_to_the_stable_reader_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "consumer"
    repository.mkdir()
    original = b"trusted bytes\n"
    replacement = b"changed after snapshot\n"
    vendored = repository / "validator.py"
    vendored.write_bytes(original)

    real_read = trusted_sources.read_bytes_bounded
    captured = False

    def read_then_replace(path: Path, root: Path, max_bytes: int) -> tuple[bytes, int]:
        nonlocal captured
        payload, size = real_read(path, root, max_bytes)
        if path == vendored.resolve():
            captured = True
            vendored.write_bytes(replacement)
        return payload, size

    def forbidden_path_digest(_path: Path) -> str:
        raise AssertionError("trusted validation must not reopen candidate bytes by path")

    monkeypatch.setattr(trusted_sources, "read_bytes_bounded", read_then_replace)
    monkeypatch.setattr(trusted_sources, "_digest", forbidden_path_digest)

    assert trusted_sources.validate_document(_document("validator.py", original), repository_root=repository) == []
    assert captured is True
    assert vendored.read_bytes() == replacement


def test_validate_lock_confines_the_lock_snapshot_to_repository_root(tmp_path: Path) -> None:
    repository = tmp_path / "consumer"
    repository.mkdir()
    outside = tmp_path / "trusted-executable-sources.lock.yaml"
    outside.write_text("schema_version: 1\nsources: []\n", encoding="utf-8")

    findings = trusted_sources.validate_lock(outside, repository_root=repository)

    assert findings
    assert any("Could not open input file safely" in finding for finding in findings)

"""Adversarial regressions for trusted-lock byte-snapshot semantics."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from contracts import confined_io
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


def test_stable_binary_reader_returns_exact_bytes_and_count(tmp_path: Path) -> None:
    repository = tmp_path / "consumer"
    repository.mkdir()
    candidate = repository / "validator.bin"
    candidate.write_bytes(b"\x00trusted\xff")

    payload, byte_count = confined_io.read_bytes_bounded(candidate, repository, 64)

    assert payload == b"\x00trusted\xff"
    assert byte_count == len(payload)


def test_stable_binary_reader_rejects_file_larger_than_bound(tmp_path: Path) -> None:
    repository = tmp_path / "consumer"
    repository.mkdir()
    candidate = repository / "validator.bin"
    candidate.write_bytes(b"oversized")

    with pytest.raises(confined_io.ConfinedReadError) as exc_info:
        confined_io.read_bytes_bounded(candidate, repository, 4)

    assert exc_info.value.code == "input.too-large"
    assert exc_info.value.byte_count == len(b"oversized")


def test_fallback_reader_rejects_path_identity_change_after_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "consumer"
    repository.mkdir()
    candidate = repository / "validator.bin"
    candidate.write_bytes(b"trusted")

    real_open_stable = confined_io.open_stable
    snapshot_checks = 0

    def force_fallback(path: Path, flags: int):
        return real_open_stable(path, flags, component_nofollow=False)

    def current_only_during_open(_snapshot) -> bool:
        nonlocal snapshot_checks
        snapshot_checks += 1
        return snapshot_checks == 1

    monkeypatch.setattr(confined_io, "open_stable", force_fallback)
    monkeypatch.setattr(confined_io, "snapshot_is_current", current_only_during_open)

    with pytest.raises(confined_io.ConfinedReadError) as exc_info:
        confined_io.read_bytes_bounded(candidate, repository, 64)

    assert exc_info.value.code == "input.read-error"
    assert "identity changed while reading" in str(exc_info.value)
    assert snapshot_checks == 2


@pytest.mark.parametrize(
    ("text", "suffix", "message"),
    [
        ("{", ".json", "invalid trusted source lock syntax"),
        ("- not-an-object\n", ".yaml", "trusted source lock root must be an object"),
    ],
)
def test_trusted_lock_parser_rejects_malformed_or_non_object_snapshots(
    text: str,
    suffix: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        trusted_sources.parse_document(text, suffix=suffix)


def test_trusted_lock_parser_accepts_json_snapshot() -> None:
    document = trusted_sources.parse_document('{"schema_version": 1, "sources": []}', suffix=".json")

    assert document == {"schema_version": 1, "sources": []}

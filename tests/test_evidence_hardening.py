"""Regression tests for the latest provider-evidence security audit."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from urllib.error import HTTPError

import pytest
from test_evidence_verifier import REPORT_PATH, SHA, StubVerifier, successful_fixture

import contracts.evidence as evidence_module
from contracts.evidence import GitHubEvidenceVerifier
from contracts.validate_adoption import _path_digest

_MISSING = object()


class _ClosableResponse:
    def __init__(self, payload: bytes = b"") -> None:
        self.payload = payload
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False

    def read(self, limit: int | None = None) -> bytes:
        return self.payload if limit is None else self.payload[:limit]

    def close(self) -> None:
        self.closed = True


class _StaticOpener:
    def __init__(self, response: _ClosableResponse) -> None:
        self.response = response

    def open(self, request, timeout):
        return self.response


class _RedirectOpener:
    def __init__(self, location: str) -> None:
        self.response = _ClosableResponse()
        self.error = HTTPError(
            "https://api.github.com/artifact",
            302,
            "redirect",
            {"Location": location},
            self.response,
        )

    def open(self, request, timeout):
        raise self.error


@pytest.mark.parametrize("value", [_MISSING, None, 0, -1, "1", True])
def test_invalid_check_run_id_returns_finding_without_traceback(value: object) -> None:
    reference, responses, archive = successful_fixture()
    reference = dict(reference)
    if value is _MISSING:
        reference.pop("check_run_id")
    else:
        reference["check_run_id"] = value
    errors = StubVerifier(responses, archive).verify_action(reference, SHA)
    assert errors == ["GitHub evidence verification failed: evidence check_run_id must be a positive integer"]


def test_artifact_redirect_and_unexpected_response_are_closed(monkeypatch) -> None:
    verifier = GitHubEvidenceVerifier("secret")
    unexpected = _ClosableResponse(b"unexpected")
    monkeypatch.setattr(
        evidence_module,
        "build_opener",
        lambda *_: _StaticOpener(unexpected),
    )
    with pytest.raises(ValueError, match="did not return"):
        verifier._download_artifact_bytes("owner/repository", 1)
    assert unexpected.closed

    redirect = _RedirectOpener("https://x.blob.core.windows.net/a")
    signed = _ClosableResponse(b"zip-bytes")
    monkeypatch.setattr(evidence_module, "build_opener", lambda *_: redirect)
    monkeypatch.setattr(evidence_module, "urlopen", lambda *args, **kwargs: signed)
    assert verifier._download_artifact_bytes("owner/repository", 2) == b"zip-bytes"
    assert redirect.response.closed
    assert signed.closed


def test_high_compression_report_is_rejected_by_uncompressed_limit(monkeypatch) -> None:
    payload = b"x" * 4096
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(REPORT_PATH, payload)
    archive_bytes = output.getvalue()
    assert len(archive_bytes) < len(payload)
    monkeypatch.setattr(evidence_module, "MAX_UNCOMPRESSED_BYTES", 1024)
    with pytest.raises(ValueError, match="uncompressed size limit"):
        GitHubEvidenceVerifier._read_report(archive_bytes, REPORT_PATH)


def test_actual_decompressed_bytes_are_bounded_even_when_metadata_lies(monkeypatch) -> None:
    class Member:
        filename = REPORT_PATH
        external_attr = 0
        file_size = 1

    class Source:
        def __init__(self) -> None:
            self.remaining = 32
            self.max_request = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size: int) -> bytes:
            self.max_request = max(self.max_request, size)
            if self.remaining == 0:
                return b""
            count = min(size, self.remaining)
            self.remaining -= count
            return b"x" * count

    source = Source()

    class Archive:
        def __init__(self, payload) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def infolist(self):
            return [Member()]

        def open(self, member, mode):
            return source

    monkeypatch.setattr(evidence_module.zipfile, "ZipFile", Archive)
    monkeypatch.setattr(evidence_module, "MAX_UNCOMPRESSED_BYTES", 10)
    monkeypatch.setattr(evidence_module, "READ_CHUNK_BYTES", 4)
    with pytest.raises(ValueError, match="actual uncompressed size limit"):
        GitHubEvidenceVerifier._read_report(b"archive", REPORT_PATH)
    assert source.max_request <= 4


def test_local_artifact_digest_streams_instead_of_using_read_bytes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    file = tmp_path / "artifact.bin"
    file.write_bytes(b"abc" * 1024)
    directory = tmp_path / "tree"
    directory.mkdir()
    (directory / "artifact.bin").write_bytes(b"def" * 1024)

    def reject_read_bytes(self: Path) -> bytes:
        raise AssertionError(f"whole-file read attempted for {self}")

    monkeypatch.setattr(Path, "read_bytes", reject_read_bytes)
    assert _path_digest(file) == f"sha256:{hashlib.sha256(b'abc' * 1024).hexdigest()}"
    assert _path_digest(directory).startswith("sha256:")


def test_extension_namespace_is_a_closed_versioned_registry() -> None:
    root = Path(__file__).resolve().parents[1]
    schema = json.loads((root / "contracts/adoption-assessment.schema.json").read_text(encoding="utf-8"))
    extension_schema = schema["properties"]["extensions"]
    assert set(extension_schema["properties"]) == {"mcp"}
    assert extension_schema["additionalProperties"] is False
    documentation = (root / "contracts/README.md").read_text(encoding="utf-8")
    assert "closed, versioned registry" in documentation
    assert "unknown keys are rejected" in documentation

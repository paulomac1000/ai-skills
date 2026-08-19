"""Regressions for bounded provider metadata reads in final external adoption."""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"


def _external_adoption() -> ModuleType:
    if str(CONTRACTS) not in sys.path:
        sys.path.insert(0, str(CONTRACTS))
    path = CONTRACTS / "validate_external_adoption.py"
    spec = importlib.util.spec_from_file_location("external_provider_response_bounds", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_final_provider_metadata_read_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    validator = _external_adoption()
    read_sizes: list[int] = []

    class Response(io.BytesIO):
        def read(self, size: int = -1) -> bytes:
            read_sizes.append(size)
            return super().read(size)

    class Opener:
        def open(self, _request, *, timeout: int):
            assert timeout > 0
            payload = b'{"padding":"' + (b"x" * validator.MAX_PROVIDER_RESPONSE_BYTES) + b'"}'
            return Response(payload)

    monkeypatch.setattr(validator, "build_opener", lambda *_handlers: Opener())
    verifier = validator._ExternalGitHubEvidenceVerifier("token")

    with pytest.raises(ValueError, match="provider metadata response exceeds the size limit"):
        verifier._get_json("/repos/owner/project/actions/runs/1")

    assert read_sizes == [validator.MAX_PROVIDER_RESPONSE_BYTES + 1]


def test_final_provider_metadata_accepts_and_caches_bounded_json(monkeypatch: pytest.MonkeyPatch) -> None:
    validator = _external_adoption()
    opens = 0

    class Opener:
        def open(self, _request, *, timeout: int):
            nonlocal opens
            assert timeout > 0
            opens += 1
            return io.BytesIO(b'{"status":"completed"}')

    monkeypatch.setattr(validator, "build_opener", lambda *_handlers: Opener())
    verifier = validator._ExternalGitHubEvidenceVerifier("token")
    path = "/repos/owner/project/actions/runs/1"

    assert verifier._get_json(path) == {"status": "completed"}
    assert verifier._get_json(path) == {"status": "completed"}
    assert opens == 1

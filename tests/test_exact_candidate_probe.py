"""Fail-closed regressions for the canonical exact-candidate MCP probe."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "skills/mcp-server-architect/tools/mcp_exact_candidate_probe.py"
ACCEPTANCE = ROOT / "skills/mcp-server-architect/tools/exact_candidate_acceptance.py"
CAPTURE = ROOT / "skills/mcp-server-architect/tools/capture_mcp_contract.py"
DIGEST = "sha256:" + "b" * 64
SHA = "a" * 40


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _probe() -> ModuleType:
    return _load("exact_probe_module", PROBE)


def test_evidence_without_client_provenance_fails_closed() -> None:
    module = _probe()
    evidence = module.ExactCandidateEvidence(
        source_sha=SHA,
        artifact_digest=DIGEST,
        artifact_source_sha=SHA,
        sdk_revision="mcp@2.0.0",
        initialize_ok=True,
        tools_list_ok=True,
        schema_snapshot_digest="sha256:" + "c" * 64,
        schema_compatible=True,
        representative_invocation_ok=True,
        runtime_source_sha=SHA,
        client_provenance=None,
    )
    try:
        module.validate_client_provenance(evidence.client_provenance, DIGEST)
    except module.ExactCandidateAcceptanceError as exc:
        assert "caller-asserted session facts are rejected" in str(exc)
    else:
        raise AssertionError("caller-asserted evidence was accepted without provenance")


def test_acceptance_validator_requires_client_provenance() -> None:
    module = _load("exact_probe_acceptance", ACCEPTANCE)
    evidence = module.ExactCandidateEvidence(
        source_sha=SHA,
        artifact_digest=DIGEST,
        artifact_source_sha=SHA,
        sdk_revision="mcp@2.0.0",
        initialize_ok=True,
        tools_list_ok=True,
        schema_snapshot_digest="sha256:" + "c" * 64,
        schema_compatible=True,
        representative_invocation_ok=True,
        runtime_source_sha=SHA,
        client_provenance=None,
    )
    try:
        module.validate_exact_candidate(evidence)
    except module.ExactCandidateAcceptanceError as exc:
        assert "client provenance" in str(exc)
    else:
        raise AssertionError("acceptance passed without client provenance")


def test_probe_rejects_unpinned_official_client_version(monkeypatch) -> None:
    module = _probe()

    class _FakeMetadata:
        @staticmethod
        def version(name: str) -> str:
            return "9.9.9"

    monkeypatch.setattr(module.importlib, "metadata", _FakeMetadata)
    try:
        module.verify_official_client()
    except module.ProbeClientError as exc:
        assert "pinned official client" in str(exc)
    else:
        raise AssertionError("an unpinned client version was accepted")


def test_probe_rejects_malformed_initialize_payload() -> None:
    module = _probe()
    bad_payloads = (
        {"serverInfo": {"name": "x"}},
        {"protocolVersion": "2025-06-18"},
        {},
    )
    for payload in bad_payloads:
        try:
            module.validate_client_provenance(
                {
                    "package": "mcp",
                    "version": "2.0.0",
                    "protocol_revision": "2025-06-18",
                    "transport": "stdio",
                    "initialize_payload": payload,
                    "session_receipt": "0" * 64,
                },
                DIGEST,
            )
        except module.ExactCandidateAcceptanceError as exc:
            assert "initialize payload" in str(exc)
        else:
            raise AssertionError(f"malformed initialize payload accepted: {payload}")


def test_probe_rejects_receipt_that_does_not_match_payload() -> None:
    module = _probe()
    payload = {
        "protocolVersion": "2025-06-18",
        "serverInfo": {"name": "candidate", "version": "1.0.0"},
    }
    try:
        module.validate_client_provenance(
            {
                "package": "mcp",
                "version": "2.0.0",
                "protocol_revision": "2025-06-18",
                "transport": "stdio",
                "initialize_payload": payload,
                "session_receipt": "f" * 64,
            },
            DIGEST,
        )
    except module.ExactCandidateAcceptanceError as exc:
        assert "receipt does not match" in str(exc)
    else:
        raise AssertionError("an inconsistent session receipt was accepted")


def test_consistent_probe_receipt_is_accepted() -> None:
    module = _probe()
    payload = {
        "protocolVersion": "2025-06-18",
        "serverInfo": {"name": "candidate", "version": "1.0.0"},
    }
    receipt = hashlib.sha256(
        json.dumps(
            {
                "artifact_digest": DIGEST,
                "client_version": "2.0.0",
                "initialize": payload,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    provenance = module.validate_client_provenance(
        {
            "package": "mcp",
            "version": "2.0.0",
            "protocol_revision": "2025-06-18",
            "transport": "stdio",
            "initialize_payload": payload,
            "session_receipt": receipt,
        },
        DIGEST,
    )
    assert provenance.version == "2.0.0"
    assert provenance.session_receipt == receipt


def test_capture_contract_rejects_arbitrary_client_commands() -> None:
    module = _load("exact_probe_capture", CAPTURE)

    class _Parser:
        def __init__(self) -> None:
            self.errors: list[str] = []

        def error(self, message: str) -> None:
            self.errors.append(message)

    parser = _Parser()
    module._require_canonical_probe_command(
        ["python", "make_fake_json.py"],
        parser,  # type: ignore[arg-type]
    )
    assert parser.errors and "canonical" in parser.errors[0]
    parser.errors.clear()
    module._require_canonical_probe_command(
        ["python", str(PROBE), "--source-sha", SHA],
        parser,  # type: ignore[arg-type]
    )
    assert parser.errors == []

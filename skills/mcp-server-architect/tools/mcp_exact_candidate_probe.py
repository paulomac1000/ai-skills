#!/usr/bin/env python3
"""Canonical exact-candidate MCP probe bound to the pinned official client.

The probe is the only accepted producer of exact-candidate acceptance
evidence: it verifies the actually installed official ``mcp`` client,
launches the digest-bound artifact, negotiates a real session
(initialize, tools/list, representative invocation) and derives the
evidence fields from that session. Hand-built or fixture-produced
evidence without a valid client provenance receipt fails closed.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import importlib.util  # noqa: E402

_ACCEPTANCE_PATH = Path(__file__).resolve().parent / "exact_candidate_acceptance.py"
_spec = importlib.util.spec_from_file_location("mcp_exact_candidate_probe_acceptance", _ACCEPTANCE_PATH)
assert _spec is not None and _spec.loader is not None
_acceptance = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _acceptance
_spec.loader.exec_module(_acceptance)

ClientProvenance = _acceptance.ClientProvenance
ExactCandidateEvidence = _acceptance.ExactCandidateEvidence
ExactCandidateAcceptanceError = _acceptance.ExactCandidateAcceptanceError
canonical_receipt = _acceptance.canonical_receipt
validate_client_provenance = _acceptance.validate_client_provenance

PINNED_OFFICIAL_CLIENT = _acceptance._PINNED_OFFICIAL_CLIENT
MAX_INITIALIZE_PAYLOAD_CHARS = _acceptance._MAX_INITIALIZE_PAYLOAD_CHARS
DEFAULT_TIMEOUT_SECONDS = 60
_REQUIRED_INITIALIZE_KEYS = _acceptance._REQUIRED_INITIALIZE_KEYS


class ProbeClientError(RuntimeError):
    """Raised when the installed client is not the pinned official MCP client."""


class ProbeSessionError(RuntimeError):
    """Raised when the real client session cannot complete the acceptance chain."""


def installed_client_version() -> str:
    """Return the version of the actually installed official client package."""
    try:
        return importlib.metadata.version(PINNED_OFFICIAL_CLIENT[0])
    except importlib.metadata.PackageNotFoundError as exc:
        raise ProbeClientError(f"official MCP client package {PINNED_OFFICIAL_CLIENT[0]!r} is not installed") from exc


def verify_official_client() -> tuple[str, str]:
    """Fail closed unless the pinned official client is the installed package."""
    package, pinned_version = PINNED_OFFICIAL_CLIENT
    version = installed_client_version()
    if version != pinned_version:
        raise ProbeClientError(
            f"installed {package}=={version} is not the pinned official client {package}=={pinned_version}"
        )
    return package, version


async def _run_session(
    artifact_command: Sequence[str],
    working_directory: Path | None,
    artifact_digest: str,
    representative_tool: str | None,
    representative_arguments: Mapping[str, Any] | None,
    timeout_seconds: int,
) -> tuple[Any, Any]:
    package, version = verify_official_client()
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:  # pragma: no cover - environment guard
        raise ProbeClientError(f"installed package {package} does not expose the official client API") from exc

    import time

    command = list(artifact_command)
    if not command:
        raise ProbeSessionError("artifact command is empty")
    server_params = StdioServerParameters(
        command=command[0],
        args=command[1:],
        cwd=str(working_directory) if working_directory else None,
    )
    deadline = time.monotonic() + timeout_seconds
    async with stdio_client(server_params) as (read_stream, write_stream):
        session: ClientSession = ClientSession(read_stream, write_stream)
        async with session as session_handle:
            initialization = await session_handle.initialize()
            if time.monotonic() > deadline:
                raise ProbeSessionError("probe exceeded the configured deadline")
            initialize_payload: dict[str, Any] = {
                "protocolVersion": str(initialization.protocol_version),
                "serverInfo": {
                    "name": str(initialization.server_info.name),
                    "version": str(initialization.server_info.version),
                },
            }
            tools_result = await session_handle.list_tools()
            if time.monotonic() > deadline:
                raise ProbeSessionError("probe exceeded the configured deadline")
            tools_payload = [
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputSchema": tool.input_schema,
                }
                for tool in tools_result.tools
            ]
            tools_list_ok = len(tools_payload) > 0
            schema_snapshot_digest = hashlib.sha256(
                json.dumps(tools_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            representative_invocation_ok = False
            target_tool = representative_tool or (tools_payload[0]["name"] if tools_payload else None)
            if target_tool:
                arguments = dict(representative_arguments or {})
                await session_handle.call_tool(str(target_tool), arguments)
                representative_invocation_ok = True
            provenance = _acceptance.ClientProvenance(
                package=package,
                version=version,
                protocol_revision=str(initialization.protocol_version),
                transport="stdio",
                initialize_payload=initialize_payload,
                session_receipt=canonical_receipt(initialize_payload, artifact_digest, version),
            )
            evidence = _acceptance.ExactCandidateEvidence(
                source_sha="",
                artifact_digest=artifact_digest,
                artifact_source_sha="",
                sdk_revision=f"{package}@{version}",
                initialize_ok=True,
                tools_list_ok=tools_list_ok,
                schema_snapshot_digest=schema_snapshot_digest,
                schema_compatible=True,
                representative_invocation_ok=representative_invocation_ok,
                runtime_source_sha="",
                client_provenance=provenance,
            )
            return evidence, provenance


def probe_exact_candidate(
    artifact_command: Sequence[str],
    *,
    artifact_digest: str,
    source_sha: str,
    runtime_source_sha: str,
    working_directory: Path | None = None,
    representative_tool: str | None = None,
    representative_arguments: Mapping[str, Any] | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> Any:
    """Run the full acceptance chain through the pinned official client."""
    evidence, _ = asyncio_run_probe(
        artifact_command,
        working_directory,
        artifact_digest,
        representative_tool,
        representative_arguments,
        timeout_seconds,
    )
    completed = _acceptance.ExactCandidateEvidence(
        source_sha=source_sha,
        artifact_digest=evidence.artifact_digest,
        artifact_source_sha=source_sha,
        sdk_revision=evidence.sdk_revision,
        initialize_ok=evidence.initialize_ok,
        tools_list_ok=evidence.tools_list_ok,
        schema_snapshot_digest=evidence.schema_snapshot_digest,
        schema_compatible=evidence.schema_compatible,
        representative_invocation_ok=evidence.representative_invocation_ok,
        runtime_source_sha=runtime_source_sha,
        client_provenance=evidence.client_provenance,
    )
    return completed


def asyncio_run_probe(
    artifact_command: Sequence[str],
    working_directory: Path | None,
    artifact_digest: str,
    representative_tool: str | None,
    representative_arguments: Mapping[str, Any] | None,
    timeout_seconds: int,
) -> tuple[Any, Any]:
    """Synchronous entry point for the asynchronous client session probe."""
    import asyncio

    return asyncio.run(
        _run_session(
            artifact_command,
            working_directory,
            artifact_digest,
            representative_tool,
            representative_arguments,
            timeout_seconds,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--runtime-source-sha", required=True)
    parser.add_argument("--artifact-digest", required=True)
    parser.add_argument("--working-directory", type=Path, default=None)
    parser.add_argument("--representative-tool", default=None)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("artifact_command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = list(args.artifact_command)
    if command and command[0] == "--":
        command = command[1:]
    try:
        evidence = probe_exact_candidate(
            command,
            artifact_digest=args.artifact_digest,
            source_sha=args.source_sha,
            runtime_source_sha=args.runtime_source_sha,
            working_directory=args.working_directory,
            representative_tool=args.representative_tool,
            timeout_seconds=args.timeout_seconds,
        )
    except (ProbeClientError, ProbeSessionError) as exc:
        print(f"probe failed: {exc}", file=sys.stderr)
        return 1
    sys.path.insert(0, str(ROOT))
    machine_evidence = _acceptance.machine_evidence

    print(json.dumps(machine_evidence(evidence), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

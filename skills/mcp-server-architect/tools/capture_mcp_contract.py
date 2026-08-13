#!/usr/bin/env python3
"""Capture a canonical MCP public-contract snapshot from an exact no-shell probe."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_contract_module = importlib.import_module("contracts.mcp_public_contract")
normalize_contract = _contract_module.normalize_contract
validate_contract = _contract_module.validate_contract

MAX_STDOUT_BYTES = 2 * 1024 * 1024
ALLOWED_ENVIRONMENT = {
    "COMSPEC",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "PATH",
    "PATHEXT",
    "PYTHONHASHSEED",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "TMPDIR",
    "WINDIR",
}


def _run_probe(argv: list[str], working_directory: Path, timeout_seconds: int) -> bytes:
    environment = {name: value for name, value in os.environ.items() if name in ALLOWED_ENVIRONMENT}
    completed = subprocess.run(  # noqa: S603 - exact argv is supplied by the operator; shell is never used.
        argv,
        cwd=working_directory,
        env=environment,
        check=False,
        capture_output=True,
        timeout=timeout_seconds,
    )
    if completed.stderr:
        sys.stderr.buffer.write(completed.stderr)
    if completed.returncode != 0:
        raise RuntimeError(f"official-client contract probe failed with exit code {completed.returncode}")
    if len(completed.stdout) > MAX_STDOUT_BYTES:
        raise RuntimeError("official-client contract probe exceeded the bounded stdout budget")
    return completed.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--working-directory", type=Path, default=Path("."))
    parser.add_argument("--expected-source-revision", required=True)
    parser.add_argument("--expected-artifact-digest", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command or any(not item for item in command):
        parser.error("an exact probe argv is required after --")
    if not (1 <= args.timeout_seconds <= 600):
        parser.error("--timeout-seconds must be between 1 and 600")
    if os.path.lexists(args.output):
        parser.error("output already exists; refusing to overwrite")

    working_directory = args.working_directory.resolve(strict=True)
    if not working_directory.is_dir():
        parser.error("working directory must be a directory")

    try:
        document = json.loads(_run_probe(command, working_directory, args.timeout_seconds))
    except (json.JSONDecodeError, RuntimeError, subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    findings = validate_contract(document)
    if findings:
        parser.error("; ".join(findings))
    assert isinstance(document, dict)
    if document["source_revision"] != args.expected_source_revision:
        parser.error("captured source revision does not match --expected-source-revision")
    if document["artifact"]["digest"] != args.expected_artifact_digest:
        parser.error("captured artifact digest does not match --expected-artifact-digest")

    canonical = normalize_contract(document)
    args.output.write_text(
        json.dumps(canonical, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

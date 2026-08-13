#!/usr/bin/env python3
"""Capture a canonical MCP public-contract snapshot from an exact no-shell probe."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_contract_module = importlib.import_module("contracts.mcp_public_contract")
normalize_contract = _contract_module.normalize_contract
validate_contract = _contract_module.validate_contract

MAX_PROBE_OUTPUT_BYTES = 2 * 1024 * 1024
PIPE_READ_BYTES = 64 * 1024
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


@dataclass(slots=True)
class _CapturedStream:
    data: bytearray = field(default_factory=bytearray)
    bytes_seen: int = 0
    overflow: bool = False
    error: str | None = None


def _drain_stream(source: BinaryIO, capture: _CapturedStream, abort_event: threading.Event) -> None:
    try:
        while chunk := source.read(PIPE_READ_BYTES):
            capture.bytes_seen += len(chunk)
            remaining = max(0, MAX_PROBE_OUTPUT_BYTES - len(capture.data))
            if remaining:
                capture.data.extend(chunk[:remaining])
            if capture.bytes_seen > MAX_PROBE_OUTPUT_BYTES:
                capture.overflow = True
                abort_event.set()
    except (OSError, ValueError) as exc:
        capture.error = f"{type(exc).__name__}: {exc}"
        abort_event.set()
    finally:
        source.close()


def _spawn_probe(
    argv: list[str], working_directory: Path, environment: dict[str, str]
) -> subprocess.Popen[bytes]:
    if os.name == "nt":
        return subprocess.Popen(  # noqa: S603 - exact argv is supplied by the operator; shell is never used.
            argv,
            cwd=working_directory,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    return subprocess.Popen(  # noqa: S603 - exact argv is supplied by the operator; shell is never used.
        argv,
        cwd=working_directory,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )


def _terminate_process_tree(process: subprocess.Popen[bytes], environment: dict[str, str]) -> None:
    """Best-effort terminate the probe and descendants without invoking a shell."""
    if os.name == "nt":
        try:
            subprocess.run(  # noqa: S603,S607 - fixed Windows system utility and numeric PID.
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                env=environment,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass


def _run_probe(argv: list[str], working_directory: Path, timeout_seconds: int) -> bytes:
    environment = {name: value for name, value in os.environ.items() if name in ALLOWED_ENVIRONMENT}
    process = _spawn_probe(argv, working_directory, environment)
    assert process.stdout is not None and process.stderr is not None
    abort_event = threading.Event()
    stdout_capture = _CapturedStream()
    stderr_capture = _CapturedStream()
    threads = [
        threading.Thread(target=_drain_stream, args=(process.stdout, stdout_capture, abort_event), daemon=True),
        threading.Thread(target=_drain_stream, args=(process.stderr, stderr_capture, abort_event), daemon=True),
    ]
    for thread in threads:
        thread.start()

    deadline = time.monotonic() + timeout_seconds
    failure: str | None = None
    while process.poll() is None:
        if abort_event.wait(timeout=0.02):
            if stdout_capture.overflow or stderr_capture.overflow:
                failure = f"official-client contract probe exceeded {MAX_PROBE_OUTPUT_BYTES} bytes per output stream"
            else:
                detail = stdout_capture.error or stderr_capture.error or "unknown stream error"
                failure = f"official-client contract probe output capture failed: {detail}"
            _terminate_process_tree(process, environment)
            break
        if time.monotonic() >= deadline:
            failure = f"official-client contract probe exceeded timeout of {timeout_seconds} seconds"
            _terminate_process_tree(process, environment)
            break
    try:
        returncode = process.wait(timeout=5)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_tree(process, environment)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired as second_exc:
            raise RuntimeError("official-client contract probe process tree did not terminate") from second_exc
        raise RuntimeError("official-client contract probe process did not terminate promptly") from exc

    for thread in threads:
        thread.join(timeout=5)
    if any(thread.is_alive() for thread in threads):
        _terminate_process_tree(process, environment)
        for thread in threads:
            thread.join(timeout=5)
    if any(thread.is_alive() for thread in threads):
        raise RuntimeError("official-client contract probe output drain did not terminate")
    if stderr_capture.data:
        sys.stderr.buffer.write(stderr_capture.data)
        sys.stderr.buffer.flush()
    if failure is None and (stdout_capture.overflow or stderr_capture.overflow):
        failure = f"official-client contract probe exceeded {MAX_PROBE_OUTPUT_BYTES} bytes per output stream"
    if failure is None and (stdout_capture.error or stderr_capture.error):
        detail = stdout_capture.error or stderr_capture.error
        failure = f"official-client contract probe output capture failed: {detail}"
    if failure is not None:
        raise RuntimeError(failure)
    if returncode != 0:
        raise RuntimeError(f"official-client contract probe failed with exit code {returncode}")
    return bytes(stdout_capture.data)


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
    except (json.JSONDecodeError, RuntimeError) as exc:
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
    try:
        with args.output.open("x", encoding="utf-8", newline="\n") as destination:
            destination.write(json.dumps(canonical, indent=2, sort_keys=True) + "\n")
    except FileExistsError:
        parser.error("output already exists; refusing to overwrite")
    except OSError as exc:
        parser.error(f"cannot write output: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

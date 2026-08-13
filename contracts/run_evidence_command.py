#!/usr/bin/env python3
"""Execute one exact argv and emit command, test, and artifact observations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

EXECUTION_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
READ_CHUNK_BYTES = 1024 * 1024
PIPE_READ_BYTES = 64 * 1024
MAX_CAPTURE_BYTES = 8 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 900
MAX_TIMEOUT_SECONDS = 3600


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(READ_CHUNK_BYTES):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


@dataclass(slots=True)
class _CapturedStream:
    data: bytearray = field(default_factory=bytearray)
    bytes_seen: int = 0
    overflow: bool = False
    error: str | None = None

    def observation(self) -> dict[str, Any]:
        payload = bytes(self.data)
        return {"digest": f"sha256:{hashlib.sha256(payload).hexdigest()}", "bytes": len(payload)}


def _drain_stream(
    source: BinaryIO,
    capture: _CapturedStream,
    *,
    limit: int,
    abort_event: threading.Event,
) -> None:
    try:
        while chunk := source.read(PIPE_READ_BYTES):
            capture.bytes_seen += len(chunk)
            remaining = max(0, limit - len(capture.data))
            if remaining:
                capture.data.extend(chunk[:remaining])
            if capture.bytes_seen > limit:
                capture.overflow = True
                abort_event.set()
    except (OSError, ValueError) as exc:
        capture.error = f"{type(exc).__name__}: {exc}"
        abort_event.set()
    finally:
        source.close()


def _spawn_process(argv: list[str], cwd: Path) -> subprocess.Popen[bytes]:
    if os.name == "nt":
        return subprocess.Popen(  # noqa: S603 - exact argv; shell is never used.
            argv,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    return subprocess.Popen(  # noqa: S603 - exact argv; shell is never used.
        argv,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if os.name == "nt":
        try:
            subprocess.run(  # noqa: S603,S607 - fixed system utility and numeric PID.
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
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


def _append_error(existing: str | None, message: str) -> str:
    return f"{existing}; {message}" if existing else message


def _execute_bounded(
    argv: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    max_output_bytes: int,
) -> tuple[int, _CapturedStream, _CapturedStream, str | None, int | None]:
    process = _spawn_process(argv, cwd)
    assert process.stdout is not None and process.stderr is not None
    abort_event = threading.Event()
    stdout_capture = _CapturedStream()
    stderr_capture = _CapturedStream()
    threads = [
        threading.Thread(
            target=_drain_stream,
            args=(process.stdout, stdout_capture),
            kwargs={"limit": max_output_bytes, "abort_event": abort_event},
            daemon=True,
        ),
        threading.Thread(
            target=_drain_stream,
            args=(process.stderr, stderr_capture),
            kwargs={"limit": max_output_bytes, "abort_event": abort_event},
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + timeout_seconds
    execution_error: str | None = None
    failure_status: int | None = None
    while process.poll() is None:
        if abort_event.wait(timeout=0.02):
            if stdout_capture.overflow or stderr_capture.overflow:
                execution_error = f"command output exceeded {max_output_bytes} bytes per stream"
                failure_status = 125
            else:
                detail = stdout_capture.error or stderr_capture.error or "unknown stream error"
                execution_error = f"command output capture failed: {detail}"
                failure_status = 125
            _terminate_process_tree(process)
            break
        if time.monotonic() >= deadline:
            execution_error = f"command exceeded timeout of {timeout_seconds} seconds"
            failure_status = 124
            _terminate_process_tree(process)
            break
    try:
        returncode = process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        returncode = process.poll() if process.poll() is not None else -1
        execution_error = _append_error(execution_error, "command process tree did not terminate promptly")
        failure_status = failure_status or 125

    for thread in threads:
        thread.join(timeout=5)
    if any(thread.is_alive() for thread in threads):
        _terminate_process_tree(process)
        for thread in threads:
            thread.join(timeout=5)
    if any(thread.is_alive() for thread in threads):
        execution_error = _append_error(execution_error, "command output drain did not terminate")
        failure_status = failure_status or 125
    if execution_error is None and (stdout_capture.overflow or stderr_capture.overflow):
        execution_error = f"command output exceeded {max_output_bytes} bytes per stream"
        failure_status = 125
    if stdout_capture.error or stderr_capture.error:
        detail = stdout_capture.error or stderr_capture.error or "unknown stream error"
        execution_error = _append_error(execution_error, f"command output capture failed: {detail}")
        failure_status = failure_status or 125
    return returncode, stdout_capture, stderr_capture, execution_error, failure_status


def _replay(capture: _CapturedStream, destination: BinaryIO) -> None:
    destination.write(capture.data)
    destination.flush()


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _junit_cases(path: Path) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(path.read_bytes())
    except ET.ParseError as exc:
        raise ValueError(f"{path}: result is not valid JUnit XML") from exc
    cases: list[dict[str, str]] = []
    seen: set[str] = set()
    for element in root.iter():
        if _tag(element) != "testcase":
            continue
        classname = str(element.attrib.get("classname") or "").strip()
        name = str(element.attrib.get("name") or "").strip()
        if not name:
            raise ValueError(f"{path}: testcase without a name")
        identity = f"{classname}::{name}" if classname else name
        if identity in seen:
            raise ValueError(f"{path}: duplicate testcase identity: {identity}")
        seen.add(identity)
        status = "passed"
        for child in element:
            child_tag = _tag(child)
            if child_tag in {"failure", "error", "skipped"}:
                status = child_tag
                break
        cases.append({"identity": identity, "status": status})
    if not cases:
        raise ValueError(f"{path}: JUnit document contains no test cases")
    if any(case["status"] in {"failure", "error"} for case in cases):
        raise ValueError(f"{path}: JUnit document contains failed or errored tests")
    return cases


def _lexical_absolute(path: Path, root: Path) -> Path:
    candidate = path if path.is_absolute() else root / path
    return Path(os.path.abspath(os.fspath(candidate)))


def _relative_without_symlinks(candidate: Path, root: Path, name: str) -> Path:
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{name} must stay inside the repository boundary") from exc
    current = root
    for part in relative.parts:
        current /= part
        if os.path.lexists(current) and current.is_symlink():
            raise ValueError(f"{name} must not contain symlink components")
        if not os.path.lexists(current):
            raise ValueError(f"{name} must exist")
    return relative


def _safe_relative(path: Path, root: Path, name: str) -> tuple[Path, str]:
    candidate = _lexical_absolute(path, root)
    relative = _relative_without_symlinks(candidate, root, name)
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"{name} must identify a regular file")
    return resolved, relative.as_posix()


def _safe_working_directory(path: Path, repository_root: Path) -> tuple[Path, str]:
    if any(part == ".." for part in path.parts):
        raise ValueError("working_directory must not contain parent traversal")
    candidate = _lexical_absolute(path, repository_root)
    relative = _relative_without_symlinks(candidate, repository_root, "working_directory")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("working_directory must be a real directory")
    return resolved, relative.as_posix() or "."


def _command_digest(argv: list[str], working_directory: str) -> str:
    encoded = json.dumps(
        {"argv": argv, "working_directory": working_directory},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--working-directory", type=Path, default=Path("."))
    parser.add_argument("--result-file", action="append", type=Path, default=[])
    parser.add_argument("--artifact-file", action="append", type=Path, default=[])
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-output-bytes", type=int, default=MAX_CAPTURE_BYTES)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("argv", nargs=argparse.REMAINDER)
    return parser


def main(raw_args: list[str] | None = None) -> int:
    args = build_parser().parse_args(raw_args)
    execution_id = str(args.execution_id).strip()
    if EXECUTION_ID.fullmatch(execution_id) is None:
        raise ValueError("execution_id must use lowercase letters, digits, and hyphens")
    argv = list(args.argv)
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv or any(not isinstance(value, str) or not value for value in argv):
        raise ValueError("an exact non-empty argv is required after --")
    repository_root = Path.cwd().resolve(strict=True)
    working_directory, working_directory_text = _safe_working_directory(args.working_directory, repository_root)
    if not 0 < args.timeout_seconds <= MAX_TIMEOUT_SECONDS:
        raise ValueError(f"timeout_seconds must be between 1 and {MAX_TIMEOUT_SECONDS}")
    if not 0 < args.max_output_bytes <= MAX_CAPTURE_BYTES:
        raise ValueError(f"max_output_bytes must be between 1 and {MAX_CAPTURE_BYTES}")

    returncode, stdout_capture, stderr_capture, execution_error, failure_status = _execute_bounded(
        argv,
        cwd=working_directory,
        timeout_seconds=args.timeout_seconds,
        max_output_bytes=args.max_output_bytes,
    )
    stdout_observation = stdout_capture.observation()
    stderr_observation = stderr_capture.observation()
    _replay(stdout_capture, sys.stdout.buffer)
    _replay(stderr_capture, sys.stderr.buffer)

    results: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    validation_errors = [execution_error] if execution_error is not None else []
    try:
        for raw_path in args.result_file:
            path, relative = _safe_relative(raw_path, working_directory, "result_file")
            results.append(
                {
                    "kind": "test-result",
                    "path": relative,
                    "format": "junit",
                    "digest": _digest(path),
                    "test_cases": _junit_cases(path),
                }
            )
        for raw_path in args.artifact_file:
            path, relative = _safe_relative(raw_path, working_directory, "artifact_file")
            artifacts.append(
                {
                    "kind": "artifact-observation",
                    "path": relative,
                    "digest": _digest(path),
                    "bytes": path.stat().st_size,
                }
            )
    except (OSError, ValueError) as exc:
        validation_errors.append(str(exc))
    validation_error = "; ".join(validation_errors) if validation_errors else None

    record: dict[str, Any] = {
        "format": "ai-skills-execution-record",
        "execution_id": execution_id,
        "argv": argv,
        "working_directory": working_directory_text,
        "command_digest": _command_digest(argv, working_directory_text),
        "exit_status": returncode,
        "command_result": {
            "kind": "command-result",
            "stdout": stdout_observation,
            "stderr": stderr_observation,
        },
        "results": results,
        "artifacts": artifacts,
    }
    if validation_error is not None:
        record["validation_error"] = validation_error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if failure_status is not None:
        return failure_status
    if returncode != 0:
        return returncode
    if validation_error is not None:
        raise ValueError(validation_error)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

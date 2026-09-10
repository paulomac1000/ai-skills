#!/usr/bin/env python3
"""Classify hidden runtime failures that must not be reported as a green verification gate."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
from pathlib import Path

MAX_LOG_BYTES = 16 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024

BLOCKING_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pytest_unhandled_thread", re.compile(r"PytestUnhandledThreadExceptionWarning")),
    ("python_thread_exception", re.compile(r"^\s*Exception in thread\b.*:", re.IGNORECASE)),
    ("pytest_unraisable", re.compile(r"PytestUnraisableExceptionWarning")),
    ("python_unawaited_coroutine", re.compile(r"coroutine .* was never awaited", re.IGNORECASE)),
    ("python_pending_task", re.compile(r"Task was destroyed but it is pending", re.IGNORECASE)),
    (
        "node_cancelled_file",
        re.compile(
            r"(?:^\s*cancelled\s*:|^\s*not ok\b.*#\s*cancelled\b|"
            r"failureType\s*[:=]\s*['\"]cancelled(?:ByParent)?['\"])",
            re.IGNORECASE,
        ),
    ),
    ("node_pending_promise", re.compile(r"Promise resolution is still pending", re.IGNORECASE)),
    ("node_unhandled_rejection", re.compile(r"\bunhandledRejection\b", re.IGNORECASE)),
    ("node_uncaught_exception", re.compile(r"\buncaughtException\b", re.IGNORECASE)),
)
GENERIC_WARNING = re.compile(r"\b[A-Za-z][A-Za-z0-9_]*Warning\s*:")


def _read(path: Path) -> str:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    expected: os.stat_result | None = None
    if not nofollow:
        expected = os.lstat(path)
        if stat.S_ISLNK(expected.st_mode):
            raise ValueError("log must be a regular file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | nofollow
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ValueError(f"log cannot be opened safely: {error}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("log must be a regular file")
        if expected is not None and not os.path.samestat(expected, metadata):
            raise ValueError("log path identity changed while opening")
        if metadata.st_size > MAX_LOG_BYTES:
            raise ValueError("log exceeds maximum supported size")
        remaining = MAX_LOG_BYTES + 1
        chunks: list[bytes] = []
        while remaining > 0:
            chunk = os.read(descriptor, min(READ_CHUNK_BYTES, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > MAX_LOG_BYTES:
            raise ValueError("log exceeds maximum supported size")
        if len(data) != metadata.st_size:
            raise ValueError("log changed while being read")
    finally:
        os.close(descriptor)
    return data.decode("utf-8")


def evaluate(text: str, allowed_patterns: tuple[re.Pattern[str], ...] = ()) -> dict[str, object]:
    hits: list[dict[str, object]] = []
    counts = {
        "cancelled": 0,
        "pending": 0,
        "unhandled_exceptions": 0,
        "unraisable": 0,
        "blocking_warnings": 0,
        "leaked_async_work": 0,
        "allowed_warnings": 0,
    }

    for line_number, line in enumerate(text.splitlines(), 1):
        kinds = [kind for kind, pattern in BLOCKING_PATTERNS if pattern.search(line)]
        if kinds:
            for kind in kinds:
                hits.append({"line": line_number, "kind": kind, "text": line[:1000]})
                if kind == "node_cancelled_file":
                    counts["cancelled"] += 1
                elif kind in {"node_pending_promise", "python_pending_task"}:
                    counts["pending"] += 1
                    counts["leaked_async_work"] += 1
                elif kind == "python_unawaited_coroutine":
                    counts["blocking_warnings"] += 1
                    counts["leaked_async_work"] += 1
                elif kind == "pytest_unraisable":
                    counts["unraisable"] += 1
                else:
                    counts["unhandled_exceptions"] += 1
            continue

        if GENERIC_WARNING.search(line):
            if any(pattern.search(line) for pattern in allowed_patterns):
                counts["allowed_warnings"] += 1
            else:
                counts["blocking_warnings"] += 1
                hits.append({"line": line_number, "kind": "unclassified_warning", "text": line[:1000]})

    blocking = sum(
        int(counts[key])
        for key in (
            "cancelled",
            "pending",
            "unhandled_exceptions",
            "unraisable",
            "blocking_warnings",
            "leaked_async_work",
        )
    )
    return {"schema_version": 1, **counts, "findings": hits, "verdict": "pass" if blocking == 0 else "fail"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        help="reviewed non-blocking warning regex; cannot suppress runtime failures",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        result = evaluate(_read(args.log), tuple(re.compile(value) for value in args.allow))
    except (OSError, UnicodeError, ValueError, re.error) as error:
        print(json.dumps({"verdict": "fail", "error": str(error)}, sort_keys=True))
        return 2

    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

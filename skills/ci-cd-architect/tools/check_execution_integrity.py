#!/usr/bin/env python3
"""Classify hidden runtime failures that must not be reported as a green verification gate."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

MAX_LOG_BYTES = 16 * 1024 * 1024

BLOCKING_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pytest_unhandled_thread", re.compile(r"PytestUnhandledThreadExceptionWarning")),
    ("pytest_unraisable", re.compile(r"PytestUnraisableExceptionWarning")),
    ("python_unawaited_coroutine", re.compile(r"coroutine .* was never awaited", re.IGNORECASE)),
    ("python_pending_task", re.compile(r"Task was destroyed but it is pending", re.IGNORECASE)),
    ("node_cancelled_file", re.compile(r"\bcancelled\b", re.IGNORECASE)),
    ("node_pending_promise", re.compile(r"Promise resolution is still pending", re.IGNORECASE)),
    ("node_unhandled_rejection", re.compile(r"unhandledRejection", re.IGNORECASE)),
    ("node_uncaught_exception", re.compile(r"uncaughtException", re.IGNORECASE)),
)


def _read(path: Path) -> str:
    data = path.read_bytes()
    if len(data) > MAX_LOG_BYTES:
        raise ValueError("log exceeds maximum supported size")
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
        if any(pattern.search(line) for pattern in allowed_patterns):
            counts["allowed_warnings"] += 1
            continue
        for kind, pattern in BLOCKING_PATTERNS:
            if not pattern.search(line):
                continue
            hits.append({"line": line_number, "kind": kind, "text": line[:1000]})
            if kind == "node_cancelled_file":
                counts["cancelled"] += 1
            elif kind in {"node_pending_promise", "python_pending_task"}:
                counts["pending"] += 1
                counts["leaked_async_work"] += 1
            elif kind == "pytest_unraisable":
                counts["unraisable"] += 1
            elif kind in {"pytest_unhandled_thread", "node_unhandled_rejection", "node_uncaught_exception"}:
                counts["unhandled_exceptions"] += 1
            else:
                counts["blocking_warnings"] += 1
            break

    blocking = sum(int(counts[key]) for key in ("cancelled", "pending", "unhandled_exceptions", "unraisable", "blocking_warnings"))
    return {"schema_version": 1, **counts, "findings": hits, "verdict": "pass" if blocking == 0 else "fail"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--allow", action="append", default=[], help="reviewed non-blocking regex")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        allowed = tuple(re.compile(value) for value in args.allow)
        result = evaluate(_read(args.log), allowed)
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

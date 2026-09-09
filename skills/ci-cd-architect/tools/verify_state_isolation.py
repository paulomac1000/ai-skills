#!/usr/bin/env python3
"""Snapshot protected paths and prove validation did not mutate production-effective state."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable

MAX_FILES = 100_000
MAX_FILE_BYTES = 128 * 1024 * 1024


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=True)


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def prove_disjoint(writable: Iterable[Path], protected: Iterable[Path]) -> None:
    writes = [_resolved(path) for path in writable]
    protects = [_resolved(path) for path in protected]
    for write in writes:
        for protect in protects:
            if _is_within(write, protect) or _is_within(protect, write):
                raise ValueError(f"writable/protected paths overlap: {write} <> {protect}")


def _digest_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"protected path is not a regular file: {path}")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"protected file exceeds size bound: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(paths: Iterable[Path]) -> dict[str, str]:
    result: dict[str, str] = {}
    count = 0
    for raw in paths:
        path = _resolved(raw)
        candidates = [path] if path.is_file() else sorted(item for item in path.rglob("*") if item.is_file())
        for item in candidates:
            count += 1
            if count > MAX_FILES:
                raise ValueError("protected state exceeds maximum file count")
            result[str(item)] = _digest_file(item)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    preflight = sub.add_parser("preflight")
    preflight.add_argument("--writable", action="append", type=Path, default=[])
    preflight.add_argument("--protected", action="append", type=Path, required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("--protected", action="append", type=Path, required=True)
    snap.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("assert-unchanged")
    check.add_argument("--protected", action="append", type=Path, required=True)
    check.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "preflight":
            prove_disjoint(args.writable, args.protected)
            print(json.dumps({"verdict": "pass"}))
            return 0
        if args.command == "snapshot":
            value = snapshot(args.protected)
            args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(json.dumps({"verdict": "pass", "files": len(value)}))
            return 0
        before = json.loads(args.snapshot.read_text(encoding="utf-8"))
        after = snapshot(args.protected)
        changed = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
        print(json.dumps({"verdict": "pass" if not changed else "fail", "changed": changed}, indent=2))
        return 0 if not changed else 1
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"verdict": "fail", "error": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Execute one exact argv and emit a canonical diagnostic execution record."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

EXECUTION_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
READ_CHUNK_BYTES = 1024 * 1024


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(READ_CHUNK_BYTES):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


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
    parser.add_argument("--result-file", action="append", type=Path, required=True)
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
    working_directory, working_directory_text = _safe_working_directory(
        args.working_directory,
        repository_root,
    )

    completed = subprocess.run(argv, cwd=working_directory, check=False)  # noqa: S603
    results: list[dict[str, Any]] = []
    validation_error: str | None = None
    try:
        for raw_path in args.result_file:
            path, relative = _safe_relative(raw_path, working_directory, "result_file")
            cases = _junit_cases(path)
            results.append(
                {
                    "path": relative,
                    "format": "junit",
                    "digest": _digest(path),
                    "test_cases": cases,
                }
            )
    except (OSError, ValueError) as exc:
        validation_error = str(exc)

    record = {
        "format": "ai-skills-execution-record",
        "execution_id": execution_id,
        "argv": argv,
        "working_directory": working_directory_text,
        "command_digest": _command_digest(argv, working_directory_text),
        "exit_status": completed.returncode,
        "results": results,
    }
    if validation_error is not None:
        record["validation_error"] = validation_error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if completed.returncode != 0:
        return completed.returncode
    if validation_error is not None:
        raise ValueError(validation_error)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

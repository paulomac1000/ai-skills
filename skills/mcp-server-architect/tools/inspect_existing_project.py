#!/usr/bin/env python3
"""Inspect an existing repository without executing or modifying consumer code."""

from __future__ import annotations

import argparse
import json
import os
import stat
import tomllib
from pathlib import Path
from typing import Any

MAX_FILES = 600
MAX_FILE_BYTES = 512 * 1024
MAX_TOTAL_BYTES = 12 * 1024 * 1024
IGNORED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "bin",
    "obj",
    "__pycache__",
    ".pytest_cache",
}
TEXT_SUFFIXES = {".py", ".toml", ".txt", ".ini", ".yaml", ".yml", ".md", ".json"}
HTTP_DEPENDENCIES = {"requests", "httpx", "aiohttp", "urllib3"}


def _regular_text(path: Path) -> str | None:
    try:
        metadata = path.lstat()
    except OSError:
        return None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        return None
    if metadata.st_size > MAX_FILE_BYTES:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _source_corpus(root: Path) -> tuple[str, int, int]:
    chunks: list[str] = []
    total = 0
    files = 0
    for path in sorted(root.rglob("*")):
        if files >= MAX_FILES or total >= MAX_TOTAL_BYTES:
            break
        if IGNORED_PARTS.intersection(path.parts) or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = _regular_text(path)
        if text is None:
            continue
        encoded_size = len(text.encode("utf-8"))
        if total + encoded_size > MAX_TOTAL_BYTES:
            break
        chunks.append(text)
        total += encoded_size
        files += 1
    return "\n".join(chunks).casefold(), files, total


def _pyproject(root: Path) -> dict[str, Any]:
    path = root / "pyproject.toml"
    text = _regular_text(path)
    if text is None:
        return {}
    try:
        value = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _dependency_names(project: dict[str, Any], root: Path) -> set[str]:
    names: set[str] = set()
    raw_project = project.get("project")
    if isinstance(raw_project, dict):
        dependencies = raw_project.get("dependencies")
        if isinstance(dependencies, list):
            for raw in dependencies:
                if not isinstance(raw, str):
                    continue
                token = raw.strip().split("[", 1)[0]
                for separator in ("==", ">=", "<=", "~=", "!=", ">", "<", ";", " "):
                    token = token.split(separator, 1)[0]
                if token:
                    names.add(token.casefold().replace("_", "-"))
    for candidate in sorted(root.glob("requirements*.txt")) + sorted(root.glob("requirements*.in")):
        text = _regular_text(candidate)
        if text is None:
            continue
        for line in text.splitlines():
            value = line.strip()
            if not value or value.startswith(("#", "-")):
                continue
            token = value
            for separator in ("==", ">=", "<=", "~=", "!=", ">", "<", ";", " "):
                token = token.split(separator, 1)[0]
            if token:
                names.add(token.casefold().replace("_", "-"))
    return names


def _project_version(project: dict[str, Any]) -> str | None:
    raw_project = project.get("project")
    if not isinstance(raw_project, dict):
        return None
    value = raw_project.get("version")
    return value.strip() if isinstance(value, str) and value.strip() else None


def inspect_repository(repository_root: Path) -> dict[str, Any]:
    """Return bounded source-derived facts and a progressive adoption plan."""
    root = repository_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("repository root must be a directory")
    project = _pyproject(root)
    dependencies = _dependency_names(project, root)
    corpus, scanned_files, scanned_bytes = _source_corpus(root)

    if "fastmcp" in dependencies or "fastmcp-slim" in dependencies:
        sdk_profile = "python-fastmcp-package"
    elif "mcp" in dependencies:
        sdk_profile = "python-official-mcp"
    else:
        sdk_profile = "unknown"

    has_external_upstream = bool(HTTP_DEPENDENCIES.intersection(dependencies)) or any(
        marker in corpus for marker in ("requests.get(", "requests.post(", "httpx.", "aiohttp.")
    )
    has_external_tests = (root / "tests/external").is_dir() or any(
        marker in corpus for marker in ("pytest.mark.external", '"external:"', "'external:'")
    )
    pyproject_text = _regular_text(root / "pyproject.toml") or ""
    external_default_excluded = "not external" in pyproject_text.casefold()
    upstream_contract = (root / "upstream-contract.yaml").is_file()
    live_policy = (root / "live-backend-test-policy.yaml").is_file()
    has_stdio = "stdio" in corpus
    has_streamable_http = any(marker in corpus for marker in ("streamable_http", "streamable-http"))
    has_legacy_sse = any(marker in corpus for marker in ("/sse", "legacy sse", "http+sse"))
    destructive_signal = any(
        marker in corpus
        for marker in (
            "operation_kind: destructive",
            'operation_kind="destructive"',
            'operation_kind = "destructive"',
            "delete_",
            "remove_",
        )
    )
    write_signal = destructive_signal or any(
        marker in corpus
        for marker in (
            "operation_kind: write",
            'operation_kind="write"',
            'operation_kind = "write"',
            "create_",
            "update_",
            "put_",
        )
    )

    facts: dict[str, Any] = {
        "language": "python" if project else "unknown",
        "sdk_profile": sdk_profile,
        "project_version": _project_version(project),
        "packaged": bool(project),
        "containerized": any((root / name).is_file() for name in ("Dockerfile", "Containerfile")),
        "github_actions": (root / ".github/workflows").is_dir(),
        "external_upstream": has_external_upstream,
        "external_tests": has_external_tests,
        "external_tests_default_excluded": external_default_excluded,
        "upstream_contract_present": upstream_contract,
        "live_backend_policy_present": live_policy,
        "transports": {
            "stdio": has_stdio,
            "streamable_http": has_streamable_http,
            "legacy_http_sse_signal": has_legacy_sse,
        },
        "capabilities": {
            "write_signal": write_signal,
            "destructive_signal": destructive_signal,
        },
    }

    upstream_status = "not-applicable"
    if has_external_upstream:
        upstream_status = "verified" if upstream_contract else "required"
    live_status = "not-applicable"
    if has_external_tests:
        live_status = "declared" if live_policy else "needs-policy"

    unknowns: list[str] = []
    if sdk_profile == "unknown":
        unknowns.append("MCP SDK package identity was not resolved from package metadata")
    if has_external_upstream and not upstream_contract:
        unknowns.append("external upstream contract is unobserved; probe the real boundary before adapter refactoring")
    if has_external_tests and not external_default_excluded:
        unknowns.append("external tests are not visibly deselected by default")
    if has_external_tests and not live_policy:
        unknowns.append("live-backend safety policy is missing")

    routes = ["STANDARD.md", "references/testing-strategy.md"]
    if sdk_profile == "python-fastmcp-package":
        routes.append("references/python-fastmcp-package.md")
    elif sdk_profile == "python-official-mcp":
        routes.append("references/python-official-mcp-sdk.md")
    if has_external_upstream:
        routes.append("references/upstream-contract-discovery.md")

    return {
        "format": "ai-skills-adoption-discovery",
        "schema_version": 1,
        "facts": facts,
        "plan": {
            "discovery": "complete",
            "upstream_contract": upstream_status,
            "live_backend_safety": live_status,
            "implementation": "not-evaluated",
            "local_verification": "not-evaluated",
            "provider_verification": "not-evaluated",
            "acceptance": "not-evaluated",
        },
        "required_read_set": routes,
        "unknowns": unknowns,
        "scan": {"files": scanned_files, "bytes": scanned_bytes},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    document = inspect_repository(args.repository)
    serialized = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(serialized, end="")
    else:
        if os.path.lexists(args.output):
            parser.error("output already exists; refusing to overwrite")
        args.output.write_text(serialized, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

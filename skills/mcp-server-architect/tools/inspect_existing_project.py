#!/usr/bin/env python3
"""Inspect an existing repository without executing or modifying consumer code."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
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
_PREBUILT_CONTAINER_COPY = re.compile(
    r"^\s*(?:COPY|ADD)\b[^\n]*\b(?:dist|build|out|publish|artifacts)/",
    re.IGNORECASE | re.MULTILINE,
)
_SOURCE_REVISION_ARG = re.compile(
    r"^\s*ARG\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE | re.MULTILINE,
)
_SOURCE_REVISION_FILE = re.compile(r"\bSOURCE[_-](?:REVISION|SHA)\b", re.IGNORECASE)
_RUN_INSTRUCTION = re.compile(r"^RUN\b\s*(.*)$", re.IGNORECASE)
_SOURCE_CHECK_COMMAND = re.compile(r"\b(?:test|cmp)\b", re.IGNORECASE)
_SHELL_COMMAND_BOUNDARY = re.compile(r"\s*(?:&&|\|\||;)\s*")


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
    candidates = 0
    for directory, names, filenames in os.walk(root, topdown=True, followlinks=False):
        names[:] = sorted(name for name in names if name not in IGNORED_PARTS)
        base = Path(directory)
        for filename in sorted(filenames):
            candidates += 1
            if candidates > MAX_FILES * 20 or files >= MAX_FILES or total >= MAX_TOTAL_BYTES:
                return "\n".join(chunks).casefold(), files, total
            path = base / filename
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            text = _regular_text(path)
            if text is None:
                continue
            encoded_size = len(text.encode("utf-8"))
            if total + encoded_size > MAX_TOTAL_BYTES:
                return "\n".join(chunks).casefold(), files, total
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


def _pytest_addopts(project: dict[str, Any]) -> list[str]:
    """Return parsed pytest addopts from the structured pyproject configuration only."""
    tool = project.get("tool")
    pytest = tool.get("pytest") if isinstance(tool, dict) else None
    ini_options = pytest.get("ini_options") if isinstance(pytest, dict) else None
    raw = ini_options.get("addopts") if isinstance(ini_options, dict) else None
    fragments: list[str]
    if isinstance(raw, str):
        fragments = [raw]
    elif isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        fragments = list(raw)
    else:
        return []
    tokens: list[str] = []
    try:
        for fragment in fragments:
            tokens.extend(shlex.split(fragment))
    except ValueError:
        return []
    return tokens


def _marker_expression_excludes_external(expression: str) -> bool:
    """Conservatively prove that a pytest marker expression excludes every external test."""
    normalized = " ".join(expression.casefold().split())
    if re.search(r"\bor\b", normalized):
        return False
    return re.search(r"\bnot\s+external\b", normalized) is not None


def _external_tests_default_excluded(project: dict[str, Any]) -> bool:
    tokens = _pytest_addopts(project)
    for index, token in enumerate(tokens):
        if token == "-m" and index + 1 < len(tokens):
            if _marker_expression_excludes_external(tokens[index + 1]):
                return True
        elif token.startswith("-m=") and _marker_expression_excludes_external(token[3:]):
            return True
    return False


def _docker_instructions(text: str) -> list[str]:
    """Return bounded logical Dockerfile instructions with continuations joined."""
    instructions: list[str] = []
    current: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or (not current and stripped.startswith("#")):
            continue
        continued = stripped.endswith("\\")
        current.append(stripped[:-1].rstrip() if continued else stripped)
        if continued:
            continue
        instructions.append(" ".join(current))
        current = []
    if current:
        instructions.append(" ".join(current))
    return instructions


def _source_revision_binding_signal(text: str, revision_args: list[str]) -> bool:
    """Require one comparison command to bind an artifact revision to the expected source argument."""
    source_args = [
        name
        for name in revision_args
        if "source" in name.casefold() and ("revision" in name.casefold() or "sha" in name.casefold())
    ]
    if not source_args:
        return False
    for instruction in _docker_instructions(text):
        run = _RUN_INSTRUCTION.match(instruction)
        if run is None:
            continue
        for command in _SHELL_COMMAND_BOUNDARY.split(run.group(1)):
            if _SOURCE_CHECK_COMMAND.search(command) is None or _SOURCE_REVISION_FILE.search(command) is None:
                continue
            for name in source_args:
                reference = re.compile(rf"\$(?:\{{{re.escape(name)}\}}|{re.escape(name)}\b)")
                if reference.search(command) is not None:
                    return True
    return False


def _container_build_facts(root: Path) -> dict[str, bool]:
    """Require every root build definition that copies prebuilt artifacts to bind them to source."""
    texts = [text for name in ("Dockerfile", "Containerfile") if (text := _regular_text(root / name)) is not None]
    if not texts:
        return {"prebuilt_artifact_copy": False, "source_revision_binding_signal": False}
    per_definition: list[tuple[bool, bool]] = []
    for text in texts:
        prebuilt = _PREBUILT_CONTAINER_COPY.search(text) is not None
        revision_args = _SOURCE_REVISION_ARG.findall(text)
        bound = prebuilt and _source_revision_binding_signal(text, revision_args)
        per_definition.append((prebuilt, bound))
    prebuilt_copy = any(prebuilt for prebuilt, _ in per_definition)
    source_binding = prebuilt_copy and all(not prebuilt or bound for prebuilt, bound in per_definition)
    return {
        "prebuilt_artifact_copy": prebuilt_copy,
        "source_revision_binding_signal": source_binding,
    }


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
    external_default_excluded = _external_tests_default_excluded(project)
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
    containerized = any((root / name).is_file() for name in ("Dockerfile", "Containerfile"))
    container_build = _container_build_facts(root)

    facts: dict[str, Any] = {
        "language": "python" if project else "unknown",
        "sdk_profile": sdk_profile,
        "project_version": _project_version(project),
        "packaged": bool(project),
        "containerized": containerized,
        "container_build": container_build,
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
    artifact_binding_status = "not-applicable"
    if containerized and container_build["prebuilt_artifact_copy"]:
        artifact_binding_status = (
            "declared" if container_build["source_revision_binding_signal"] else "needs-binding"
        )

    unknowns: list[str] = []
    if sdk_profile == "unknown":
        unknowns.append("MCP SDK package identity was not resolved from package metadata")
    if has_external_upstream and not upstream_contract:
        unknowns.append("external upstream contract is unobserved; probe the real boundary before adapter refactoring")
    if has_external_tests and not external_default_excluded:
        unknowns.append("external tests are not proven deselected by the structured default pytest addopts")
    if has_external_tests and not live_policy:
        unknowns.append("live-backend safety policy is missing")
    if artifact_binding_status == "needs-binding":
        unknowns.append(
            "container build copies prebuilt artifacts without a source-revision binding signal; stale local artifacts may be packaged"
        )

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
            "container_artifact_binding": artifact_binding_status,
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

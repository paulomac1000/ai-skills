#!/usr/bin/env python3
"""Collect non-secret README evidence candidates from a repository.

This tool does not decide what is true. It inventories likely canonical sources
so an agent can build a claim ledger without starting from README prose.
"""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path
from typing import Any

IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "target",
    ".tox",
    ".nox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "coverage",
    "htmlcov",
    "__pycache__",
}
TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".mjs",
    ".cjs",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".cs",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
    ".md",
    ".sh",
}
REGISTRY_MARKERS = (
    "registerTool",
    "register_tool",
    "@mcp.tool",
    "FastMCP",
    "McpServer",
    "tools/list",
    "StreamableHTTP",
    "StreamableHttp",
    "FastAPI(",
    "app.get(",
    "app.post(",
    "router.get(",
    "router.post(",
)


def read_text(path: Path, limit: int = 1_000_000) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    if len(data) > limit or b"\x00" in data:
        return ""
    return data.decode("utf-8", errors="replace")


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def safe_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return {}


def safe_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def parse_pyproject(path: Path) -> dict[str, Any]:
    data = safe_toml(path)
    raw_project = data.get("project")
    project: dict[str, Any] = raw_project if isinstance(raw_project, dict) else {}
    raw_tool = data.get("tool")
    tool = raw_tool if isinstance(raw_tool, dict) else {}
    raw_poetry = tool.get("poetry")
    poetry: dict[str, Any] = raw_poetry if isinstance(raw_poetry, dict) else {}
    return {
        "name": project.get("name") or poetry.get("name"),
        "version": project.get("version") or poetry.get("version"),
        "requires_python": project.get("requires-python"),
        "scripts": project.get("scripts", {}),
        "dependencies_declared": bool(project.get("dependencies") or poetry.get("dependencies")),
    }


def parse_package_json(path: Path) -> dict[str, Any]:
    data = safe_json(path)
    return {
        "name": data.get("name"),
        "version": data.get("version"),
        "private": data.get("private"),
        "engines": data.get("engines", {}),
        "scripts": data.get("scripts", {}),
        "bin": data.get("bin", {}),
        "package_manager": data.get("packageManager"),
    }


def parse_cargo(path: Path) -> dict[str, Any]:
    data = safe_toml(path)
    raw_package = data.get("package")
    package: dict[str, Any] = raw_package if isinstance(raw_package, dict) else {}
    return {
        "name": package.get("name"),
        "version": package.get("version"),
        "rust_version": package.get("rust-version"),
    }


def parse_go_mod(path: Path) -> dict[str, Any]:
    text = read_text(path)
    module = re.search(r"(?m)^module\s+(.+)$", text)
    go = re.search(r"(?m)^go\s+([0-9.]+)$", text)
    toolchain = re.search(r"(?m)^toolchain\s+(.+)$", text)
    return {
        "module": module.group(1).strip() if module else None,
        "go": go.group(1).strip() if go else None,
        "toolchain": toolchain.group(1).strip() if toolchain else None,
    }


def parse_env_names(path: Path) -> list[str]:
    names: set[str] = set()
    for line in read_text(path).splitlines():
        match = re.match(r"\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=", line)
        if match:
            names.add(match.group(1))
    return sorted(names)


def docker_summary(path: Path) -> dict[str, Any]:
    text = read_text(path)
    fields: dict[str, list[str]] = {}
    for instruction in ("FROM", "EXPOSE", "USER", "ENTRYPOINT", "CMD"):
        values = re.findall(rf"(?mi)^\s*{instruction}\s+(.+)$", text)
        if values:
            fields[instruction.lower()] = [value.strip() for value in values]
    return fields


def iter_source_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        yield path


def registry_hints(root: Path, max_files: int = 40) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    for path in iter_source_files(root):
        text = read_text(path, limit=500_000)
        if not text:
            continue
        found = [marker for marker in REGISTRY_MARKERS if marker in text]
        if found:
            hints.append({"path": rel(path, root), "markers": found})
            if len(hints) >= max_files:
                break
    return hints


def workflow_summary(root: Path) -> list[dict[str, Any]]:
    workflow_dir = root / ".github" / "workflows"
    if not workflow_dir.is_dir():
        return []
    result = []
    for path in sorted(workflow_dir.glob("*")):
        if path.suffix.lower() not in {".yml", ".yaml"}:
            continue
        text = read_text(path)
        run_lines = [match.group(1).strip() for match in re.finditer(r"(?m)^\s*run:\s*(.+)$", text)][:20]
        uses = [match.group(1).strip() for match in re.finditer(r"(?m)^\s*uses:\s*(.+)$", text)][:20]
        result.append({"path": rel(path, root), "run": run_lines, "uses": uses})
    return result


def doc_inventory(root: Path) -> list[str]:
    candidates = []
    for name in (
        "README.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "LICENSE",
        "LICENSE.md",
        "AGENTS.md",
        ".env.example",
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    ):
        path = root / name
        if path.exists():
            candidates.append(name)
    docs = root / "docs"
    if docs.is_dir():
        for path in sorted(docs.rglob("*.md"))[:100]:
            if not any(part in IGNORE_DIRS for part in path.parts):
                candidates.append(rel(path, root))
    return candidates


def readme_observations(root: Path) -> dict[str, Any]:
    path = root / "README.md"
    if not path.exists():
        return {"exists": False}
    text = read_text(path)
    headings = re.findall(r"(?m)^(#{1,6})\s+(.+?)\s*$", text)
    volatile = []
    patterns = {
        "test_count": r"\b\d[\d,._]*\s+tests?\b",
        "coverage_percent": r"\bcoverage\b.{0,20}\b\d{1,3}(?:\.\d+)?%",
        "tool_count": r"\b(?:tools?|capabilities)\s*[:(]?\s*\d+\b|\b\d+\s+(?:MCP\s+)?tools?\b",
        "static_build_badge": r"shields\.io/badge/build-(?:passing|success|green)",
        "hardcoded_version_badge": r"shields\.io/badge/version-[0-9]",
    }
    for label, pattern in patterns.items():
        if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
            volatile.append(label)
    return {
        "exists": True,
        "headings": [{"level": len(mark), "text": title} for mark, title in headings],
        "line_count": len(text.splitlines()),
        "possible_volatile_claims": volatile,
    }


def build_report(root: Path) -> dict[str, Any]:
    report: dict[str, Any] = {
        "root": str(root.resolve()),
        "documents": doc_inventory(root),
        "manifests": {},
        "environment_examples": {},
        "docker": {},
        "workflows": workflow_summary(root),
        "registry_and_server_hints": registry_hints(root),
        "readme": readme_observations(root),
        "notes": [
            "This inventory is evidence discovery, not a truth verdict.",
            "No environment-variable values are collected.",
            "Existing README claims remain low-authority until reconciled.",
        ],
    }

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        report["manifests"]["pyproject.toml"] = parse_pyproject(pyproject)

    package_json = root / "package.json"
    if package_json.exists():
        report["manifests"]["package.json"] = parse_package_json(package_json)

    cargo = root / "Cargo.toml"
    if cargo.exists():
        report["manifests"]["Cargo.toml"] = parse_cargo(cargo)

    go_mod = root / "go.mod"
    if go_mod.exists():
        report["manifests"]["go.mod"] = parse_go_mod(go_mod)

    for name in (".env.example", ".env.sample", "example.env"):
        path = root / name
        if path.exists():
            report["environment_examples"][name] = parse_env_names(path)

    for path in sorted(root.glob("Dockerfile*")):
        if path.is_file():
            report["docker"][rel(path, root)] = docker_summary(path)

    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?", default=".", help="repository root")
    parser.add_argument("-o", "--output", help="write JSON to this file")
    args = parser.parse_args()

    root = Path(args.repo).resolve()
    if not root.is_dir():
        parser.error(f"not a directory: {root}")

    report = build_report(root)
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"

    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

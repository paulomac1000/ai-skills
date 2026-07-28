#!/usr/bin/env python3
"""Discover repository structure without executing repository-controlled commands."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

OutputFormat = Literal["json", "text"]

IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "bin",
    "coverage",
    "dist",
    "node_modules",
    "obj",
    "target",
}
MANIFEST_NAMES = {
    "Cargo.toml",
    "Directory.Build.props",
    "Directory.Packages.props",
    "Gemfile",
    "global.json",
    "go.mod",
    "package.json",
    "pnpm-workspace.yaml",
    "pyproject.toml",
    "requirements.txt",
    "setup.cfg",
    "setup.py",
    "uv.lock",
    "yarn.lock",
}
TASK_RUNNER_NAMES = {
    "Justfile",
    "Makefile",
    "Taskfile.yaml",
    "Taskfile.yml",
    "build.ps1",
    "build.sh",
    "justfile",
}
CI_NAMES = {
    ".circleci/config.yml",
    ".gitlab-ci.yml",
    "Jenkinsfile",
    "azure-pipelines.yml",
}
DOC_MARKERS = {
    "CONTRIBUTING.md",
    "README.md",
    "mkdocs.yml",
    "mkdocs.yaml",
}


@dataclass(frozen=True)
class Discovery:
    """Deterministic repository inventory used by AGENTS.md authoring and audit."""

    root: str
    files: tuple[str, ...]
    ecosystems: tuple[str, ...]
    manifests: tuple[str, ...]
    ci_files: tuple[str, ...]
    task_runners: tuple[str, ...]
    agent_files: tuple[str, ...]
    documentation: tuple[str, ...]
    symlinks: tuple[str, ...]
    empty: bool
    monorepo_signals: tuple[str, ...]


def _safe_root(path: Path) -> Path:
    candidate = Path(os.path.abspath(path.expanduser()))
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        if current.is_symlink():
            raise ValueError(f"repository root contains a symlink component: {current}")
        if not current.exists():
            break
    if not candidate.exists():
        raise ValueError(f"repository root does not exist: {candidate}")
    if not candidate.is_dir():
        raise ValueError(f"repository root is not a directory: {candidate}")
    return candidate.resolve(strict=True)


def _relative(root: Path, value: Path) -> str:
    return value.relative_to(root).as_posix()


def _classify_ecosystems(files: set[str]) -> set[str]:
    names = {Path(value).name for value in files}
    suffixes = {Path(value).suffix.casefold() for value in files}
    ecosystems: set[str] = set()
    if {"pyproject.toml", "requirements.txt", "setup.py", "setup.cfg", "uv.lock"} & names or ".py" in suffixes:
        ecosystems.add("python")
    if {"global.json", "Directory.Build.props", "Directory.Packages.props"} & names or {
        ".sln",
        ".csproj",
        ".cs",
    } & suffixes:
        ecosystems.add("dotnet")
    if {"package.json", "pnpm-workspace.yaml", "yarn.lock"} & names or {
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
    } & suffixes:
        ecosystems.add("node")
    if "go.mod" in names or ".go" in suffixes:
        ecosystems.add("go")
    if "Cargo.toml" in names or ".rs" in suffixes:
        ecosystems.add("rust")
    if "Gemfile" in names or ".rb" in suffixes:
        ecosystems.add("ruby")
    if not ecosystems and any(Path(value).suffix.casefold() in {".md", ".rst", ".adoc"} for value in files):
        ecosystems.add("documentation")
    return ecosystems


def discover(root: Path) -> Discovery:
    """Return a static repository inventory without following symlinks or reading executable content."""
    safe_root = _safe_root(root)
    files: set[str] = set()
    symlinks: set[str] = set()

    for directory, directory_names, file_names in os.walk(safe_root, followlinks=False):
        current = Path(directory)
        retained_directories: list[str] = []
        for name in sorted(directory_names):
            candidate = current / name
            relative = _relative(safe_root, candidate)
            if candidate.is_symlink():
                symlinks.add(relative)
            elif name not in IGNORED_DIRECTORIES:
                retained_directories.append(name)
        directory_names[:] = retained_directories

        for name in sorted(file_names):
            candidate = current / name
            relative = _relative(safe_root, candidate)
            if candidate.is_symlink():
                symlinks.add(relative)
                continue
            if candidate.is_file():
                files.add(relative)

    manifests = {
        value
        for value in files
        if Path(value).name in MANIFEST_NAMES or Path(value).suffix.casefold() in {".csproj", ".sln"}
    }
    ci_files = {
        value
        for value in files
        if value in CI_NAMES
        or value.startswith(".github/workflows/")
        and Path(value).suffix.casefold() in {".yml", ".yaml"}
    }
    task_runners = {
        value
        for value in files
        if Path(value).name in TASK_RUNNER_NAMES
        or value.startswith("scripts/")
        and Path(value).suffix.casefold() in {".py", ".ps1", ".sh"}
    }
    agent_files = {value for value in files if Path(value).name == "AGENTS.md"}
    documentation = {
        value
        for value in files
        if Path(value).name in DOC_MARKERS
        or value.startswith("docs/")
        and Path(value).suffix.casefold() in {".md", ".rst", ".adoc"}
    }

    monorepo_signals: set[str] = set()
    if any(value in files for value in ("pnpm-workspace.yaml", "Directory.Packages.props")):
        monorepo_signals.add("workspace-manifest")
    if len({Path(value).parent for value in manifests if Path(value).parent != Path(".")}) > 1:
        monorepo_signals.add("multiple-project-roots")
    if any(Path(value).parent != Path(".") for value in agent_files):
        monorepo_signals.add("nested-agent-instructions")

    ordered_files = tuple(sorted(files))
    return Discovery(
        root=safe_root.as_posix(),
        files=ordered_files,
        ecosystems=tuple(sorted(_classify_ecosystems(files))),
        manifests=tuple(sorted(manifests)),
        ci_files=tuple(sorted(ci_files)),
        task_runners=tuple(sorted(task_runners)),
        agent_files=tuple(sorted(agent_files)),
        documentation=tuple(sorted(documentation)),
        symlinks=tuple(sorted(symlinks)),
        empty=not ordered_files,
        monorepo_signals=tuple(sorted(monorepo_signals)),
    )


def _render_text(result: Discovery) -> str:
    rows = [
        f"root: {result.root}",
        f"empty: {str(result.empty).lower()}",
        f"ecosystems: {', '.join(result.ecosystems) or 'none'}",
        f"manifests: {len(result.manifests)}",
        f"ci_files: {len(result.ci_files)}",
        f"task_runners: {len(result.task_runners)}",
        f"agent_files: {len(result.agent_files)}",
        f"symlinks_not_followed: {len(result.symlinks)}",
    ]
    return "\n".join(rows)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument("--format", choices=("json", "text"), default="json", dest="output_format")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = discover(args.root)
    except ValueError as error:
        print(str(error))
        return 2
    if args.output_format == "json":
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print(_render_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

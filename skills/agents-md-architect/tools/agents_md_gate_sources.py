#!/usr/bin/env python3
"""Classify repository CI/task sources for AGENTS.md audit budgets."""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from agents_md_types import MAX_GATE_FILES
from discover_repository import Discovery, discover

Classification = Literal["ci_entrypoint", "task_entrypoint", "helper", "library", "generated", "excluded"]

MAIN_GUARD = re.compile(
    r"""(?m)^\s*if\s+__name__\s*==\s*['"]__main__['"]\s*:"""
)
SCRIPT_REFERENCE = re.compile(
    r"""(?<![A-Za-z0-9_.-])(?:python(?:3)?\s+|bash\s+|sh\s+|pwsh\s+|powershell\s+|\./)?(?P<path>(?:scripts|bin)/[A-Za-z0-9_./-]+(?:\.(?:py|sh|ps1|rb))?)(?![A-Za-z0-9_.-])"""
)
MAX_CLASSIFIER_FILE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class GateSource:
    path: str
    classification: Classification
    counted: bool
    reason: str


@dataclass(frozen=True)
class GateSourceInventory:
    policy_revision: str
    limit: int
    count: int
    headroom: int
    sources: tuple[GateSource, ...]


def _read_bounded(root: Path, relative: str) -> str:
    path = root / relative
    if path.is_symlink():
        raise ValueError(f"refusing symlink gate source: {relative}")
    resolved = path.resolve(strict=True)
    resolved.relative_to(root)
    if not resolved.is_file():
        raise ValueError(f"gate source is not a regular file: {relative}")
    data = resolved.read_bytes()
    if len(data) > MAX_CLASSIFIER_FILE_BYTES:
        raise ValueError(f"gate source exceeds {MAX_CLASSIFIER_FILE_BYTES} bytes: {relative}")
    return data.decode("utf-8")


def _is_executable(root: Path, relative: str) -> bool:
    try:
        return os.access((root / relative).resolve(strict=True), os.X_OK)
    except OSError:
        return False


def _referenced_task_paths(root: Path, discovery: Discovery) -> set[str]:
    references: set[str] = set()
    source_paths = set(discovery.ci_files)
    source_paths.update(
        path for path in discovery.task_runners
        if Path(path).name in {"Makefile", "makefile", "Justfile", "justfile", "Taskfile.yml", "Taskfile.yaml", "build.sh", "build.ps1"}
    )
    source_paths.update(
        path for path in discovery.manifests
        if Path(path).name in {"package.json", "pyproject.toml"}
    )
    for relative in sorted(source_paths):
        try:
            text = _read_bounded(root, relative)
        except (OSError, UnicodeError, ValueError):
            continue
        for match in SCRIPT_REFERENCE.finditer(text):
            references.add(match.group("path").lstrip("./"))
    return references


def classify_gate_sources(
    root: Path,
    discovery: Discovery,
    *,
    limit: int = MAX_GATE_FILES,
    policy_revision: str = "agents-md-gate-sources-1",
) -> GateSourceInventory:
    """Classify discovered CI/task-shaped sources without counting helpers as entrypoints."""
    safe_root = Path(discovery.root)
    references = _referenced_task_paths(safe_root, discovery)
    rows: list[GateSource] = []

    for relative in sorted(set((*discovery.ci_files, *discovery.task_runners))):
        path = Path(relative)
        if relative in discovery.ci_files:
            rows.append(GateSource(relative, "ci_entrypoint", True, "discovered CI workflow/configuration"))
            continue

        name = path.name
        if name in {"Makefile", "makefile", "Justfile", "justfile", "Taskfile.yml", "Taskfile.yaml", "build.sh", "build.ps1"}:
            rows.append(GateSource(relative, "task_entrypoint", True, "well-known repository task-runner entrypoint"))
            continue
        if relative.startswith("bin/"):
            rows.append(GateSource(relative, "task_entrypoint", True, "bin/ is an explicit command entrypoint namespace"))
            continue
        if relative in references:
            rows.append(GateSource(relative, "task_entrypoint", True, "referenced by CI or a public repository task surface"))
            continue
        if _is_executable(safe_root, relative):
            rows.append(GateSource(relative, "task_entrypoint", True, "file has executable mode"))
            continue

        suffix = path.suffix.casefold()
        if suffix == ".py":
            try:
                text = _read_bounded(safe_root, relative)
            except (OSError, UnicodeError, ValueError) as error:
                rows.append(GateSource(relative, "helper", False, f"could not prove independent entrypoint: {error}"))
                continue
            if MAIN_GUARD.search(text):
                rows.append(GateSource(relative, "task_entrypoint", True, "Python module exposes an explicit __main__ entrypoint"))
            else:
                rows.append(GateSource(relative, "helper", False, "script-shaped file has no independent entrypoint evidence"))
            continue

        rows.append(GateSource(relative, "helper", False, "script-shaped file has no independent entrypoint evidence"))

    count = sum(1 for row in rows if row.counted)
    return GateSourceInventory(
        policy_revision=policy_revision,
        limit=limit,
        count=count,
        headroom=limit - count,
        sources=tuple(rows),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument("--limit", type=int, default=MAX_GATE_FILES)
    args = parser.parse_args()
    try:
        discovery = discover(args.root)
        inventory = classify_gate_sources(args.root, discovery, limit=args.limit)
    except (OSError, UnicodeError, ValueError) as error:
        print(json.dumps({"verdict": "fail", "error": str(error)}, sort_keys=True))
        return 2
    payload = {
        **asdict(inventory),
        "verdict": "pass" if inventory.count <= inventory.limit else "fail",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if inventory.count <= inventory.limit else 1


if __name__ == "__main__":
    raise SystemExit(main())

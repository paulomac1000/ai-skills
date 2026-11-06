#!/usr/bin/env python3
"""Classify repository CI/task sources for AGENTS.md audit budgets."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from agents_md_python_imports import collect_imported_libraries
from agents_md_source_io import is_executable_shebang_script, read_bounded
from agents_md_source_types import (
    GATE_SOURCE_POLICY_REVISION,
    MAIN_GUARD,
    WELL_KNOWN_TASK_RUNNERS,
    GateSource,
    GateSourceInventory,
    TaskSourceScan,
)
from agents_md_task_source_scan import collect_task_references
from agents_md_types import MAX_GATE_FILES
from discover_repository import Discovery, discover

__all__ = ["GATE_SOURCE_POLICY_REVISION", "GateSource", "GateSourceInventory", "classify_gate_sources"]

# Retain the tested private facade while implementation lives in bounded helpers.
_is_executable_shebang_script = is_executable_shebang_script
_read_bounded = read_bounded


def classify_gate_sources(
    root: Path,
    discovery: Discovery,
    *,
    limit: int = MAX_GATE_FILES,
    policy_revision: str = GATE_SOURCE_POLICY_REVISION,
) -> GateSourceInventory:
    """Classify entrypoints and bounded imported sources without executing them."""
    safe_root = Path(discovery.root)
    task_scan: TaskSourceScan = collect_task_references(safe_root, discovery)
    imported_libraries, import_issues = collect_imported_libraries(safe_root, discovery, task_scan)
    candidates = set(discovery.ci_files)
    candidates.update(discovery.task_runners)
    candidates.update(task_scan.references)
    candidates.update(imported_libraries)
    candidates.update(task_scan.external_sources)
    entrypoint_paths = set(task_scan.references)
    rows: list[GateSource] = []

    for relative in sorted(candidates):
        external_origins = task_scan.external_sources.get(relative)
        if external_origins is not None:
            rows.append(
                GateSource(
                    relative,
                    "excluded",
                    False,
                    "external checkout identity is recorded for separate validation; "
                    "content is not read or counted as repository-local code",
                    external_origins,
                )
            )
            continue

        path = Path(relative)
        origins = set(task_scan.references.get(relative, ()))
        origins.update(imported_libraries.get(relative, ()))
        origin_rows = tuple(sorted(origins))
        if relative in discovery.ci_files:
            rows.append(
                GateSource(
                    relative,
                    "ci_entrypoint",
                    True,
                    "discovered CI workflow/configuration",
                    origin_rows or ("discovered CI workflow/configuration",),
                )
            )
            continue
        if path.name in WELL_KNOWN_TASK_RUNNERS:
            rows.append(
                GateSource(
                    relative,
                    "task_entrypoint",
                    True,
                    "well-known repository task-runner entrypoint",
                    origin_rows or ("well-known repository task-runner entrypoint",),
                )
            )
            continue
        if relative.startswith("bin/"):
            rows.append(
                GateSource(
                    relative,
                    "task_entrypoint",
                    True,
                    "bin/ is an explicit command entrypoint namespace",
                    origin_rows or ("explicit bin/ entrypoint namespace",),
                )
            )
            continue
        if relative in task_scan.module_invocations:
            rows.append(
                GateSource(
                    relative,
                    "task_entrypoint",
                    True,
                    "invoked as a Python module by a public repository task surface",
                    origin_rows,
                )
            )
            continue
        if relative in entrypoint_paths:
            rows.append(
                GateSource(
                    relative,
                    "task_entrypoint",
                    True,
                    "referenced by CI or another public repository task surface",
                    origin_rows,
                )
            )
            continue
        if is_executable_shebang_script(safe_root, relative):
            rows.append(
                GateSource(
                    relative,
                    "task_entrypoint",
                    True,
                    "executable scripts/ file has a shebang and is independently runnable",
                    origin_rows or ("executable scripts/ shebang",),
                )
            )
            continue

        if path.suffix.casefold() == ".py":
            try:
                text = read_bounded(safe_root, relative)
            except (OSError, UnicodeError, ValueError) as error:
                rows.append(
                    GateSource(
                        relative,
                        "helper",
                        False,
                        f"could not prove independent entrypoint: {error}",
                        origin_rows,
                    )
                )
                continue
            if MAIN_GUARD.search(text):
                rows.append(
                    GateSource(
                        relative,
                        "task_entrypoint",
                        True,
                        "Python module exposes an explicit __main__ entrypoint",
                        origin_rows or ("explicit Python __main__ guard",),
                    )
                )
            elif relative in imported_libraries:
                importers = ", ".join(origin_rows[:5])
                rows.append(
                    GateSource(
                        relative,
                        "library",
                        False,
                        f"imported by a counted task entrypoint; not independently invoked: {importers}",
                        origin_rows,
                    )
                )
            else:
                rows.append(
                    GateSource(
                        relative,
                        "helper",
                        False,
                        "script-shaped file has no independent entrypoint evidence",
                        origin_rows,
                    )
                )
            continue

        rows.append(
            GateSource(
                relative,
                "helper",
                False,
                "script-shaped file has no independent entrypoint evidence",
                origin_rows,
            )
        )

    count = sum(row.counted for row in rows)
    issues = tuple(sorted(set((*task_scan.issues, *import_issues))))
    return GateSourceInventory(policy_revision, limit, count, limit - count, tuple(rows), issues)


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
    complete = inventory.count <= inventory.limit and not inventory.issues
    print(json.dumps({**asdict(inventory), "verdict": "pass" if complete else "fail"}, indent=2, sort_keys=True))
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())

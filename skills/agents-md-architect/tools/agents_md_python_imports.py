"""Bounded static AST inventory of repository-local Python imports."""

from __future__ import annotations

import ast
import importlib.util
from collections import deque
from pathlib import Path

from agents_md_python_modules import resolve_module_paths
from agents_md_source_io import read_bounded
from agents_md_source_types import (
    MAX_IMPORT_CONTEXTS,
    MAX_IMPORT_DEPTH,
    MAX_RELATED_SOURCE_FILES,
    ModuleInvocation,
    TaskSourceScan,
)
from discover_repository import Discovery


def imported_module_names(module_name: str, text: str) -> tuple[tuple[str, int], ...]:
    """Parse import declarations as data; never import or execute candidate code."""
    tree = ast.parse(text)
    modules: set[tuple[str, int]] = set()
    package = module_name.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported = node.module or ""
            if node.level:
                if not package:
                    continue
                try:
                    imported = importlib.util.resolve_name("." * node.level + imported, package)
                except (ImportError, ValueError):
                    continue
            if imported:
                modules.add((imported, node.lineno))
                modules.update((f"{imported}.{alias.name}", node.lineno) for alias in node.names if alias.name != "*")
    return tuple(sorted(modules))


def collect_imported_libraries(
    root: Path,
    discovery: Discovery,
    task_sources: TaskSourceScan,
) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
    """Follow repository-local AST imports within explicit file/depth bounds."""
    discovered_files = set(discovery.files)
    direct_entrypoints = set(task_sources.references)
    imported_origins: dict[str, set[str]] = {}
    issues: list[str] = []
    initial = [
        invocation
        for invocations in (
            *task_sources.module_invocations.values(),
            *task_sources.direct_python.values(),
            *task_sources.package_initializers.values(),
        )
        for invocation in invocations
    ]
    pending = deque((invocation, 0) for invocation in initial)
    visited: set[tuple[str, str, tuple[str, ...]]] = set()
    visited_files: set[str] = set()
    for path, invocations in task_sources.package_initializers.items():
        imported_origins.setdefault(path, set()).update(invocation.origin for invocation in invocations)

    while pending:
        invocation, depth = pending.popleft()
        context_key = (invocation.path, invocation.module, invocation.import_roots)
        if context_key in visited:
            continue
        if len(visited) >= MAX_IMPORT_CONTEXTS:
            issues.append(
                f"Python import inventory exceeds {MAX_IMPORT_CONTEXTS} contexts; "
                f"dependency chain at {invocation.origin} remains unclassified"
            )
            break
        if invocation.path not in visited_files and len(visited_files) >= MAX_RELATED_SOURCE_FILES:
            issues.append(
                f"Python import inventory exceeds {MAX_RELATED_SOURCE_FILES} distinct files; "
                f"dependency chain at {invocation.origin} remains unclassified"
            )
            break
        visited.add(context_key)
        visited_files.add(invocation.path)
        if depth > MAX_IMPORT_DEPTH:
            issues.append(f"Python import depth exceeds {MAX_IMPORT_DEPTH} at {invocation.path}")
            continue
        try:
            text = read_bounded(root, invocation.path)
            imports = imported_module_names(invocation.module, text)
        except (OSError, UnicodeError, ValueError, SyntaxError) as error:
            issues.append(f"cannot inspect imports in {invocation.path!r}: {error}")
            continue

        for module, line_number in imports:
            matches: dict[str, str] = {}
            for import_root in invocation.import_roots:
                matches.update(resolve_module_paths(module, (import_root,), discovered_files))
            if len(matches) > 1:
                issues.append(
                    f"ambiguous repository import {module!r} at {invocation.path}:{line_number}: "
                    + ", ".join(sorted(matches))
                )
            for path, resolved_module in sorted(matches.items()):
                if path in direct_entrypoints:
                    continue
                origin = f"{invocation.path}:{line_number}"
                imported_origins.setdefault(path, set()).add(origin)
                if Path(path).suffix.casefold() != ".py":
                    continue
                if depth >= MAX_IMPORT_DEPTH:
                    issues.append(f"Python import depth exceeds {MAX_IMPORT_DEPTH} at {path}")
                    continue
                pending.append(
                    (
                        ModuleInvocation(path, resolved_module, invocation.import_roots, origin),
                        depth + 1,
                    )
                )
    return (
        {path: tuple(sorted(origins)) for path, origins in imported_origins.items()},
        tuple(sorted(set(issues))),
    )

"""Bounded static AST inventory of repository-local Python imports."""

from __future__ import annotations

import ast
import importlib.util
import posixpath
from collections import deque
from pathlib import Path

from agents_md_checkout_sources import resolve_import_source_path
from agents_md_source_io import read_bounded
from agents_md_source_types import (
    MAX_IMPORT_CONTEXTS,
    MAX_IMPORT_DEPTH,
    MAX_RELATED_SOURCE_FILES,
    CheckoutContext,
    CommandSource,
    ImportRoot,
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


def module_name_for_path(path: str, root: str) -> str | None:
    """Derive a Python import name when a source path is under one import root."""
    try:
        relative = Path(path).relative_to(Path(root))
    except ValueError:
        return None
    parts = list(relative.parts)
    if not parts:
        return None
    if parts[-1] == "__init__.py":
        parts.pop()
    else:
        parts[-1] = Path(parts[-1]).stem
    return ".".join(part for part in parts if part)


def has_repository_module_namespace(
    module: str,
    roots: tuple[str, ...],
    discovered_files: set[str],
    discovered_symlinks: tuple[str, ...],
) -> bool:
    """Detect a local namespace whose requested module target is missing."""
    namespace = module.split(".", 1)[0].replace(".", "/")
    for root in roots:
        base = posixpath.normpath(posixpath.join(root, namespace))
        if base == ".." or base.startswith("../") or base.startswith("/"):
            continue
        if (
            f"{base}.py" in discovered_files
            or any(path.startswith(f"{base}/") for path in discovered_files)
            or any(
                link == base or link == f"{base}.py" or link.startswith(f"{base}/") or base.startswith(f"{link}/")
                for link in discovered_symlinks
            )
        ):
            return True
    return False


def collect_imported_libraries(
    root: Path,
    discovery: Discovery,
    task_sources: TaskSourceScan,
) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]], tuple[str, ...]]:
    """Follow repository-local AST imports within explicit file/depth bounds."""
    discovered_files = set(discovery.files)
    imported_origins: dict[str, set[str]] = {}
    external_origins: dict[str, set[str]] = {}
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
    visited: set[tuple[str, str, tuple[ImportRoot, ...], str, CheckoutContext | None]] = set()
    visited_files: set[str] = set()
    for path, invocations in task_sources.package_initializers.items():
        imported_origins.setdefault(path, set()).update(invocation.origin for invocation in invocations)

    while pending:
        invocation, depth = pending.popleft()
        context_key = (
            invocation.path,
            invocation.module,
            invocation.import_roots,
            invocation.working_directory,
            invocation.checkout_context,
        )
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

        module_source = CommandSource(
            invocation.path,
            invocation.working_directory,
            "",
            invocation.origin,
            invocation.checkout_context,
        )
        for module, line_number in imports:
            matches: dict[str, str] = {}
            shadowing = sorted(
                {
                    link
                    for link in discovery.symlinks
                    for import_root in invocation.import_roots
                    for base in (posixpath.normpath(posixpath.join(import_root.path, module.replace(".", "/"))),)
                    for candidate in (base, f"{base}.py", f"{base}/__init__.py")
                    if link == candidate or candidate.startswith(f"{link}/")
                }
            )
            if shadowing:
                issues.append(
                    f"imported dependency {module!r} at {invocation.path}:{line_number} "
                    f"resolves to repository symlink(s) {', '.join(repr(link) for link in shadowing)}; "
                    "the target is outside the audit read boundary"
                )
            for import_root in invocation.import_roots:
                module_base = posixpath.normpath(posixpath.join(import_root.path, module.replace(".", "/")))
                for workspace_path in (f"{module_base}.py", f"{module_base}/__init__.py"):
                    if workspace_path == ".." or workspace_path.startswith("../") or workspace_path.startswith("/"):
                        continue
                    local_path, external_path, ownership_issue = resolve_import_source_path(
                        module_source, import_root, workspace_path
                    )
                    if ownership_issue is not None:
                        issues.append(
                            f"cannot establish import ownership at {invocation.path}:{line_number}: {ownership_issue}"
                        )
                    elif external_path is not None:
                        external_origins.setdefault(external_path, set()).add(f"{invocation.path}:{line_number}")
                    elif local_path is not None and local_path in discovered_files:
                        matches[local_path] = module
            if len(matches) > 1:
                issues.append(
                    f"ambiguous repository import {module!r} at {invocation.path}:{line_number}: "
                    + ", ".join(sorted(matches))
                )
            for path, resolved_module in sorted(matches.items()):
                origin = f"{invocation.path}:{line_number}"
                imported_origins.setdefault(path, set()).add(origin)
                if Path(path).suffix.casefold() != ".py":
                    continue
                if depth >= MAX_IMPORT_DEPTH:
                    issues.append(f"Python import depth exceeds {MAX_IMPORT_DEPTH} at {path}")
                    continue
                module_context = f"{resolved_module}.__init__" if Path(path).name == "__init__.py" else resolved_module
                pending.append(
                    (
                        ModuleInvocation(
                            path,
                            module_context,
                            invocation.import_roots,
                            origin,
                            invocation.working_directory,
                            invocation.checkout_context,
                        ),
                        depth + 1,
                    )
                )
            module_parts = module.split(".")
            for import_root in invocation.import_roots:
                for prefix_length in range(1, len(module_parts)):
                    package_name = ".".join(module_parts[:prefix_length])
                    package_path = posixpath.normpath(posixpath.join(import_root.path, package_name.replace(".", "/")))
                    if package_path == ".." or package_path.startswith("../") or package_path.startswith("/"):
                        continue
                    workspace_initializer = f"{package_path}/__init__.py"
                    local_path, external_path, ownership_issue = resolve_import_source_path(
                        module_source, import_root, workspace_initializer
                    )
                    origin = f"{invocation.path}:{line_number}"
                    if ownership_issue is not None:
                        issues.append(f"cannot establish import ownership at {origin}: {ownership_issue}")
                        continue
                    if external_path is not None:
                        external_origins.setdefault(external_path, set()).add(origin)
                        continue
                    if local_path is None or local_path not in discovered_files:
                        continue
                    imported_origins.setdefault(local_path, set()).add(origin)
                    if depth >= MAX_IMPORT_DEPTH:
                        issues.append(f"Python import depth exceeds {MAX_IMPORT_DEPTH} at {local_path}")
                        continue
                    pending.append(
                        (
                            ModuleInvocation(
                                local_path,
                                f"{package_name}.__init__",
                                invocation.import_roots,
                                origin,
                                invocation.working_directory,
                                invocation.checkout_context,
                            ),
                            depth + 1,
                        )
                    )
    return (
        {path: tuple(sorted(origins)) for path, origins in imported_origins.items()},
        {path: tuple(sorted(origins)) for path, origins in external_origins.items()},
        tuple(sorted(set(issues))),
    )

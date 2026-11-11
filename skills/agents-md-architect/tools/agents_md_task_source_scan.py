"""Discover bounded, source-qualified CI and task invocation provenance."""

from __future__ import annotations

import shlex
from collections import deque
from collections.abc import Collection
from dataclasses import replace
from pathlib import Path

from agents_md_checkout_sources import (
    resolve_checkout_source_path,
)
from agents_md_completion_evidence import _package_script_commands, public_task_invocations
from agents_md_composite_steps import composite_action_invocations
from agents_md_python_evidence import _extract_python_invocations
from agents_md_python_imports import module_name_for_path
from agents_md_python_modules import module_invocation_references
from agents_md_python_roots import invocation_roots_for_script
from agents_md_shell_evidence import _extract_gate_invocations
from agents_md_source_io import command_origin, local_reference_resolves, public_task_surfaces, read_bounded
from agents_md_source_types import (
    COMMAND_PATH_REFERENCE,
    MAX_RELATED_SOURCE_FILES,
    MAX_WRAPPER_DEPTH,
    WELL_KNOWN_TASK_RUNNERS,
    CheckoutContext,
    CommandSource,
    ModuleInvocation,
    TaskSourceScan,
    WorkflowCommandScan,
)
from agents_md_workflow_contexts import github_workflow_command_scan
from discover_repository import Discovery


def _commands_from_surface(
    relative: str,
    text: str,
    parent: CommandSource | None = None,
    discovery_files: Collection[str] | None = None,
) -> WorkflowCommandScan:
    """Extract actual command surfaces using repository-owned static parsers."""
    suffix = Path(relative).suffix.casefold()
    if relative.startswith(".github/workflows/") and suffix in {".yml", ".yaml"}:
        scan = github_workflow_command_scan(relative, text)
        if discovery_files is not None:
            unresolved = [
                f"local composite action reference is unresolved at {relative}: {reference}"
                for reference in scan.local_action_references
                if not local_reference_resolves(reference, set(discovery_files))
            ]
            if unresolved:
                scan = WorkflowCommandScan(scan.commands, (*scan.issues, *unresolved), scan.local_action_references)
        return scan
    if Path(relative).name in {"action.yml", "action.yaml"}:
        scoped, scan_issues, nested_references = composite_action_invocations(text, relative)
        unresolved = [
            f"local composite action reference is unresolved at {relative}: {reference}"
            for reference in nested_references
            if discovery_files is None or not local_reference_resolves(reference, set(discovery_files))
        ]
        context = parent.checkout_context if parent is not None else None
        return WorkflowCommandScan(
            tuple(
                CommandSource(
                    relative,
                    cwd,
                    command,
                    command_origin(relative, text, command),
                    context,
                    pythonpath if pythonpath is not None else (parent.pythonpath if parent is not None else None),
                )
                for command, cwd, pythonpath in scoped
            ),
            tuple(sorted({*scan_issues, *unresolved})),
        )
    if suffix == ".py":
        commands = _extract_python_invocations(text)
    elif suffix in {".sh", ".ps1"} or Path(relative).name in WELL_KNOWN_TASK_RUNNERS:
        commands = _extract_gate_invocations(relative, text)
    elif suffix in {".yml", ".yaml"} or Path(relative).name.casefold() == "jenkinsfile":
        commands = _extract_gate_invocations(relative, text)
    elif Path(relative).name == "package.json":
        commands = public_task_invocations(relative, text) | _package_script_commands(text)
    else:
        commands = public_task_invocations(relative, text)
    return WorkflowCommandScan(
        tuple(
            CommandSource(
                relative,
                parent.working_directory if parent is not None else ".",
                command,
                command_origin(relative, text, command),
                parent.checkout_context if parent is not None else None,
                parent.pythonpath if parent is not None else None,
            )
            for command in sorted(commands)
        ),
        (),
    )


def _effective_pythonpath(source: CommandSource) -> str | None:
    try:
        tokens = shlex.split(source.command, posix=True)
    except ValueError:
        return source.pythonpath
    assignments = [token.partition("=")[2] for token in tokens if token.startswith("PYTHONPATH=")]
    return assignments[-1] if assignments else source.pythonpath


def collect_task_references(root: Path, discovery: Discovery) -> TaskSourceScan:
    """Collect bounded task references and merge equivalent execution-context scans."""
    references: dict[str, set[str]] = {}
    module_invocations: dict[str, list[ModuleInvocation]] = {}
    unresolved_module_candidates: dict[str, set[str]] = {}
    direct_python: dict[str, list[ModuleInvocation]] = {}
    package_initializers: dict[str, list[ModuleInvocation]] = {}
    external_sources: dict[str, set[str]] = {}
    issues: list[str] = []
    pending: deque[tuple[str, int, CommandSource | None]] = deque(
        (surface, 0, None) for surface in sorted(public_task_surfaces(discovery))
    )
    scanned: set[tuple[str, tuple[str, CheckoutContext | None, str | None] | None]] = set()
    discovered_files = set(discovery.files)

    while pending:
        relative, depth, parent = pending.popleft()
        scan_context: tuple[str, CheckoutContext | None, str | None] | None = None
        if parent is not None:
            checkout_context = parent.checkout_context
            if checkout_context is not None:
                checkout_context = replace(checkout_context, step_index=0)
            scan_context = (parent.working_directory, checkout_context, parent.pythonpath)
        scan_key = (relative, scan_context)
        if scan_key in scanned:
            continue
        if len(scanned) >= MAX_RELATED_SOURCE_FILES:
            issues.append(
                f"task-wrapper scan exceeds {MAX_RELATED_SOURCE_FILES} files; "
                f"next source {relative!r} remains unclassified"
            )
            break
        scanned.add(scan_key)
        try:
            text = read_bounded(root, relative)
        except (OSError, UnicodeError, ValueError) as error:
            issues.append(f"cannot inspect task source {relative!r}: {error}")
            continue
        command_scan = _commands_from_surface(relative, text, parent, discovery.files)
        issues.extend(command_scan.issues)
        for command_source in command_scan.commands:
            origin = command_source.origin
            raw_candidates = {match.group("path") for match in COMMAND_PATH_REFERENCE.finditer(command_source.command)}
            for raw_path in sorted(raw_candidates):
                candidate, external_path, checkout_issue = resolve_checkout_source_path(command_source, raw_path)
                if checkout_issue is not None:
                    issues.append(checkout_issue)
                    continue
                if external_path is not None:
                    external_sources.setdefault(external_path, set()).add(origin)
                    continue
                if candidate is None:
                    issues.append(f"task path ownership is unresolved at {origin}: {raw_path}")
                    continue
                raw_candidate = raw_path.removeprefix("./")
                suffix = Path(raw_candidate).suffix.casefold()
                source_like = suffix in {".py", ".sh", ".ps1", ".rb"} or candidate.startswith(
                    ("scripts/", "bin/", "tools/", ".agents/tools/")
                )
                if not source_like:
                    continue
                if candidate == ".." or candidate.startswith("../") or candidate.startswith("/"):
                    issues.append(f"task path escapes repository without a pinned external checkout at {origin}")
                    continue
                if candidate not in discovered_files:
                    issues.append(f"referenced task path not found in repository at {origin}: {raw_candidate}")
                    continue
                references.setdefault(candidate, set()).add(origin)
                if suffix == ".py":
                    roots, pythonpath_issue = invocation_roots_for_script(candidate, command_source, root)
                    if pythonpath_issue is not None:
                        issues.append(pythonpath_issue)
                    module_name = next(
                        (found for prefix in roots if (found := module_name_for_path(candidate, prefix.path))),
                        Path(candidate).stem,
                    )
                    direct_python.setdefault(candidate, []).append(
                        ModuleInvocation(
                            candidate,
                            module_name,
                            roots,
                            origin,
                            command_source.working_directory,
                            command_source.checkout_context,
                        )
                    )
                    if depth < MAX_WRAPPER_DEPTH:
                        pending.append(
                            (
                                candidate,
                                depth + 1,
                                replace(command_source, pythonpath=_effective_pythonpath(command_source)),
                            )
                        )
                    else:
                        issues.append(
                            f"Python task-source depth exceeds {MAX_WRAPPER_DEPTH} at {origin} -> {candidate}"
                        )
                if suffix in {".sh", ".ps1"}:
                    if depth < MAX_WRAPPER_DEPTH:
                        pending.append(
                            (
                                candidate,
                                depth + 1,
                                replace(command_source, pythonpath=_effective_pythonpath(command_source)),
                            )
                        )
                    else:
                        issues.append(f"wrapper depth exceeds {MAX_WRAPPER_DEPTH} at {origin} -> {candidate}")

            (
                module_references,
                module_initializers,
                module_issues,
                possible_module_paths,
                external_module_sources,
            ) = module_invocation_references(command_source, discovery)
            issues.extend(module_issues)
            for candidate in possible_module_paths:
                unresolved_module_candidates.setdefault(candidate, set()).add(command_source.origin)
            for candidate, origins in external_module_sources.items():
                external_sources.setdefault(candidate, set()).update(origins)
            for candidate, invocations in module_initializers.items():
                package_initializers.setdefault(candidate, []).extend(invocations)
            for candidate, invocations in module_references.items():
                references.setdefault(candidate, set()).update(invocation.origin for invocation in invocations)
                module_invocations.setdefault(candidate, []).extend(invocations)
                if depth < MAX_WRAPPER_DEPTH:
                    pending.append(
                        (
                            candidate,
                            depth + 1,
                            replace(command_source, pythonpath=_effective_pythonpath(command_source)),
                        )
                    )
                else:
                    issues.append(
                        f"module wrapper depth exceeds {MAX_WRAPPER_DEPTH} at {command_source.origin} -> {candidate}"
                    )

    return TaskSourceScan(
        references={path: tuple(sorted(origins)) for path, origins in references.items()},
        module_invocations={path: tuple(values) for path, values in module_invocations.items()},
        unresolved_module_candidates={
            path: tuple(sorted(origins)) for path, origins in unresolved_module_candidates.items()
        },
        direct_python={path: tuple(values) for path, values in direct_python.items()},
        package_initializers={path: tuple(values) for path, values in package_initializers.items()},
        external_sources={path: tuple(sorted(origins)) for path, origins in external_sources.items()},
        issues=tuple(sorted(set(issues))),
    )

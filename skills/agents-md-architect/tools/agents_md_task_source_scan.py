"""Discover bounded, source-qualified CI and task invocation provenance."""

from __future__ import annotations

import posixpath
from collections import deque
from pathlib import Path

from agents_md_checkout_sources import (
    external_checkout_path,
    normalize_checkout_working_directory,
    pinned_external_checkout_aliases,
    same_repository_checkout_aliases,
)
from agents_md_completion_evidence import public_task_invocations
from agents_md_python_evidence import _extract_python_invocations
from agents_md_python_modules import (
    invocation_roots_for_script,
    module_invocation_references,
    module_name_for_path,
)
from agents_md_shell_evidence import _extract_gate_invocations, _extract_yaml_command_evidence
from agents_md_source_io import command_origin, public_task_surfaces, read_bounded
from agents_md_source_types import (
    COMMAND_PATH_REFERENCE,
    MAX_RELATED_SOURCE_FILES,
    MAX_WRAPPER_DEPTH,
    WELL_KNOWN_TASK_RUNNERS,
    CommandSource,
    ModuleInvocation,
    TaskSourceScan,
)
from discover_repository import Discovery


def _commands_from_surface(relative: str, text: str) -> tuple[CommandSource, ...]:
    """Extract actual command surfaces using repository-owned static parsers."""
    suffix = Path(relative).suffix.casefold()
    if relative.startswith(".github/workflows/") and suffix in {".yml", ".yaml"}:
        aliases = same_repository_checkout_aliases(relative, text)
        return tuple(
            CommandSource(
                relative,
                normalize_checkout_working_directory(working_directory, aliases),
                command,
                command_origin(relative, text, command),
            )
            for working_directory, command in sorted(_extract_yaml_command_evidence(relative, text))
        )
    if suffix == ".py":
        commands = _extract_python_invocations(text)
    elif suffix in {".sh", ".ps1"} or Path(relative).name in WELL_KNOWN_TASK_RUNNERS:
        commands = _extract_gate_invocations(relative, text)
    else:
        commands = public_task_invocations(relative, text)
    return tuple(
        CommandSource(relative, ".", command, command_origin(relative, text, command)) for command in sorted(commands)
    )


def collect_task_references(root: Path, discovery: Discovery) -> TaskSourceScan:
    references: dict[str, set[str]] = {}
    module_invocations: dict[str, list[ModuleInvocation]] = {}
    direct_python: dict[str, list[ModuleInvocation]] = {}
    package_initializers: dict[str, list[ModuleInvocation]] = {}
    external_sources: dict[str, set[str]] = {}
    issues: list[str] = []
    pending = deque((surface, 0) for surface in sorted(public_task_surfaces(discovery)))
    scanned: set[str] = set()
    discovered_files = set(discovery.files)

    while pending:
        relative, depth = pending.popleft()
        if relative in scanned:
            continue
        if len(scanned) >= MAX_RELATED_SOURCE_FILES:
            issues.append(
                f"task-wrapper scan exceeds {MAX_RELATED_SOURCE_FILES} files; "
                f"next source {relative!r} remains unclassified"
            )
            break
        scanned.add(relative)
        try:
            text = read_bounded(root, relative)
        except (OSError, UnicodeError, ValueError) as error:
            issues.append(f"cannot inspect task source {relative!r}: {error}")
            continue
        external_checkouts, checkout_issues = pinned_external_checkout_aliases(relative, text)
        issues.extend(checkout_issues)

        for command_source in _commands_from_surface(relative, text):
            origin = command_source.origin
            for match in COMMAND_PATH_REFERENCE.finditer(command_source.command):
                raw_candidate = match.group("path").removeprefix("./")
                candidate = posixpath.normpath(posixpath.join(command_source.working_directory, raw_candidate))
                if candidate == ".." or candidate.startswith("../") or candidate.startswith("/"):
                    external_alias = next(
                        (alias for alias in external_checkouts if candidate.startswith(f"../{alias}/")),
                        None,
                    )
                    if external_alias is not None:
                        checkout = external_checkouts[external_alias]
                        suffix = candidate[len(f"../{external_alias}/") :]
                        external_path = external_checkout_path(checkout, external_alias, suffix)
                        external_sources.setdefault(external_path, set()).add(origin)
                    else:
                        issues.append(f"task path escapes repository without a pinned external checkout at {origin}")
                    continue
                if candidate not in discovered_files:
                    external_alias = next(
                        (alias for alias in external_checkouts if candidate.startswith(f"{alias}/")),
                        None,
                    )
                    if external_alias is not None:
                        checkout = external_checkouts[external_alias]
                        suffix = candidate[len(f"{external_alias}/") :]
                        external_path = external_checkout_path(checkout, external_alias, suffix)
                        external_sources.setdefault(external_path, set()).add(origin)
                    continue
                references.setdefault(candidate, set()).add(origin)
                if Path(candidate).suffix.casefold() == ".py":
                    roots = invocation_roots_for_script(candidate, command_source)
                    module_name = next(
                        (found for prefix in roots if (found := module_name_for_path(candidate, prefix))),
                        Path(candidate).stem,
                    )
                    direct_python.setdefault(candidate, []).append(
                        ModuleInvocation(candidate, module_name, roots, origin)
                    )
                if Path(candidate).suffix.casefold() in {".sh", ".ps1"}:
                    if depth < MAX_WRAPPER_DEPTH:
                        pending.append((candidate, depth + 1))
                    else:
                        issues.append(f"wrapper depth exceeds {MAX_WRAPPER_DEPTH} at {origin} -> {candidate}")

            module_references, module_initializers, module_issues = module_invocation_references(
                command_source, discovery
            )
            issues.extend(module_issues)
            for candidate, invocations in module_initializers.items():
                package_initializers.setdefault(candidate, []).extend(invocations)
            for candidate, invocations in module_references.items():
                references.setdefault(candidate, set()).update(invocation.origin for invocation in invocations)
                module_invocations.setdefault(candidate, []).extend(invocations)
                if depth < MAX_WRAPPER_DEPTH:
                    pending.append((candidate, depth + 1))
                else:
                    issues.append(
                        f"module wrapper depth exceeds {MAX_WRAPPER_DEPTH} at {command_source.origin} -> {candidate}"
                    )

    return TaskSourceScan(
        references={path: tuple(sorted(origins)) for path, origins in references.items()},
        module_invocations={path: tuple(values) for path, values in module_invocations.items()},
        direct_python={path: tuple(values) for path, values in direct_python.items()},
        package_initializers={path: tuple(values) for path, values in package_initializers.items()},
        external_sources={path: tuple(sorted(origins)) for path, origins in external_sources.items()},
        issues=tuple(sorted(set(issues))),
    )

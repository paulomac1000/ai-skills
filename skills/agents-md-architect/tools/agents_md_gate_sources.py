#!/usr/bin/env python3
"""Classify repository CI/task sources for AGENTS.md audit budgets."""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import posixpath
import re
import shlex
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, assert_never

import yaml
from agents_md_completion_evidence import public_task_invocations
from agents_md_python_evidence import _extract_python_invocations
from agents_md_shell_evidence import (
    _extract_gate_invocations,
    _extract_yaml_command_evidence,
)
from agents_md_types import MAX_GATE_FILES
from discover_repository import Discovery, discover

Classification = Literal["ci_entrypoint", "task_entrypoint", "helper", "library", "generated", "excluded"]
ExternalCheckoutKind = Literal[
    "pinned_revision",
    "trusted_lock",
    "candidate_input",
    "workflow_authority",
]

GATE_SOURCE_POLICY_REVISION = "agents-md-gate-sources-4"
MAIN_GUARD = re.compile(r"""(?m)^\s*if\s+__name__\s*==\s*['"]__main__['"]\s*:""")
COMMAND_PATH_REFERENCE = re.compile(
    r"""(?:(?:python(?:3)?|bash|sh|pwsh|powershell)\s+|\./)"""
    r"""(?P<path>[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+(?:\.(?:py|sh|ps1|rb))?)"""
)
MAX_CLASSIFIER_FILE_BYTES = 2 * 1024 * 1024
MAX_WRAPPER_DEPTH = 4
MAX_IMPORT_DEPTH = 4
MAX_RELATED_SOURCE_FILES = 256

WELL_KNOWN_TASK_RUNNERS = {
    "Makefile",
    "makefile",
    "Justfile",
    "justfile",
    "Taskfile.yml",
    "Taskfile.yaml",
    "build.sh",
    "build.ps1",
}


@dataclass(frozen=True)
class GateSource:
    path: str
    classification: Classification
    counted: bool
    reason: str
    origins: tuple[str, ...] = ()


@dataclass(frozen=True)
class GateSourceInventory:
    policy_revision: str
    limit: int
    count: int
    headroom: int
    sources: tuple[GateSource, ...]
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModuleInvocation:
    path: str
    module: str
    import_roots: tuple[str, ...]
    origin: str


@dataclass(frozen=True)
class ExternalCheckout:
    repository: str
    revision: str
    kind: ExternalCheckoutKind


@dataclass(frozen=True)
class CommandSource:
    path: str
    working_directory: str
    command: str
    origin: str


@dataclass(frozen=True)
class TaskSourceScan:
    references: dict[str, tuple[str, ...]]
    module_invocations: dict[str, tuple[ModuleInvocation, ...]]
    direct_python: dict[str, tuple[ModuleInvocation, ...]]
    package_initializers: dict[str, tuple[ModuleInvocation, ...]]
    external_sources: dict[str, tuple[str, ...]]
    issues: tuple[str, ...]


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


def _public_task_surfaces(discovery: Discovery) -> set[str]:
    surfaces = set(discovery.ci_files)
    surfaces.update(path for path in discovery.task_runners if Path(path).name in WELL_KNOWN_TASK_RUNNERS)
    surfaces.update(path for path in discovery.manifests if Path(path).name in {"package.json", "pyproject.toml"})
    return surfaces


def _command_origin(relative: str, text: str, command: str) -> str:
    for line_number, line in enumerate(text.splitlines(), start=1):
        if command.strip() and command.strip() in line:
            return f"{relative}:{line_number}"
    return relative


def _same_repository_checkout_aliases(relative: str, text: str) -> tuple[str, ...]:
    """Return checkout paths that statically denote this repository revision."""
    if Path(relative).suffix.casefold() not in {".yml", ".yaml"}:
        return ()
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError:
        return ()
    jobs = document.get("jobs") if isinstance(document, dict) else None
    if not isinstance(jobs, dict):
        return ()
    aliases: set[str] = set()
    for job in jobs.values():
        steps = job.get("steps") if isinstance(job, dict) else None
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            uses = step.get("uses")
            if not isinstance(uses, str) or uses.split("@", 1)[0] != "actions/checkout":
                continue
            options = step.get("with")
            if not isinstance(options, dict):
                continue
            repository = options.get("repository")
            if repository not in (None, "", "${{ github.repository }}"):
                continue
            reference = options.get("ref")
            if reference not in (
                None,
                "",
                "${{ github.event.pull_request.head.sha }}",
            ):
                continue
            path = options.get("path")
            if not isinstance(path, str) or not path.strip():
                continue
            normalized = posixpath.normpath(path.strip())
            if (
                normalized != "."
                and not posixpath.isabs(normalized)
                and normalized != ".."
                and not normalized.startswith("../")
            ):
                aliases.add(normalized)
    return tuple(sorted(aliases))


def _pinned_external_checkout_aliases(relative: str, text: str) -> tuple[dict[str, ExternalCheckout], tuple[str, ...]]:
    """Identify sibling checkouts with immutable or explicitly recognized identities."""
    if Path(relative).suffix.casefold() not in {".yml", ".yaml"}:
        return {}, ()
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError:
        return {}, ()
    jobs = document.get("jobs") if isinstance(document, dict) else None
    if not isinstance(jobs, dict):
        return {}, ()
    aliases: dict[str, ExternalCheckout] = {}
    issues: list[str] = []
    for job in jobs.values():
        steps = job.get("steps") if isinstance(job, dict) else None
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            uses = step.get("uses")
            if not isinstance(uses, str) or uses.split("@", 1)[0] != "actions/checkout":
                continue
            options = step.get("with")
            if not isinstance(options, dict):
                continue
            repository = options.get("repository")
            path = options.get("path")
            if (
                not isinstance(repository, str)
                or not repository.strip()
                or repository == "${{ github.repository }}"
                or not isinstance(path, str)
                or not path.strip()
            ):
                continue
            alias = posixpath.normpath(path.strip())
            if alias in {".", ".."} or alias.startswith("../") or posixpath.isabs(alias):
                issues.append(f"external checkout alias is unsafe in {relative}: {path!r}")
                continue
            reference = options.get("ref")
            dynamic_trust_lock = (
                repository == "${{ steps.authority.outputs.repository }}"
                and reference == "${{ steps.authority.outputs.revision }}"
            )
            workflow_authority = (
                repository == "${{ job.workflow_repository }}" and reference == "${{ job.workflow_sha }}"
            )
            candidate_input = (
                repository == "${{ inputs.candidate_repository }}" and reference == "${{ inputs.candidate_sha }}"
            )
            if not isinstance(reference, str):
                issues.append(f"external checkout reference is missing in {relative}: {alias!r}")
                continue
            if re.fullmatch(r"[0-9a-f]{40}", reference):
                kind: ExternalCheckoutKind = "pinned_revision"
            elif dynamic_trust_lock:
                kind = "trusted_lock"
            elif workflow_authority:
                kind = "workflow_authority"
            elif candidate_input:
                kind = "candidate_input"
            else:
                issues.append(
                    f"external checkout {repository!r} at path {alias!r} in {relative} "
                    "must pin an immutable full commit SHA or use a recognized "
                    "authority/candidate identity pair"
                )
                continue
            target = ExternalCheckout(repository, reference, kind)
            existing = aliases.get(alias)
            if existing is not None and existing != target:
                issues.append(f"external checkout alias {alias!r} is ambiguous in {relative}")
                continue
            aliases[alias] = target
    return aliases, tuple(sorted(set(issues)))


def _external_checkout_path(checkout: ExternalCheckout, alias: str, suffix: str) -> str:
    match checkout.kind:
        case "pinned_revision":
            identity = f"{checkout.repository}@{checkout.revision}"
        case "trusted_lock":
            identity = f"trusted-lock:{alias}"
        case "candidate_input":
            identity = f"candidate-input:{alias}"
        case "workflow_authority":
            identity = f"workflow-authority:{alias}"
        case unreachable:
            assert_never(unreachable)
    return f"external:{identity}/{suffix}"


def _normalize_checkout_working_directory(working_directory: str, aliases: tuple[str, ...]) -> str:
    normalized = posixpath.normpath(working_directory or ".")
    for alias in aliases:
        if normalized == alias:
            return "."
        if normalized.startswith(f"{alias}/"):
            return normalized[len(alias) + 1 :]
    return normalized


def _commands_from_surface(relative: str, text: str) -> tuple[CommandSource, ...]:
    """Extract actual command surfaces using the repository's static parsers."""
    suffix = Path(relative).suffix.casefold()
    if relative.startswith(".github/workflows/") and suffix in {".yml", ".yaml"}:
        aliases = _same_repository_checkout_aliases(relative, text)
        return tuple(
            CommandSource(
                relative,
                _normalize_checkout_working_directory(working_directory, aliases),
                command,
                _command_origin(relative, text, command),
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
        CommandSource(relative, ".", command, _command_origin(relative, text, command)) for command in sorted(commands)
    )


def _pythonpath_roots(tokens: list[str], default: tuple[str, ...]) -> tuple[str, ...]:
    roots: list[str] = list(default)
    for token in tokens:
        if not token.startswith("PYTHONPATH="):
            continue
        for raw_prefix in token.split("=", 1)[1].split(":"):
            prefix = raw_prefix.strip()
            if not prefix or prefix == ".":
                roots.extend(default)
                continue
            if "$" in prefix or posixpath.isabs(prefix):
                continue
            normalized = posixpath.normpath(posixpath.join(default[0], prefix))
            if normalized == ".." or normalized.startswith("../"):
                continue
            roots.append(normalized)
    return tuple(dict.fromkeys(roots or list(default)))


def _resolve_module_paths(
    module: str, roots: tuple[str, ...], discovered_files: set[str]
) -> tuple[tuple[str, str], ...]:
    relative_module = module.replace(".", "/")
    matches: dict[str, str] = {}
    for root in roots:
        base = posixpath.normpath(posixpath.join(root, relative_module))
        if base == ".." or base.startswith("../") or base.startswith("/"):
            continue
        for candidate, module_name in (
            (f"{base}.py", module),
            (f"{base}/__init__.py", module),
        ):
            if candidate in discovered_files:
                matches[candidate] = module_name
    return tuple(sorted(matches.items()))


def _module_invocation_references(
    source: CommandSource, discovery: Discovery
) -> tuple[
    dict[str, tuple[ModuleInvocation, ...]],
    dict[str, tuple[ModuleInvocation, ...]],
    tuple[str, ...],
]:
    """Resolve static Python module invocations without executing source."""
    references: dict[str, list[ModuleInvocation]] = {}
    package_initializers: dict[str, list[ModuleInvocation]] = {}
    issues: list[str] = []
    discovered_files = set(discovery.files)
    try:
        tokens = shlex.split(source.command, posix=True)
    except ValueError:
        if "-m" in source.command:
            issues.append(f"unparseable module invocation at {source.origin}")
        return {}, {}, tuple(issues)
    for index, token in enumerate(tokens):
        if token != "-m" or index == 0 or index + 1 >= len(tokens):
            continue
        interpreter = tokens[index - 1]
        interpreter_name = posixpath.basename(interpreter.strip("\"'"))
        variable_python = interpreter in {"$PY", "${PY}", "$PYTHON", "${PYTHON}"}
        if "python" not in interpreter_name.casefold() and not variable_python:
            continue
        module = tokens[index + 1]
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", module):
            issues.append(f"invalid Python module name at {source.origin}")
            continue
        roots = _pythonpath_roots(tokens[:index], (source.working_directory,))
        relative_module = module.replace(".", "/")
        parts = module.split(".")
        module_targets = _resolve_module_paths(module, roots, discovered_files)
        module_files = tuple(
            (path, resolved_name) for path, resolved_name in module_targets if not path.endswith("/__init__.py")
        )
        package_initializers_only = tuple(
            (path, resolved_name) for path, resolved_name in module_targets if path.endswith("/__init__.py")
        )
        package_mains: dict[str, str] = {}
        for root in roots:
            package_path = posixpath.normpath(posixpath.join(root, relative_module))
            if package_path == ".." or package_path.startswith("../") or package_path.startswith("/"):
                continue
            main_module = f"{package_path}/__main__.py"
            if main_module in discovered_files:
                package_mains[main_module] = f"{module}.__main__"

        if package_mains:
            if module_files:
                issues.append(
                    f"ambiguous module resolution for {module!r} at {source.origin}: "
                    + ", ".join(sorted({path for path, _name in (*module_files, *package_mains.items())}))
                )
            matches = tuple(sorted(package_mains.items()))
            initialized_prefixes = range(1, len(parts) + 1)
        elif module_files:
            if package_initializers_only:
                issues.append(
                    f"ambiguous module resolution for {module!r} at {source.origin}: "
                    + ", ".join(sorted({path for path, _name in (*module_files, *package_initializers_only)}))
                )
            matches = module_files
            initialized_prefixes = range(1, len(parts))
        elif package_initializers_only:
            issues.append(
                f"invoked Python package {module!r} has no executable package entrypoint "
                f"(__main__.py) at {source.origin}"
            )
            matches = ()
            initialized_prefixes = range(0)
        else:
            matches = ()
            initialized_prefixes = range(0)

        for root in roots:
            for prefix_length in initialized_prefixes:
                package_name = ".".join(parts[:prefix_length])
                package_path = posixpath.normpath(posixpath.join(root, package_name.replace(".", "/")))
                if package_path == ".." or package_path.startswith("../") or package_path.startswith("/"):
                    continue
                initializer = f"{package_path}/__init__.py"
                if initializer in discovered_files:
                    package_initializers.setdefault(initializer, []).append(
                        ModuleInvocation(
                            initializer,
                            f"{package_name}.__init__",
                            roots,
                            source.origin,
                        )
                    )
        if len(matches) > 1:
            issues.append(
                f"ambiguous module resolution for {module!r} at {source.origin}: "
                + ", ".join(path for path, _name in matches)
            )
        if not matches and module.startswith("tools."):
            issues.append(f"invoked local tools module {module!r} not found at {source.origin}")
        for candidate, resolved_name in matches:
            references.setdefault(candidate, []).append(
                ModuleInvocation(
                    candidate,
                    resolved_name,
                    roots,
                    source.origin,
                )
            )
    return (
        {path: tuple(values) for path, values in references.items()},
        {path: tuple(values) for path, values in package_initializers.items()},
        tuple(issues),
    )


def _module_name_for_path(path: str, root: str) -> str | None:
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


def _invocation_roots_for_script(path: str, source: CommandSource) -> tuple[str, ...]:
    try:
        tokens = shlex.split(source.command, posix=True)
    except ValueError:
        tokens = []
    default = (Path(path).parent.as_posix() or ".", source.working_directory)
    return _pythonpath_roots(tokens, default)


def _collect_task_references(root: Path, discovery: Discovery) -> TaskSourceScan:
    references: dict[str, set[str]] = {}
    module_invocations: dict[str, list[ModuleInvocation]] = {}
    direct_python: dict[str, list[ModuleInvocation]] = {}
    package_initializers: dict[str, list[ModuleInvocation]] = {}
    external_sources: dict[str, set[str]] = {}
    issues: list[str] = []
    pending = deque((surface, 0) for surface in sorted(_public_task_surfaces(discovery)))
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
            text = _read_bounded(root, relative)
        except (OSError, UnicodeError, ValueError) as error:
            issues.append(f"cannot inspect task source {relative!r}: {error}")
            continue
        external_checkouts, checkout_issues = _pinned_external_checkout_aliases(relative, text)
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
                        external_path = _external_checkout_path(checkout, external_alias, suffix)
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
                        external_path = _external_checkout_path(checkout, external_alias, suffix)
                        external_sources.setdefault(external_path, set()).add(origin)
                    continue
                references.setdefault(candidate, set()).add(origin)
                suffix = Path(candidate).suffix.casefold()
                if suffix == ".py":
                    roots = _invocation_roots_for_script(candidate, command_source)
                    module_name = next(
                        (found for root_prefix in roots if (found := _module_name_for_path(candidate, root_prefix))),
                        Path(candidate).stem,
                    )
                    direct_python.setdefault(candidate, []).append(
                        ModuleInvocation(candidate, module_name, roots, origin)
                    )
                if suffix in {".sh", ".ps1"}:
                    if depth < MAX_WRAPPER_DEPTH:
                        pending.append((candidate, depth + 1))
                    else:
                        issues.append(f"wrapper depth exceeds {MAX_WRAPPER_DEPTH} at {origin} -> {candidate}")

            module_references, module_initializers, module_issues = _module_invocation_references(
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


def _imported_module_names(module_name: str, text: str) -> tuple[tuple[str, int], ...]:
    """Read Python import declarations as data; never import or execute them."""
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


def _collect_imported_libraries(
    root: Path, discovery: Discovery, task_sources: TaskSourceScan
) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
    """Boundedly inventory repository imports without counting libraries as entrypoints."""
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
    for path, invocations in task_sources.package_initializers.items():
        imported_origins.setdefault(path, set()).update(invocation.origin for invocation in invocations)

    while pending:
        invocation, depth = pending.popleft()
        context_key = (invocation.path, invocation.module, invocation.import_roots)
        if context_key in visited:
            continue
        visited.add(context_key)
        if len(visited) > MAX_RELATED_SOURCE_FILES:
            issues.append(
                f"Python import inventory exceeds {MAX_RELATED_SOURCE_FILES} modules; "
                f"dependency chain at {invocation.origin} remains unclassified"
            )
            break
        if depth > MAX_IMPORT_DEPTH:
            issues.append(f"Python import depth exceeds {MAX_IMPORT_DEPTH} at {invocation.path}")
            continue
        try:
            text = _read_bounded(root, invocation.path)
            imported_modules = _imported_module_names(invocation.module, text)
        except (OSError, UnicodeError, ValueError, SyntaxError) as error:
            issues.append(f"cannot inspect imports in {invocation.path!r}: {error}")
            continue

        for module, line_number in imported_modules:
            matches: dict[str, str] = {}
            for import_root in invocation.import_roots:
                matches.update(_resolve_module_paths(module, (import_root,), discovered_files))
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
                        ModuleInvocation(
                            path,
                            resolved_module,
                            invocation.import_roots,
                            origin,
                        ),
                        depth + 1,
                    )
                )
    return (
        {path: tuple(sorted(origins)) for path, origins in imported_origins.items()},
        tuple(sorted(set(issues))),
    )


def _is_executable_shebang_script(root: Path, relative: str) -> bool:
    if not relative.startswith("scripts/"):
        return False
    path = root / relative
    try:
        if path.is_symlink() or path.stat().st_mode & 0o111 == 0:
            return False
        return _read_bounded(root, relative).startswith("#!")
    except (OSError, UnicodeError, ValueError):
        return False


def classify_gate_sources(
    root: Path,
    discovery: Discovery,
    *,
    limit: int = MAX_GATE_FILES,
    policy_revision: str = GATE_SOURCE_POLICY_REVISION,
) -> GateSourceInventory:
    """Classify entrypoints and bounded imported sources without executing them."""
    safe_root = Path(discovery.root)
    task_scan = _collect_task_references(safe_root, discovery)
    imported_libraries, import_issues = _collect_imported_libraries(safe_root, discovery, task_scan)
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

        name = path.name
        if name in WELL_KNOWN_TASK_RUNNERS:
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
        if _is_executable_shebang_script(safe_root, relative):
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

        suffix = path.suffix.casefold()
        if suffix == ".py":
            try:
                text = _read_bounded(safe_root, relative)
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

    count = sum(1 for row in rows if row.counted)
    issues = tuple(sorted(set((*task_scan.issues, *import_issues))))
    return GateSourceInventory(
        policy_revision=policy_revision,
        limit=limit,
        count=count,
        headroom=limit - count,
        sources=tuple(rows),
        issues=issues,
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
        "verdict": "pass" if inventory.count <= inventory.limit and not inventory.issues else "fail",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if inventory.count <= inventory.limit and not inventory.issues else 1


if __name__ == "__main__":
    raise SystemExit(main())

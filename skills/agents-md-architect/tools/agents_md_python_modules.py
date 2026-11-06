"""Static resolution of Python ``-m`` invocations to repository source paths."""

from __future__ import annotations

import posixpath
import re
import shlex
from pathlib import Path

from agents_md_source_types import CommandSource, ModuleInvocation
from discover_repository import Discovery


def pythonpath_roots(tokens: list[str], default: tuple[str, ...]) -> tuple[str, ...]:
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
            if normalized != ".." and not normalized.startswith("../"):
                roots.append(normalized)
    return tuple(dict.fromkeys(roots or list(default)))


def resolve_module_paths(
    module: str,
    roots: tuple[str, ...],
    discovered_files: set[str],
) -> tuple[tuple[str, str], ...]:
    relative_module = module.replace(".", "/")
    matches: dict[str, str] = {}
    for root in roots:
        base = posixpath.normpath(posixpath.join(root, relative_module))
        if base == ".." or base.startswith("../") or base.startswith("/"):
            continue
        for candidate in (f"{base}.py", f"{base}/__init__.py"):
            if candidate in discovered_files:
                matches[candidate] = module
    return tuple(sorted(matches.items()))


def module_invocation_references(
    source: CommandSource,
    discovery: Discovery,
) -> tuple[dict[str, tuple[ModuleInvocation, ...]], dict[str, tuple[ModuleInvocation, ...]], tuple[str, ...]]:
    """Resolve static module invocations without importing candidate modules."""
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
        roots = pythonpath_roots(tokens[:index], (source.working_directory,))
        relative_module = module.replace(".", "/")
        parts = module.split(".")
        module_targets = resolve_module_paths(module, roots, discovered_files)
        module_files = tuple((path, name) for path, name in module_targets if not path.endswith("/__init__.py"))
        package_initializers_only = tuple(
            (path, name) for path, name in module_targets if path.endswith("/__init__.py")
        )
        package_mains: dict[str, str] = {}
        for root in roots:
            package_path = posixpath.normpath(posixpath.join(root, relative_module))
            if package_path == ".." or package_path.startswith("../") or package_path.startswith("/"):
                continue
            main_path = f"{package_path}/__main__.py"
            if main_path in discovered_files:
                package_mains[main_path] = f"{module}.__main__"

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
                f"invoked Python package {module!r} has no executable package entrypoint (__main__.py) at {source.origin}"
            )
            matches = ()
            initialized_prefixes = range(0)
        else:
            matches = ()
            initialized_prefixes = range(0)
            if any(root != "." for root in roots):
                issues.append(
                    f"invoked module {module!r} not found under declared repository import roots at {source.origin}"
                )

        for root in roots:
            for prefix_length in initialized_prefixes:
                package_name = ".".join(parts[:prefix_length])
                package_path = posixpath.normpath(posixpath.join(root, package_name.replace(".", "/")))
                if package_path == ".." or package_path.startswith("../") or package_path.startswith("/"):
                    continue
                initializer = f"{package_path}/__init__.py"
                if initializer in discovered_files:
                    package_initializers.setdefault(initializer, []).append(
                        ModuleInvocation(initializer, f"{package_name}.__init__", roots, source.origin)
                    )
        if len(matches) > 1:
            issues.append(
                f"ambiguous module resolution for {module!r} at {source.origin}: "
                + ", ".join(path for path, _name in matches)
            )
        for candidate, resolved_name in matches:
            references.setdefault(candidate, []).append(
                ModuleInvocation(candidate, resolved_name, roots, source.origin)
            )
    return (
        {path: tuple(values) for path, values in references.items()},
        {path: tuple(values) for path, values in package_initializers.items()},
        tuple(issues),
    )


def module_name_for_path(path: str, root: str) -> str | None:
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


def invocation_roots_for_script(path: str, source: CommandSource) -> tuple[str, ...]:
    try:
        tokens = shlex.split(source.command, posix=True)
    except ValueError:
        tokens = []
    default = (Path(path).parent.as_posix() or ".", source.working_directory)
    return pythonpath_roots(tokens, default)

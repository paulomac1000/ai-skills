"""Static resolution of Python ``-m`` invocations to repository source paths."""

from __future__ import annotations

import posixpath
import re
import shlex
import sys
from pathlib import Path
from typing import Final

from agents_md_checkout_sources import (
    normalize_pythonpath_roots,
    pythonpath_roots,
    resolve_import_source_path,
)
from agents_md_source_types import CommandSource, ModuleInvocation
from discover_repository import Discovery

PYTHON_INTERPRETER = re.compile(r"^(?:python(?:\d+(?:\.\d+)*)?(?:\.exe)?|pypy(?:\d+(?:\.\d+)*)?(?:\.exe)?)$", re.I)
PYTHON_FLAGS_WITHOUT_VALUE = frozenset(
    {"-b", "-B", "-d", "-E", "-h", "-i", "-I", "-O", "-OO", "-P", "-q", "-s", "-S", "-u", "-v", "-V", "-x"}
)
PYTHON_FLAGS_WITH_VALUE = frozenset({"-W", "-X", "--check-hash-based-pycs"})
KNOWN_INSTALLED_MODULES: Final = frozenset({"pip"})


def resolve_module_paths(
    module: str,
    roots: tuple[str, ...],
    discovered_files: set[str],
) -> tuple[tuple[str, str], ...]:
    """Return discovered local module files under the declared import roots."""
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


def _has_repository_module_namespace(
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
                link == base or link.startswith(f"{base}/") or base.startswith(f"{link}/")
                for link in discovered_symlinks
            )
        ):
            return True
    return False


def module_invocation_references(
    source: CommandSource,
    discovery: Discovery,
) -> tuple[
    dict[str, tuple[ModuleInvocation, ...]],
    dict[str, tuple[ModuleInvocation, ...]],
    tuple[str, ...],
    tuple[str, ...],
    dict[str, tuple[str, ...]],
]:
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
        return {}, {}, tuple(issues), (), {}
    module_index = next((position for position, token in enumerate(tokens) if token == "-m"), None)
    if module_index is None or module_index + 1 >= len(tokens):
        return {}, {}, (), (), {}
    interpreter_index = next(
        (
            position
            for position, token in enumerate(tokens[:module_index])
            if PYTHON_INTERPRETER.fullmatch(posixpath.basename(token.replace("\\", "/").strip("\"'")))
            or token in {"$PY", "${PY}", "$PYTHON", "${PYTHON}"}
        ),
        None,
    )
    if interpreter_index is None:
        return {}, {}, (), (), {}
    options = tokens[interpreter_index + 1 : module_index]
    option_index = 0
    while option_index < len(options):
        token = options[option_index]
        if token in PYTHON_FLAGS_WITH_VALUE:
            if option_index + 1 >= len(options):
                issues.append(f"Python option {token!r} has no value before module invocation at {source.origin}")
                return {}, {}, tuple(issues), (), {}
            option_index += 2
            continue
        if token in PYTHON_FLAGS_WITHOUT_VALUE or token.startswith(("-X=", "-W=", "--check-hash-based-pycs=")):
            option_index += 1
            continue
        if token == "env" or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token):
            option_index += 1
            continue
        if not token.startswith("-"):
            return {}, {}, (), (), {}
        issues.append(
            f"unsupported Python option or wrapper token {token!r} before module invocation at {source.origin}"
        )
        return {}, {}, tuple(issues), (), {}

    module = tokens[module_index + 1]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", module):
        issues.append(f"invalid Python module name at {source.origin}")
        return {}, {}, tuple(issues), (), {}
    roots, pythonpath_issue, unresolved_roots = pythonpath_roots(
        tokens[:module_index], (source.working_directory,), source
    )
    if pythonpath_issue is not None:
        possible_paths = tuple(
            path
            for path, _name in resolve_module_paths(module, unresolved_roots, discovered_files)
            if not path.endswith("/__init__.py")
        )
        return {}, {}, (f"{pythonpath_issue} at {source.origin}",), possible_paths, {}
    roots, root_issues = normalize_pythonpath_roots(roots, Path(discovery.root), source.origin)
    issues.extend(root_issues)
    relative_module = module.replace(".", "/")
    parts = module.split(".")
    module_targets: dict[str, str] = {}
    external_sources: dict[str, set[str]] = {}
    for import_root in roots:
        for candidate, resolved_name in resolve_module_paths(module, (import_root,), discovered_files):
            path, external_path, ownership_issue = resolve_import_source_path(source, import_root, candidate)
            if ownership_issue is not None:
                issues.append(ownership_issue)
            elif external_path is not None:
                external_sources.setdefault(external_path, set()).add(source.origin)
            elif path is not None:
                module_targets[path] = resolved_name
    module_files = tuple((path, name) for path, name in module_targets.items() if not path.endswith("/__init__.py"))
    package_initializers_only = tuple(
        (path, name) for path, name in module_targets.items() if path.endswith("/__init__.py")
    )
    package_mains: dict[str, str] = {}
    for root in roots:
        package_path = posixpath.normpath(posixpath.join(root, relative_module))
        if package_path == ".." or package_path.startswith("../") or package_path.startswith("/"):
            continue
        main_path = f"{package_path}/__main__.py"
        if main_path in discovered_files:
            path, external_path, ownership_issue = resolve_import_source_path(source, root, main_path)
            if ownership_issue is not None:
                issues.append(ownership_issue)
            elif external_path is not None:
                external_sources.setdefault(external_path, set()).add(source.origin)
            elif path is not None:
                package_mains[path] = f"{module}.__main__"

    if external_sources and (package_mains or module_files or package_initializers_only):
        issues.append(
            f"ambiguous module ownership for {module!r} at {source.origin}: "
            + ", ".join((*sorted(module_targets), *sorted(external_sources)))
        )
        matches = ()
        initialized_prefixes = range(0)
    elif external_sources:
        matches = ()
        initialized_prefixes = range(0)
    elif package_mains:
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
        local_namespace = _has_repository_module_namespace(module, roots, discovered_files, discovery.symlinks)
        known_external_module = module.split(".", 1)[0] in sys.stdlib_module_names | KNOWN_INSTALLED_MODULES
        if (
            not external_sources
            and (any(root != "." for root in roots) or local_namespace)
            and (not known_external_module or local_namespace)
        ):
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
                path, external_path, ownership_issue = resolve_import_source_path(source, root, initializer)
                if ownership_issue is not None:
                    issues.append(ownership_issue)
                elif external_path is not None:
                    external_sources.setdefault(external_path, set()).add(source.origin)
                elif path is not None:
                    package_initializers.setdefault(path, []).append(
                        ModuleInvocation(path, f"{package_name}.__init__", roots, source.origin)
                    )
    if len(matches) > 1:
        issues.append(
            f"ambiguous module resolution for {module!r} at {source.origin}: "
            + ", ".join(path for path, _name in matches)
        )
    for candidate, resolved_name in matches:
        references.setdefault(candidate, []).append(ModuleInvocation(candidate, resolved_name, roots, source.origin))
    return (
        {path: tuple(values) for path, values in references.items()},
        {path: tuple(values) for path, values in package_initializers.items()},
        tuple(issues),
        (),
        {path: tuple(sorted(origins)) for path, origins in external_sources.items()},
    )

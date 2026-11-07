"""Static resolution of Python ``-m`` invocations to repository source paths."""

from __future__ import annotations

import posixpath
import re
import shlex
from pathlib import Path

from agents_md_source_types import CommandSource, ModuleInvocation
from discover_repository import Discovery

PYTHON_INTERPRETER = re.compile(r"^(?:python(?:\d+(?:\.\d+)*)?(?:\.exe)?|pypy(?:\d+(?:\.\d+)*)?(?:\.exe)?)$", re.I)
PYTHON_FLAGS_WITHOUT_VALUE = frozenset(
    {"-b", "-B", "-d", "-E", "-h", "-i", "-I", "-O", "-OO", "-P", "-q", "-s", "-S", "-u", "-v", "-V", "-x"}
)
PYTHON_FLAGS_WITH_VALUE = frozenset({"-W", "-X", "--check-hash-based-pycs"})


def pythonpath_roots(
    tokens: list[str], default: tuple[str, ...], source: CommandSource
) -> tuple[tuple[str, ...], str | None, tuple[str, ...]]:
    """Resolve static import roots from command assignments and workflow environment."""
    assignments = [token.partition("=")[2] for token in tokens if token.startswith("PYTHONPATH=")]
    value = assignments[-1] if assignments else source.pythonpath
    roots: list[str] = []
    if value is None:
        return default, None, ()

    unresolved_roots: list[str] = []

    for raw_prefix in value.split(":"):
        prefix = raw_prefix.strip()
        pythonpath_base = default[-1]
        unresolved_variable = re.match(r"^\$[A-Za-z_][A-Za-z0-9_]*(?:/|$)", prefix)
        if re.match(r"^\$PWD(?:/|$)", prefix):
            prefix = prefix.removeprefix("$PWD").removeprefix("/")
        elif re.match(r"^\$\{PWD\}(?:/|$)", prefix):
            prefix = prefix.removeprefix("${PWD}").removeprefix("/")
        elif re.match(r"^\$GITHUB_WORKSPACE(?:/|$)", prefix):
            aliases = dict(source.checkout_context.aliases) if source.checkout_context is not None else {}
            if aliases.get(".") is not None or "." not in aliases:
                return (), f"PYTHONPATH workspace root is unresolved at {value!r}", ()
            prefix = prefix.removeprefix("$GITHUB_WORKSPACE").removeprefix("/")
            pythonpath_base = "."
        if "$" in prefix or "${{" in prefix:
            if unresolved_variable is not None:
                suffix = raw_prefix[unresolved_variable.end() :].lstrip("/")
                if suffix:
                    possible_root = posixpath.normpath(posixpath.join(pythonpath_base, suffix))
                    if possible_root != ".." and not possible_root.startswith("../"):
                        unresolved_roots.append(possible_root)
            return (), f"PYTHONPATH is unresolved at {value!r}", tuple(dict.fromkeys(unresolved_roots))
        if not prefix or prefix == ".":
            roots.extend(default)
            continue
        if posixpath.isabs(prefix):
            continue
        normalized = posixpath.normpath(posixpath.join(pythonpath_base, prefix))
        if normalized == ".." or normalized.startswith("../"):
            return (), f"PYTHONPATH escapes the repository at {value!r}", ()
        roots.append(normalized)

    roots.extend(default)
    return tuple(dict.fromkeys(roots)), None, ()


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
        return {}, {}, tuple(issues), ()
    module_index = next((position for position, token in enumerate(tokens) if token == "-m"), None)
    if module_index is None or module_index + 1 >= len(tokens):
        return {}, {}, (), ()
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
        return {}, {}, (), ()
    options = tokens[interpreter_index + 1 : module_index]
    option_index = 0
    while option_index < len(options):
        token = options[option_index]
        if token in PYTHON_FLAGS_WITH_VALUE:
            if option_index + 1 >= len(options):
                issues.append(f"Python option {token!r} has no value before module invocation at {source.origin}")
                return {}, {}, tuple(issues), ()
            option_index += 2
            continue
        if token in PYTHON_FLAGS_WITHOUT_VALUE or token.startswith(("-X=", "-W=", "--check-hash-based-pycs=")):
            option_index += 1
            continue
        if token == "env" or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token):
            option_index += 1
            continue
        if not token.startswith("-"):
            return {}, {}, (), ()
        issues.append(
            f"unsupported Python option or wrapper token {token!r} before module invocation at {source.origin}"
        )
        return {}, {}, tuple(issues), ()

    module = tokens[module_index + 1]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", module):
        issues.append(f"invalid Python module name at {source.origin}")
        return {}, {}, tuple(issues), ()
    roots, pythonpath_issue, unresolved_roots = pythonpath_roots(
        tokens[:module_index], (source.working_directory,), source
    )
    if pythonpath_issue is not None:
        possible_paths = tuple(
            path
            for path, _name in resolve_module_paths(module, unresolved_roots, discovered_files)
            if not path.endswith("/__init__.py")
        )
        return {}, {}, (f"{pythonpath_issue} at {source.origin}",), possible_paths
    relative_module = module.replace(".", "/")
    parts = module.split(".")
    module_targets = resolve_module_paths(module, roots, discovered_files)
    module_files = tuple((path, name) for path, name in module_targets if not path.endswith("/__init__.py"))
    package_initializers_only = tuple((path, name) for path, name in module_targets if path.endswith("/__init__.py"))
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
        if any(root != "." for root in roots) or _has_repository_module_namespace(
            module, roots, discovered_files, discovery.symlinks
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
                package_initializers.setdefault(initializer, []).append(
                    ModuleInvocation(initializer, f"{package_name}.__init__", roots, source.origin)
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
    )


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


def invocation_roots_for_script(path: str, source: CommandSource) -> tuple[tuple[str, ...], str | None]:
    """Resolve direct-script import roots and preserve unresolved PYTHONPATH evidence."""
    try:
        tokens = shlex.split(source.command, posix=True)
    except ValueError:
        tokens = []
    default = (Path(path).parent.as_posix() or ".", source.working_directory)
    roots, issue, _unresolved_roots = pythonpath_roots(tokens, default, source)
    if issue is not None:
        return roots, f"{issue} at {source.origin}"
    return roots, None

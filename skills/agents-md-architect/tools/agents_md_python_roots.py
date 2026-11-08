"""Static PYTHONPATH root resolution with explicit workspace/candidate frames."""

from __future__ import annotations

import ntpath
import posixpath
import re
import shlex
from pathlib import Path

from agents_md_source_types import CommandSource, ImportRoot


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


def pythonpath_roots(
    tokens: list[str], default: tuple[str, ...], source: CommandSource
) -> tuple[tuple[ImportRoot, ...], str | None, tuple[str, ...]]:
    """Resolve static import roots with the frame each root's paths are expressed in."""
    assignments = [token.partition("=")[2] for token in tokens if token.startswith("PYTHONPATH=")]
    value = assignments[-1] if assignments else source.pythonpath
    if value is None:
        return tuple(ImportRoot(root) for root in dict.fromkeys(default)), None, ()

    roots: dict[tuple[str, bool], ImportRoot] = {}
    unresolved_roots: list[str] = []

    prefixes: list[str] = []
    start = 0
    for index, character in enumerate(value):
        drive_colon = index == start + 1 and value[start].isalpha()
        if character == ";" or (character == ":" and not drive_colon):
            prefixes.append(value[start:index])
            start = index + 1
    prefixes.append(value[start:])

    for raw_prefix in prefixes:
        prefix = raw_prefix.strip()
        pythonpath_base = default[-1]
        workspace_root = False
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
            workspace_root = True
        if "$" in prefix or "${{" in prefix:
            if unresolved_variable is not None:
                suffix = raw_prefix[unresolved_variable.end() :].lstrip("/")
                if suffix:
                    possible_root = posixpath.normpath(posixpath.join(pythonpath_base, suffix))
                    if possible_root != ".." and not possible_root.startswith("../"):
                        unresolved_roots.append(possible_root)
            return (), f"PYTHONPATH is unresolved at {value!r}", tuple(dict.fromkeys(unresolved_roots))
        if not prefix or prefix == ".":
            if workspace_root:
                roots[(pythonpath_base, True)] = ImportRoot(pythonpath_base, True)
            else:
                for root in default:
                    roots[(root, False)] = ImportRoot(root)
            continue
        if Path(prefix).is_absolute() or ntpath.isabs(prefix):
            roots[(prefix, True)] = ImportRoot(prefix, True)
            continue
        normalized = posixpath.normpath(posixpath.join(pythonpath_base, prefix))
        if normalized == ".." or normalized.startswith("../"):
            return (), f"PYTHONPATH escapes the repository at {value!r}", ()
        roots[(normalized, workspace_root)] = ImportRoot(normalized, workspace_root)

    for root in default:
        roots.setdefault((root, False), ImportRoot(root))
    return tuple(roots.values()), None, ()


def normalize_pythonpath_roots(
    roots: tuple[ImportRoot, ...], repository_root: Path, origin: str
) -> tuple[tuple[ImportRoot, ...], tuple[str, ...]]:
    """Resolve absolute import roots against the actual checkout without prefix matching."""
    checkout_root = repository_root.resolve()
    normalized: dict[tuple[str, bool], ImportRoot] = {}
    issues: list[str] = []
    for root in roots:
        if not Path(root.path).is_absolute():
            if ntpath.isabs(root.path):
                issues.append(f"absolute PYTHONPATH root uses an unresolvable path form at {origin}: {root.path!r}")
            else:
                normalized[(root.path, root.workspace_relative)] = root
            continue
        try:
            resolved_root = Path(root.path).resolve(strict=True)
        except (OSError, RuntimeError):
            issues.append(f"absolute PYTHONPATH root ownership is unresolved at {origin}: {root.path!r}")
            continue
        if not resolved_root.is_dir():
            issues.append(f"absolute PYTHONPATH root is not a directory at {origin}: {root.path!r}")
            continue
        try:
            relative_root = resolved_root.relative_to(checkout_root)
        except ValueError:
            continue
        repo_relative = relative_root.as_posix() or "."
        normalized[(repo_relative, True)] = ImportRoot(repo_relative, True)
    return tuple(normalized.values()), tuple(issues)


def invocation_roots_for_script(
    path: str,
    source: CommandSource,
    repository_root: Path,
) -> tuple[tuple[ImportRoot, ...], str | None]:
    """Resolve direct-script import roots and preserve unresolved PYTHONPATH evidence."""
    try:
        tokens = shlex.split(source.command, posix=True)
    except ValueError:
        tokens = []
    default = (Path(path).parent.as_posix() or ".", source.working_directory)
    roots, issue, _unresolved_roots = pythonpath_roots(tokens, default, source)
    if issue is not None:
        return roots, f"{issue} at {source.origin}"
    normalized_roots, root_issues = normalize_pythonpath_roots(roots, repository_root, source.origin)
    return normalized_roots, "; ".join(root_issues) if root_issues else None

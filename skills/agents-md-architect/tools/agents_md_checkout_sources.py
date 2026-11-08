"""Static workflow checkout identity parsing used by gate-source discovery."""

from __future__ import annotations

import ntpath
import posixpath
import re
from dataclasses import replace
from pathlib import Path

from agents_md_source_types import CommandSource, ExternalCheckout, ExternalCheckoutKind


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
) -> tuple[tuple[str, ...], str | None, tuple[str, ...]]:
    """Resolve static import roots from command assignments and workflow environment."""
    assignments = [token.partition("=")[2] for token in tokens if token.startswith("PYTHONPATH=")]
    value = assignments[-1] if assignments else source.pythonpath
    roots: list[str] = []
    if value is None:
        return default, None, ()

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
            roots.extend((pythonpath_base,) if workspace_root else default)
            continue
        if Path(prefix).is_absolute() or ntpath.isabs(prefix):
            roots.append(prefix)
            continue
        normalized = posixpath.normpath(posixpath.join(pythonpath_base, prefix))
        if normalized == ".." or normalized.startswith("../"):
            return (), f"PYTHONPATH escapes the repository at {value!r}", ()
        roots.append(normalized)

    roots.extend(default)
    return tuple(dict.fromkeys(roots)), None, ()


def normalize_pythonpath_roots(
    roots: tuple[str, ...], repository_root: Path, origin: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Resolve absolute import roots against the actual checkout without prefix matching."""
    checkout_root = repository_root.resolve()
    normalized: list[str] = []
    issues: list[str] = []
    for root in roots:
        if not Path(root).is_absolute():
            if ntpath.isabs(root):
                issues.append(f"absolute PYTHONPATH root uses an unresolvable path form at {origin}: {root!r}")
            else:
                normalized.append(root)
            continue
        try:
            resolved_root = Path(root).resolve(strict=True)
        except (OSError, RuntimeError):
            issues.append(f"absolute PYTHONPATH root ownership is unresolved at {origin}: {root!r}")
            continue
        if not resolved_root.is_dir():
            issues.append(f"absolute PYTHONPATH root is not a directory at {origin}: {root!r}")
            continue
        try:
            relative_root = resolved_root.relative_to(checkout_root)
        except ValueError:
            continue
        normalized.append(relative_root.as_posix() or ".")
    return tuple(dict.fromkeys(normalized)), tuple(issues)


def classify_checkout(
    relative: str,
    repository: str | None,
    reference: str | None,
    path: str | None,
) -> tuple[str | None, ExternalCheckout | None, str | None]:
    """Classify one checkout step without combining identity across jobs."""
    if isinstance(path, str) and "${{" in path:
        return None, None, f"checkout path is dynamic in {relative}: {path!r}"
    raw_path = path.strip() if isinstance(path, str) and path.strip() else "."
    alias = posixpath.normpath(raw_path)
    if alias == ".." or alias.startswith("../") or posixpath.isabs(alias):
        return None, None, f"checkout alias is unsafe in {relative}: {raw_path!r}"

    if repository in (None, "", "${{ github.repository }}"):
        if reference in (
            None,
            "",
            "${{ github.sha }}",
            "${{ github.event.pull_request.head.sha }}",
            "${{ github.event.pull_request.head.sha || github.sha }}",
            "${{ github.event.workflow_run.head_sha }}",
        ):
            return alias, None, None
        return (
            alias,
            None,
            f"same-repository checkout revision is unresolved in {relative}: {reference!r}",
        )

    if not isinstance(repository, str) or not repository.strip():
        return alias, None, f"external checkout repository is unresolved in {relative}: {repository!r}"
    if not isinstance(reference, str):
        return alias, None, f"external checkout reference is missing in {relative}: {alias!r}"
    if re.fullmatch(r"[0-9a-f]{40}", reference):
        kind: ExternalCheckoutKind = "pinned_revision"
    elif (
        repository == "${{ steps.authority.outputs.repository }}"
        and reference == "${{ steps.authority.outputs.revision }}"
    ):
        kind = "trusted_lock"
    elif repository == "${{ job.workflow_repository }}" and reference == "${{ job.workflow_sha }}":
        kind = "workflow_authority"
    elif repository == "${{ inputs.candidate_repository }}" and reference == "${{ inputs.candidate_sha }}":
        kind = "candidate_input"
    else:
        return (
            alias,
            None,
            f"external checkout {repository!r} at path {alias!r} in {relative} "
            "must pin an immutable full commit SHA or use a recognized authority/candidate identity pair",
        )
    return alias, ExternalCheckout(repository, reference, kind), None


def external_checkout_path(checkout: ExternalCheckout, alias: str, suffix: str) -> str:
    """Build a safe inventory identity without reading the external checkout."""
    match checkout.kind:
        case "pinned_revision":
            identity = f"{checkout.repository}@{checkout.revision}"
        case "trusted_lock":
            identity = f"trusted-lock:{alias}"
        case "candidate_input":
            identity = f"candidate-input:{alias}"
        case "workflow_authority":
            identity = f"workflow-authority:{alias}"
    return f"external:{identity}/{suffix}"


def resolve_checkout_source_path(source: CommandSource, raw_path: str) -> tuple[str | None, str | None, str | None]:
    """Resolve a command path against its original workspace and checkout snapshot."""
    relative = raw_path.removeprefix("./")
    context = source.checkout_context
    if context is None:
        candidate = posixpath.normpath(posixpath.join(source.working_directory, relative))
        if candidate == ".." or candidate.startswith("../") or posixpath.isabs(candidate):
            return None, None, f"task path escapes repository without a pinned external checkout at {source.origin}"
        return candidate, None, None

    bindings = dict(context.aliases)
    unresolved = set(context.unresolved_aliases)
    workspace_candidate = posixpath.normpath(posixpath.join(context.workspace_working_directory, relative))
    if workspace_candidate == ".." or workspace_candidate.startswith("../") or posixpath.isabs(workspace_candidate):
        return (
            None,
            None,
            f"task path escapes repository workflow workspace without a declared checkout at {source.origin}",
        )

    for alias in sorted((value for value in unresolved if value != "."), key=len, reverse=True):
        if workspace_candidate == alias or workspace_candidate.startswith(f"{alias}/"):
            return None, None, f"checkout ownership is unresolved for alias {alias!r} at {source.origin}"

    for alias in sorted((value for value in bindings if value != "."), key=len, reverse=True):
        if workspace_candidate == alias or workspace_candidate.startswith(f"{alias}/"):
            if alias in unresolved:
                return None, None, f"checkout ownership is unresolved for alias {alias!r} at {source.origin}"
            suffix = workspace_candidate[len(alias) :].lstrip("/")
            checkout = bindings[alias]
            if checkout is not None:
                normalized = posixpath.normpath(suffix or ".")
                if normalized in {".."} or normalized.startswith("../") or posixpath.isabs(normalized):
                    return None, None, f"task path escapes external checkout {alias!r} at {source.origin}"
                return None, external_checkout_path(checkout, alias, normalized), None
            return suffix or ".", None, None

    if "." in unresolved:
        return None, None, f"workspace checkout ownership is unresolved at {source.origin}"
    root_checkout = bindings.get(".")
    if root_checkout is not None:
        external_suffix = posixpath.normpath(workspace_candidate)
        if external_suffix in {".."} or external_suffix.startswith("../") or posixpath.isabs(external_suffix):
            return None, None, f"task path escapes external workspace checkout at {source.origin}"
        return None, external_checkout_path(root_checkout, ".", external_suffix), None

    return workspace_candidate, None, None


def resolve_import_source_path(
    source: CommandSource,
    import_root: str,
    relative_path: str,
) -> tuple[str | None, str | None, str | None]:
    """Bind a resolved module path to the checkout that owns its import root."""
    context = source.checkout_context
    if context is None:
        return relative_path, None, None

    local_checkout_prefix: str | None = None
    for alias, checkout in context.aliases:
        if alias == "." or checkout is not None:
            continue
        if context.workspace_working_directory == alias or context.workspace_working_directory.startswith(f"{alias}/"):
            normalized_directory = normalize_checkout_working_directory(context.workspace_working_directory, (alias,))
            if normalized_directory == source.working_directory:
                local_checkout_prefix = alias
                break

    working_directory = source.working_directory
    rooted_in_working_directory = (
        working_directory == "." or import_root == working_directory or import_root.startswith(f"{working_directory}/")
    )
    workspace_path = relative_path
    if local_checkout_prefix is not None and rooted_in_working_directory:
        workspace_path = posixpath.join(local_checkout_prefix, relative_path)

    workspace_context = replace(context, workspace_working_directory=".")
    workspace_source = replace(source, working_directory=".", checkout_context=workspace_context)
    return resolve_checkout_source_path(workspace_source, workspace_path)


def normalize_checkout_working_directory(working_directory: str, aliases: tuple[str, ...]) -> str:
    """Remove a local checkout prefix while retaining its repository-relative cwd."""
    normalized = posixpath.normpath(working_directory or ".")
    for alias in aliases:
        if normalized == alias:
            return "."
        if normalized.startswith(f"{alias}/"):
            return normalized[len(alias) + 1 :]
    return normalized

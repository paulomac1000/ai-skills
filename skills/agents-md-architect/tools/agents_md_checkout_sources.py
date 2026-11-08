"""Static workflow checkout identity parsing used by gate-source discovery."""

from __future__ import annotations

import posixpath
import re
from dataclasses import replace

from agents_md_python_roots import resolve_module_paths
from agents_md_source_types import (
    CommandSource,
    ExternalCheckout,
    ExternalCheckoutKind,
    ImportRoot,
)


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


def _local_checkout_prefix(source: CommandSource) -> str | None:
    """Return the workspace alias of the local checkout containing the command cwd."""
    context = source.checkout_context
    if context is None:
        return None
    for alias, checkout in context.aliases:
        if alias == "." or checkout is not None:
            continue
        if context.workspace_working_directory == alias or context.workspace_working_directory.startswith(f"{alias}/"):
            if (
                normalize_checkout_working_directory(context.workspace_working_directory, (alias,))
                == source.working_directory
            ):
                return alias
    return None


def resolve_import_source_path(
    source: CommandSource,
    root: ImportRoot,
    relative_path: str,
) -> tuple[str | None, str | None, str | None]:
    """Bind a resolved module path to the checkout that owns its import root.

    Candidate-relative roots are re-anchored into their local checkout alias
    before ownership resolution; workspace-relative roots are resolved as-is.
    Local ownership returns the repository-relative (alias-stripped) path.
    """
    context = source.checkout_context
    if context is None:
        return relative_path, None, None
    workspace_path = relative_path
    if not root.workspace_relative:
        local_prefix = _local_checkout_prefix(source)
        already_anchored = (
            root.normalized
            and local_prefix is not None
            and (root.path == local_prefix or root.path.startswith(f"{local_prefix}/"))
        )
        if local_prefix is not None and not already_anchored:
            workspace_path = posixpath.join(local_prefix, relative_path)
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


def record_external_only_candidates(
    source: CommandSource,
    roots: tuple[ImportRoot, ...],
    module: str,
    relative_module: str,
    external_sources: dict[str, set[str]],
) -> None:
    """Record external ownership when the invocation resolves nowhere candidate-locally.

    Every root that maps into an external checkout contributes its identity regardless
    of candidate-local lookalikes, so external-only invocations stay visible in the
    evidence instead of returning a silent complete audit.
    """
    for import_root in roots:
        for candidate, _resolved_name in resolve_module_paths(module, (import_root.path,)):
            path, external_path, ownership_issue = resolve_import_source_path(source, import_root, candidate)
            if ownership_issue is None and external_path is not None:
                external_sources.setdefault(external_path, set()).add(source.origin)
        package_path = posixpath.normpath(posixpath.join(import_root.path, relative_module))
        if package_path != ".." and not package_path.startswith("../") and not package_path.startswith("/"):
            path, external_path, ownership_issue = resolve_import_source_path(
                source, import_root, f"{package_path}/__main__.py"
            )
            if ownership_issue is None and external_path is not None:
                external_sources.setdefault(external_path, set()).add(source.origin)

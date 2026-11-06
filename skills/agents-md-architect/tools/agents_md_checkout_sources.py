"""Static workflow checkout identity parsing used by gate-source discovery."""

from __future__ import annotations

import posixpath
import re

from agents_md_source_types import CommandSource, ExternalCheckout, ExternalCheckoutKind


def classify_checkout(
    relative: str,
    repository: str | None,
    reference: str | None,
    path: str | None,
) -> tuple[str | None, ExternalCheckout | None, str | None]:
    """Classify one checkout step without combining identity across jobs."""
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
    """Resolve one task path to local or external ownership in its command scope."""
    relative = raw_path.removeprefix("./")
    context = source.checkout_context
    if context is None:
        return posixpath.normpath(posixpath.join(source.working_directory, relative)), None, None

    bindings = dict(context.aliases)
    unresolved = set(context.unresolved_aliases)
    for alias in sorted((value for value in bindings if value != "."), key=len, reverse=True):
        if relative == alias or relative.startswith(f"{alias}/"):
            if alias in unresolved:
                return None, None, f"checkout ownership is unresolved for alias {alias!r} at {source.origin}"
            suffix = relative[len(alias) :].lstrip("/")
            checkout = bindings[alias]
            if checkout is not None:
                normalized = posixpath.normpath(suffix)
                if normalized in {".."} or normalized.startswith("../") or posixpath.isabs(normalized):
                    return None, None, f"task path escapes external checkout {alias!r} at {source.origin}"
                return None, external_checkout_path(checkout, alias, normalized), None
            relative = suffix
            break
    else:
        unresolved_alias = next(
            (
                value
                for value in sorted(unresolved, key=len, reverse=True)
                if value != "." and (relative == value or relative.startswith(f"{value}/"))
            ),
            None,
        )
        if unresolved_alias is not None:
            return None, None, f"checkout ownership is unresolved for alias {unresolved_alias!r} at {source.origin}"

    working_directory = source.working_directory
    for alias in sorted((value for value in bindings if value != "."), key=len, reverse=True):
        if working_directory == alias or working_directory.startswith(f"{alias}/"):
            if alias in unresolved:
                return (
                    None,
                    None,
                    f"working-directory checkout ownership is unresolved for {alias!r} at {source.origin}",
                )
            suffix = working_directory[len(alias) :].lstrip("/")
            checkout = bindings[alias]
            if checkout is not None:
                external_suffix = posixpath.normpath(posixpath.join(suffix, relative))
                if external_suffix in {".."} or external_suffix.startswith("../") or posixpath.isabs(external_suffix):
                    return None, None, f"task path escapes external working directory {alias!r} at {source.origin}"
                return None, external_checkout_path(checkout, alias, external_suffix), None
            working_directory = suffix or "."
            break

    if "." in unresolved:
        return None, None, f"workspace checkout ownership is unresolved at {source.origin}"
    root_checkout = bindings.get(".")
    if root_checkout is not None:
        external_suffix = posixpath.normpath(posixpath.join(working_directory, relative))
        if external_suffix in {".."} or external_suffix.startswith("../") or posixpath.isabs(external_suffix):
            return None, None, f"task path escapes external workspace checkout at {source.origin}"
        return None, external_checkout_path(root_checkout, ".", external_suffix), None

    candidate = posixpath.normpath(posixpath.join(working_directory, relative))
    for alias in sorted(
        (value for value, owner in bindings.items() if owner is not None and value != "."), key=len, reverse=True
    ):
        if candidate.startswith(f"../{alias}/"):
            checkout = bindings[alias]
            if checkout is None:
                continue
            return (
                None,
                external_checkout_path(checkout, alias, candidate[len(f"../{alias}/") :]),
                None,
            )
    return candidate, None, None


def normalize_checkout_working_directory(working_directory: str, aliases: tuple[str, ...]) -> str:
    normalized = posixpath.normpath(working_directory or ".")
    for alias in aliases:
        if normalized == alias:
            return "."
        if normalized.startswith(f"{alias}/"):
            return normalized[len(alias) + 1 :]
    return normalized

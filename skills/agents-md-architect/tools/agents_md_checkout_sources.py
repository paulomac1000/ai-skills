"""Static workflow checkout identity parsing used by gate-source discovery."""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

import yaml
from agents_md_source_types import ExternalCheckout, ExternalCheckoutKind


def same_repository_checkout_aliases(relative: str, text: str) -> tuple[str, ...]:
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
            if reference not in (None, "", "${{ github.event.pull_request.head.sha }}"):
                continue
            path = options.get("path")
            if not isinstance(path, str) or not path.strip():
                continue
            normalized = posixpath.normpath(path.strip())
            if normalized not in {".", ".."} and not posixpath.isabs(normalized) and not normalized.startswith("../"):
                aliases.add(normalized)
    return tuple(sorted(aliases))


def pinned_external_checkout_aliases(
    relative: str,
    text: str,
) -> tuple[dict[str, ExternalCheckout], tuple[str, ...]]:
    """Identify sibling checkouts only when their immutable identity is explicit."""
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
            checkout = ExternalCheckout(repository, reference, kind)
            existing = aliases.get(alias)
            if existing is not None and existing != checkout:
                issues.append(f"external checkout alias {alias!r} is ambiguous in {relative}")
                continue
            aliases[alias] = checkout
    return aliases, tuple(sorted(set(issues)))


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


def normalize_checkout_working_directory(working_directory: str, aliases: tuple[str, ...]) -> str:
    normalized = posixpath.normpath(working_directory or ".")
    for alias in aliases:
        if normalized == alias:
            return "."
        if normalized.startswith(f"{alias}/"):
            return normalized[len(alias) + 1 :]
    return normalized

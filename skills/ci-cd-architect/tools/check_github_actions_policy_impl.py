#!/usr/bin/env python3
"""Validate GitHub Actions workflows from an untrusted repository tree."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

MAX_WORKFLOW_FILES = 128
MAX_WORKFLOW_BYTES = 256 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024

_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_DOCKER_DIGEST = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
_ACTION_NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$")
_EXPRESSION_REFERENCE = re.compile(r"\$\{\{")
_MATRIX_RUNNER = re.compile(r"^\$\{\{\s*matrix[.]([A-Za-z_][A-Za-z0-9_-]*)\s*\}\}$")
_SECRET_CONTEXT_REFERENCE = re.compile(
    r"\$\{\{(?:(?!\}\}).)*\bsecrets\b(?:(?!\}\}).)*\}\}",
    re.IGNORECASE | re.DOTALL,
)
_PROFILE_MARKER = re.compile(
    r"^\s*#\s*ai-skills-policy-profile:\s*(pull-request|trusted-ci|protected-release)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_WRITE_PERMISSION = re.compile(r"(^|-)write$")
_WORKFLOW_SUFFIXES = {".yml", ".yaml"}
_MUTABLE_RUNNERS = {"ubuntu-latest", "windows-latest", "macos-latest"}
_PROFILES = {"pull-request", "trusted-ci", "protected-release"}
_TRUSTED_CI_WRITE_SCOPES = frozenset({"checks", "security-events"})
_PROTECTED_RELEASE_WRITE_SCOPES = frozenset(
    {"attestations", "contents", "id-token", "packages", "security-events"}
)


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueKeyLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True)
class Finding:
    path: Path
    message: str

    def render(self) -> str:
        return f"{self.path.as_posix()}: {self.message}"


def _events(document: dict[Any, Any]) -> Any:
    """Return the workflow event declaration despite YAML 1.1 parsing `on` as bool."""
    return document.get("on", document.get(True))


def _event_names(events: Any) -> tuple[set[str], str | None]:
    if isinstance(events, str):
        return {events}, None
    if isinstance(events, dict):
        if not events:
            return set(), "workflow must declare events"
        if not all(isinstance(name, str) and name for name in events):
            return set(), "workflow event names must be non-empty strings"
        return set(events), None
    if isinstance(events, list):
        if not events:
            return set(), "workflow must declare events"
        if not all(isinstance(name, str) and name for name in events):
            return set(), "workflow event list must contain non-empty strings"
        return set(events), None
    if events is None:
        return set(), "workflow must declare events"
    return set(), "workflow events must be a string, list of strings, or mapping"


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _profile(raw_text: str, event_names: set[str], explicit_profile: str | None) -> tuple[str, str | None]:
    marker = _PROFILE_MARKER.search(raw_text)
    marker_profile = marker.group(1).casefold() if marker is not None else None
    if explicit_profile is not None:
        normalized = explicit_profile.casefold()
        if normalized not in _PROFILES:
            return "trusted-ci", f"unknown workflow policy profile: {explicit_profile}"
        if marker_profile is not None and marker_profile != normalized:
            return normalized, "workflow profile marker conflicts with repository policy"
        return normalized, None
    if marker_profile is not None:
        return marker_profile, None
    if "pull_request" in event_names:
        return "pull-request", None
    return "trusted-ci", None


def _permission_findings(
    path: Path,
    permissions: Any,
    *,
    scope: str,
    allowed_read_scopes: frozenset[str] | None = None,
    allowed_write_scopes: frozenset[str] = frozenset(),
) -> list[Finding]:
    if permissions is None:
        return [Finding(path, f"{scope} must declare explicit permissions")]
    if not isinstance(permissions, dict):
        return [
            Finding(
                path,
                f"{scope} permissions must be an explicit mapping; shorthand values are forbidden",
            )
        ]

    findings: list[Finding] = []
    for name, access in permissions.items():
        if not isinstance(name, str) or not isinstance(access, str):
            findings.append(Finding(path, f"{scope} permission names and access values must be strings"))
            continue
        normalized_name = name.casefold()
        normalized_access = access.casefold()
        if _WRITE_PERMISSION.search(normalized_access):
            if normalized_name not in allowed_write_scopes:
                allowed = ", ".join(sorted(allowed_write_scopes)) or "none"
                findings.append(
                    Finding(
                        path,
                        f"{scope} grants {name}: {access}; allowed write scopes are: {allowed}",
                    )
                )
        elif normalized_access not in {"read", "none"}:
            findings.append(Finding(path, f"{scope} has unsupported permission {name}: {access}"))
        elif (
            normalized_access == "read"
            and allowed_read_scopes is not None
            and normalized_name not in allowed_read_scopes
        ):
            allowed = ", ".join(sorted(allowed_read_scopes)) or "none"
            findings.append(
                Finding(
                    path,
                    f"{scope} grants {name}: read; allowed read scopes are: {allowed}",
                )
            )
    return findings


def _permission_has_write(permissions: Any) -> bool:
    return isinstance(permissions, dict) and any(
        isinstance(access, str) and _WRITE_PERMISSION.search(access.casefold()) for access in permissions.values()
    )


def _external_action_findings(path: Path, label: str, uses: Any) -> list[Finding]:
    if not isinstance(uses, str):
        return [Finding(path, f"{label} has non-string uses value")]
    if uses.startswith("./"):
        candidate = PurePosixPath(uses)
        if candidate.is_absolute() or ".." in candidate.parts or "\\" in uses:
            return [Finding(path, f"{label} local action path must remain inside the repository")]
        return []
    if uses.startswith("docker://"):
        image = uses.removeprefix("docker://")
        if not _DOCKER_DIGEST.fullmatch(image):
            return [Finding(path, f"{label} Docker action must use an exact sha256 digest")]
        return []
    if "@" not in uses:
        return [Finding(path, f"{label} action {uses!r} has no immutable revision")]

    action, revision = uses.rsplit("@", 1)
    findings: list[Finding] = []
    if not _ACTION_NAME.fullmatch(action):
        findings.append(Finding(path, f"{label} action {action!r} has invalid owner/repository syntax"))
    if not _FULL_SHA.fullmatch(revision):
        findings.append(Finding(path, f"{label} action {action!r} must use a full 40-character SHA"))
    return findings


def _action_findings(path: Path, job_name: str, step_index: int, step: Any) -> list[Finding]:
    if not isinstance(step, dict) or "uses" not in step:
        return []

    uses = step["uses"]
    label = f"job {job_name!r} step {step_index}"
    findings = _external_action_findings(path, label, uses)
    if not isinstance(uses, str):
        return findings

    action = uses.rsplit("@", 1)[0]
    with_block = step.get("with")
    if action == "actions/checkout" and (
        not isinstance(with_block, dict) or with_block.get("persist-credentials") is not False
    ):
        findings.append(Finding(path, f"{label} actions/checkout must set persist-credentials: false"))

    if action == "actions/upload-artifact":
        if not isinstance(with_block, dict):
            findings.append(Finding(path, f"{label} upload-artifact requires a with mapping"))
        else:
            if not _positive_int(with_block.get("retention-days")):
                findings.append(Finding(path, f"{label} upload-artifact needs positive retention-days"))
            if with_block.get("if-no-files-found") not in {"error", "warn", "ignore"}:
                findings.append(Finding(path, f"{label} upload-artifact needs explicit if-no-files-found"))

    return findings


def _concrete_runner_error(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return "runner values must be non-empty literal strings"
    normalized = value.strip()
    if _EXPRESSION_REFERENCE.search(normalized):
        return "runner matrix values must not contain expressions"
    if normalized.casefold() in _MUTABLE_RUNNERS:
        return f"runner matrix values must pin a concrete runner instead of {value}"
    return None


def _matrix_runner_values(job: dict[Any, Any], key: str) -> tuple[list[Any], str | None]:
    strategy = job.get("strategy")
    if not isinstance(strategy, dict):
        return [], "matrix runner expression requires a strategy mapping"
    matrix = strategy.get("matrix")
    if not isinstance(matrix, dict):
        return [], "matrix runner expression requires a matrix mapping"

    values: list[Any] = []
    direct_axis = matrix.get(key)
    if direct_axis is not None:
        if not isinstance(direct_axis, list) or not direct_axis:
            return [], f"matrix runner axis {key!r} must be a non-empty list"
        values.extend(direct_axis)

    include = matrix.get("include")
    if include is not None:
        if not isinstance(include, list) or not all(isinstance(item, dict) for item in include):
            return [], "matrix include must be a list of mappings"
        if direct_axis is None and any(key not in item for item in include):
            return [], f"every matrix include entry must declare runner key {key!r}"
        values.extend(item[key] for item in include if key in item)

    if not values:
        return [], f"matrix runner key {key!r} has no declared values"
    return values, None


def _runner_findings(
    path: Path,
    job_name: str,
    runs_on: Any,
    job: dict[Any, Any],
) -> list[Finding]:
    scope = f"job {job_name!r}"
    if not isinstance(runs_on, str) or not runs_on.strip():
        return [Finding(path, f"{scope} runs-on must be a non-empty literal string")]
    normalized_runs_on = runs_on.strip()
    matrix_match = _MATRIX_RUNNER.fullmatch(normalized_runs_on)
    if matrix_match is not None:
        values, matrix_error = _matrix_runner_values(job, matrix_match.group(1))
        if matrix_error:
            return [Finding(path, f"{scope} {matrix_error}")]
        findings = []
        for value in values:
            error = _concrete_runner_error(value)
            if error:
                findings.append(Finding(path, f"{scope} {error}"))
        return findings
    if _EXPRESSION_REFERENCE.search(normalized_runs_on):
        return [
            Finding(
                path,
                f"{scope} runs-on expressions are forbidden unless bound to a closed literal matrix",
            )
        ]
    if normalized_runs_on.casefold() in _MUTABLE_RUNNERS:
        return [Finding(path, f"{scope} must pin a concrete runner instead of {runs_on}")]
    return []


def _scalar_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _scalar_strings(key)
            yield from _scalar_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _scalar_strings(item)


def _reusable_workflow_findings(path: Path, job_name: str, job: dict[Any, Any], profile: str) -> list[Finding]:
    label = f"job {job_name!r}"
    findings = _external_action_findings(path, label, job.get("uses"))
    uses = job.get("uses")
    if isinstance(uses, str) and uses.startswith("./"):
        candidate = PurePosixPath(uses)
        if len(candidate.parts) < 3 or candidate.parts[:2] != (".github", "workflows"):
            findings.append(Finding(path, f"{label} local reusable workflow must live under .github/workflows"))
    if profile == "pull-request" and job.get("secrets") == "inherit":
        findings.append(Finding(path, f"{label} pull-request reusable workflow must not inherit secrets"))
    return findings


WorkflowReader = Callable[[Path, Path], tuple[str | None, str | None]]
WorkflowEnumerator = Callable[[Path], tuple[list[Path], list[Finding]]]


def audit_workflow(
    path: Path,
    repository_root: Path,
    *,
    reader: WorkflowReader,
    profile: str | None = None,
) -> list[Finding]:
    root = repository_root.resolve()
    raw_text, read_error = reader(path, root)
    if read_error is not None:
        return [Finding(path, read_error)]
    assert raw_text is not None

    try:
        document = yaml.load(raw_text, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        return [Finding(path, f"cannot parse workflow: {exc}")]
    if not isinstance(document, dict):
        return [Finding(path, "workflow root must be a mapping")]

    findings: list[Finding] = []
    event_names, event_error = _event_names(_events(document))
    if event_error:
        findings.append(Finding(path, event_error))
    selected_profile, profile_error = _profile(raw_text, event_names, profile)
    if profile_error:
        findings.append(Finding(path, profile_error))
    if "pull_request_target" in event_names:
        findings.append(Finding(path, "pull_request_target is forbidden for repository code"))
    if selected_profile == "protected-release" and {"pull_request", "pull_request_target"}.intersection(event_names):
        findings.append(Finding(path, "protected-release workflows must not run on pull-request events"))

    pull_request_workflow = "pull_request" in event_names
    allowed_read_scopes = (
        frozenset({"contents"})
        if selected_profile == "pull-request"
        else frozenset({"actions", "contents"})
        if selected_profile == "trusted-ci" and pull_request_workflow
        else None
    )
    findings.extend(
        _permission_findings(
            path,
            document.get("permissions"),
            scope="workflow",
            allowed_read_scopes=allowed_read_scopes,
            allowed_write_scopes=frozenset(),
        )
    )

    concurrency = document.get("concurrency")
    if not isinstance(concurrency, dict):
        findings.append(Finding(path, "workflow must declare concurrency as a mapping"))
    else:
        group = concurrency.get("group")
        if not isinstance(group, str) or not group.strip():
            findings.append(Finding(path, "workflow must declare a non-empty concurrency group"))
        if not isinstance(concurrency.get("cancel-in-progress"), bool):
            findings.append(Finding(path, "concurrency cancel-in-progress must be a boolean"))

    jobs = document.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        return [*findings, Finding(path, "workflow must declare at least one job")]

    protected_write_jobs = 0
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            findings.append(Finding(path, f"job {job_name!r} must be a mapping"))
            continue

        job_permissions = job.get("permissions")
        write_job = _permission_has_write(job_permissions)
        if write_job:
            protected_write_jobs += 1
        write_scopes = (
            _PROTECTED_RELEASE_WRITE_SCOPES
            if selected_profile == "protected-release"
            else _TRUSTED_CI_WRITE_SCOPES
            if selected_profile == "trusted-ci"
            else frozenset()
        )
        if "permissions" in job:
            findings.extend(
                _permission_findings(
                    path,
                    job_permissions,
                    scope=f"job {job_name!r}",
                    allowed_read_scopes=allowed_read_scopes,
                    allowed_write_scopes=write_scopes,
                )
            )
        if write_job and selected_profile == "pull-request":
            findings.append(
                Finding(
                    path,
                    f"job {job_name!r} write permissions require trusted-ci or protected-release profile",
                )
            )
        if write_job and selected_profile == "protected-release":
            if not isinstance(job.get("environment"), (str, dict)):
                findings.append(
                    Finding(
                        path,
                        f"job {job_name!r} with release write permissions requires a protected environment",
                    )
                )
            if not job.get("needs"):
                findings.append(
                    Finding(
                        path,
                        f"job {job_name!r} with release write permissions must depend on a prior validation job",
                    )
                )

        if "uses" in job:
            findings.extend(_reusable_workflow_findings(path, str(job_name), job, selected_profile))
            continue

        if not _positive_int(job.get("timeout-minutes")):
            findings.append(Finding(path, f"job {job_name!r} needs positive timeout-minutes"))
        findings.extend(_runner_findings(path, str(job_name), job.get("runs-on"), job))

        steps = job.get("steps", [])
        if not isinstance(steps, list):
            findings.append(Finding(path, f"job {job_name!r} steps must be a list"))
            continue
        for index, step in enumerate(steps, start=1):
            findings.extend(_action_findings(path, str(job_name), index, step))
            if (
                write_job
                and selected_profile == "protected-release"
                and isinstance(step, dict)
                and isinstance(step.get("uses"), str)
            ):
                action = step["uses"].rsplit("@", 1)[0]
                if action == "actions/checkout" or action.startswith("./"):
                    findings.append(
                        Finding(
                            path,
                            f"job {job_name!r} with release write permissions must not execute repository source",
                        )
                    )

    if selected_profile == "protected-release" and protected_write_jobs == 0:
        findings.append(
            Finding(
                path,
                "protected-release profile requires at least one job with explicit write permissions",
            )
        )

    if pull_request_workflow and any(_SECRET_CONTEXT_REFERENCE.search(value) for value in _scalar_strings(document)):
        findings.append(Finding(path, "pull-request workflows must not reference repository secrets"))

    return findings


def audit_repository(
    repository_root: Path,
    *,
    reader: WorkflowReader,
    enumerator: WorkflowEnumerator,
) -> list[Finding]:
    root = repository_root.resolve()
    paths, findings = enumerator(root)
    if not paths and not findings:
        findings.append(Finding(root, "no GitHub Actions workflows found"))
    for path in paths:
        findings.extend(audit_workflow(path, root, reader=reader))
    return findings

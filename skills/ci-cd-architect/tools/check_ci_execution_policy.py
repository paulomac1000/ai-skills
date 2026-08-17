#!/usr/bin/env python3
"""Validate cost-aware GitHub Actions execution triggers."""

from __future__ import annotations

import argparse
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.confined_io import ConfinedReadError, is_link_or_reparse, read_utf8_bounded  # noqa: E402

_MARKER = re.compile(
    r"^\s*#\s*ai-skills-execution-policy:\s*(on-demand)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_WORKFLOW_SUFFIXES = {".yml", ".yaml"}
_DEFAULT_INTEGRATION_BRANCHES = ("main", "master")
_ALLOWED_EVENTS = frozenset({"push", "workflow_dispatch"})
MAX_WORKFLOW_BYTES = 512 * 1024
MAX_WORKFLOW_ENTRIES = 512


class _UniqueKeyLoader(yaml.SafeLoader):
    """YAML loader that rejects duplicate keys."""


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
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
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


@dataclass(frozen=True)
class Finding:
    path: Path
    message: str

    def render(self) -> str:
        return f"{self.path.as_posix()}: {self.message}"


def _events(document: dict[Any, Any]) -> Any:
    return document.get("on", document.get(True))


def _event_map(value: Any) -> tuple[dict[str, Any], str | None]:
    if isinstance(value, str):
        return {value: None}, None
    if isinstance(value, list):
        if value and all(isinstance(item, str) and item for item in value):
            return {item: None for item in value}, None
        return {}, "workflow event list must contain non-empty strings"
    if isinstance(value, dict):
        if not value:
            return {}, "workflow must declare at least one event"
        if not all(isinstance(key, str) and key for key in value):
            return {}, "workflow event names must be non-empty strings"
        return dict(value), None
    return {}, "workflow events must be a string, list, or mapping"


def _branch_findings(path: Path, push: Any, allowed_branches: frozenset[str]) -> list[Finding]:
    if not isinstance(push, dict):
        return [
            Finding(
                path,
                "on-demand push trigger must be a mapping restricted to integration branches",
            )
        ]
    branches = push.get("branches")
    if not isinstance(branches, list) or not branches:
        return [Finding(path, "on-demand push trigger must declare a non-empty branches list")]
    findings: list[Finding] = []
    for branch in branches:
        if not isinstance(branch, str) or not branch:
            findings.append(Finding(path, "push branches must be literal non-empty strings"))
        elif branch not in allowed_branches:
            allowed = ", ".join(sorted(allowed_branches))
            findings.append(
                Finding(
                    path,
                    f"automatic push branch {branch!r} is outside the allowed integration branches: {allowed}",
                )
            )
    for forbidden in ("branches-ignore", "tags", "tags-ignore"):
        if forbidden in push:
            findings.append(
                Finding(
                    path,
                    f"on-demand push trigger must not declare {forbidden}; use manual dispatch for non-integration refs",
                )
            )
    return findings


def _dispatch_findings(path: Path, dispatch: Any) -> list[Finding]:
    if dispatch is None:
        return []
    if not isinstance(dispatch, dict):
        return [Finding(path, "workflow_dispatch configuration must be a mapping")]
    inputs = dispatch.get("inputs")
    if inputs is None:
        return []
    if not isinstance(inputs, dict):
        return [Finding(path, "workflow_dispatch inputs must be a mapping")]
    full = inputs.get("full")
    if full is None:
        return []
    if not isinstance(full, dict):
        return [Finding(path, "workflow_dispatch input 'full' must be a mapping")]
    findings: list[Finding] = []
    if full.get("type") != "boolean":
        findings.append(Finding(path, "workflow_dispatch input 'full' must use type: boolean"))
    if full.get("default") is not False:
        findings.append(Finding(path, "workflow_dispatch input 'full' must default to false"))
    return findings


def audit_text(
    path: Path,
    raw_text: str,
    *,
    integration_branches: tuple[str, ...] = _DEFAULT_INTEGRATION_BRANCHES,
    require_marker: bool = True,
) -> list[Finding]:
    marker = _MARKER.search(raw_text)
    if marker is None:
        return [Finding(path, "missing ai-skills-execution-policy: on-demand marker")] if require_marker else []

    try:
        document = yaml.load(raw_text, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        return [Finding(path, f"cannot parse workflow: {exc}")]
    if not isinstance(document, dict):
        return [Finding(path, "workflow root must be a mapping")]

    events, event_error = _event_map(_events(document))
    findings: list[Finding] = []
    if event_error:
        findings.append(Finding(path, event_error))
        return findings

    for event in sorted(set(events) - _ALLOWED_EVENTS):
        findings.append(
            Finding(
                path,
                f"on-demand workflow must not auto-run on {event!r}; allowed events are push and workflow_dispatch",
            )
        )
    if "workflow_dispatch" not in events:
        findings.append(Finding(path, "on-demand workflow must declare workflow_dispatch"))
    if "push" in events:
        allowed = frozenset(branch for branch in integration_branches if branch)
        if not allowed:
            findings.append(Finding(path, "at least one integration branch must be configured"))
        else:
            findings.extend(_branch_findings(path, events["push"], allowed))
    findings.extend(_dispatch_findings(path, events.get("workflow_dispatch")))

    concurrency = document.get("concurrency")
    if not isinstance(concurrency, dict):
        findings.append(Finding(path, "on-demand workflow must declare concurrency as a mapping"))
    elif concurrency.get("cancel-in-progress") is not True:
        findings.append(Finding(path, "on-demand workflow must set concurrency.cancel-in-progress: true"))
    return findings


def _read_workflow(path: Path, root: Path) -> tuple[str | None, str | None]:
    """Read a workflow only when it is confined, regular, stable, UTF-8, and bounded."""
    try:
        raw_text, _byte_count = read_utf8_bounded(path, root, MAX_WORKFLOW_BYTES)
    except ConfinedReadError as exc:
        if exc.code == "input.too-large":
            return None, f"workflow exceeds {MAX_WORKFLOW_BYTES} byte limit"
        return None, f"cannot read workflow safely: {exc}"
    return raw_text, None


def _workflow_paths(root: Path) -> list[Path]:
    """Enumerate a bounded workflow directory without following link-like repository components."""
    resolved_root = root.resolve(strict=True)
    directory = resolved_root / ".github" / "workflows"
    current = resolved_root
    for part in (".github", "workflows"):
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            return []
        if is_link_or_reparse(metadata):
            raise OSError(f"workflow directory contains a symlink or reparse component: {current}")
        if not stat.S_ISDIR(metadata.st_mode):
            raise OSError(f"workflow directory component is not a directory: {current}")
    try:
        entries = list(directory.iterdir())
    except OSError as exc:
        raise OSError(f"cannot enumerate workflow directory: {exc}") from exc
    if len(entries) > MAX_WORKFLOW_ENTRIES:
        raise OSError(f"workflow directory exceeds {MAX_WORKFLOW_ENTRIES} entries")
    paths: list[Path] = []
    for path in sorted(entries):
        if path.suffix not in _WORKFLOW_SUFFIXES:
            continue
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise OSError(f"cannot inspect workflow entry {path.name}: {exc}") from exc
        if is_link_or_reparse(metadata) or not stat.S_ISREG(metadata.st_mode):
            raise OSError(f"workflow entry must be a regular non-symlink file: {path.name}")
        paths.append(path)
    return paths


def audit_repository(
    root: Path, *, integration_branches: tuple[str, ...] = _DEFAULT_INTEGRATION_BRANCHES
) -> list[Finding]:
    resolved_root = root.resolve(strict=True)
    findings: list[Finding] = []
    try:
        paths = _workflow_paths(resolved_root)
    except OSError as exc:
        return [Finding(Path(".github/workflows"), f"cannot enumerate workflows safely: {exc}")]
    for path in paths:
        raw_text, error = _read_workflow(path, resolved_root)
        if error is not None:
            findings.append(Finding(path.relative_to(resolved_root), error))
            continue
        assert raw_text is not None
        if _MARKER.search(raw_text):
            findings.extend(
                audit_text(
                    path.relative_to(resolved_root),
                    raw_text,
                    integration_branches=integration_branches,
                    require_marker=True,
                )
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository_root", type=Path)
    parser.add_argument(
        "--integration-branch",
        action="append",
        dest="integration_branches",
        help="Allowed automatic push branch; repeat as needed (default: main, master)",
    )
    parser.add_argument(
        "--workflow",
        action="append",
        type=Path,
        help="Audit this workflow and require the on-demand marker; repeat as needed",
    )
    args = parser.parse_args(argv)
    root = args.repository_root.resolve(strict=True)
    branches = tuple(args.integration_branches or _DEFAULT_INTEGRATION_BRANCHES)

    findings: list[Finding] = []
    if args.workflow:
        for workflow in args.workflow:
            path = workflow if workflow.is_absolute() else root / workflow
            raw_text, error = _read_workflow(path, root)
            if error is not None:
                findings.append(Finding(workflow, error))
                continue
            assert raw_text is not None
            display = path.relative_to(root) if path.is_relative_to(root) else path
            findings.extend(audit_text(display, raw_text, integration_branches=branches, require_marker=True))
    else:
        findings.extend(audit_repository(root, integration_branches=branches))

    for finding in findings:
        print(finding.render(), file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

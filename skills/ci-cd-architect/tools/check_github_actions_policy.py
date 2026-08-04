#!/usr/bin/env python3
"""Hardened entrypoint for the trusted GitHub Actions policy auditor."""

from __future__ import annotations

import os
import stat
import sys
from collections.abc import Iterator
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPOSITORY_ROOT = TOOLS.parents[2]
CONTRACTS = REPOSITORY_ROOT / "contracts"
if str(CONTRACTS) not in sys.path:
    sys.path.insert(0, str(CONTRACTS))

import check_github_actions_policy_impl as _impl
from confined_io import (  # noqa: E402
    ConfinedReadError,
    component_snapshot as _component_snapshot,
    is_link_or_reparse as _is_link_or_reparse,
    open_stable as _open_stable,
    read_utf8_bounded,
    snapshot_is_current as _snapshot_is_current,
    supports_component_nofollow as _supports_component_nofollow,
)

MAX_DISCOVERY_ENTRIES = 4096
MAX_WORKFLOW_FILES = _impl.MAX_WORKFLOW_FILES
MAX_WORKFLOW_BYTES = _impl.MAX_WORKFLOW_BYTES
MAX_TOTAL_BYTES = _impl.MAX_TOTAL_BYTES
Finding = _impl.Finding


def _read_workflow(path: Path, repository_root: Path) -> tuple[str | None, str | None]:
    """Read a bounded workflow through the shared stable confinement layer."""
    try:
        text, _count = read_utf8_bounded(path, repository_root, MAX_WORKFLOW_BYTES)
        return text, None
    except ConfinedReadError as error:
        return None, f"cannot read workflow safely: {error.message}"


def _collect_workflow_entries(
    entries: Iterator[os.DirEntry[str]],
    workflow_dir: Path,
) -> tuple[list[Path], list[Finding]]:
    paths: list[Path] = []
    findings: list[Finding] = []
    total_bytes = 0

    for entries_seen, entry in enumerate(entries, start=1):
        if entries_seen > MAX_DISCOVERY_ENTRIES:
            findings.append(
                Finding(
                    workflow_dir,
                    f"workflow directory entry count exceeds {MAX_DISCOVERY_ENTRIES}",
                )
            )
            break
        if Path(entry.name).suffix.casefold() not in _impl._WORKFLOW_SUFFIXES:
            continue
        if len(paths) >= MAX_WORKFLOW_FILES:
            findings.append(Finding(workflow_dir, f"workflow count exceeds {MAX_WORKFLOW_FILES}"))
            break
        entry_path = workflow_dir / entry.name
        try:
            metadata = entry.stat(follow_symlinks=False)
        except OSError as exc:
            findings.append(Finding(entry_path, f"cannot inspect workflow: {exc}"))
            continue
        if _is_link_or_reparse(metadata) or not stat.S_ISREG(metadata.st_mode):
            findings.append(Finding(entry_path, "workflow path must be a regular non-symlink file"))
            continue
        total_bytes += metadata.st_size
        if total_bytes > MAX_TOTAL_BYTES:
            findings.append(Finding(workflow_dir, f"workflow bytes exceed {MAX_TOTAL_BYTES} total limit"))
            break
        paths.append(entry_path)

    paths.sort(key=lambda item: item.name)
    return paths, findings


def workflow_paths(repository_root: Path) -> tuple[list[Path], list[Finding]]:
    """Enumerate workflow candidates incrementally under a global entry budget."""
    workflow_dir = repository_root / ".github" / "workflows"

    if _supports_component_nofollow() and os.scandir in getattr(os, "supports_fd", set()):
        try:
            directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            descriptor, _ = _open_stable(workflow_dir, directory_flags)
        except FileNotFoundError:
            return [], [Finding(repository_root, "no GitHub Actions workflows found")]
        except OSError as exc:
            return [], [Finding(workflow_dir, f"cannot enumerate workflows: {exc}")]
        try:
            if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                return [], [Finding(workflow_dir, "workflow directory must be a regular directory")]
            with os.scandir(descriptor) as entries:
                return _collect_workflow_entries(entries, workflow_dir)
        except OSError as exc:
            return [], [Finding(workflow_dir, f"cannot enumerate workflows: {exc}")]
        finally:
            os.close(descriptor)

    try:
        snapshot = _component_snapshot(workflow_dir)
        if not stat.S_ISDIR(snapshot[-1][1].st_mode):
            return [], [Finding(workflow_dir, "workflow directory must be a regular directory")]
        with os.scandir(workflow_dir) as entries:
            paths, findings = _collect_workflow_entries(entries, workflow_dir)
        if not _snapshot_is_current(snapshot):
            return [], [Finding(workflow_dir, "workflow directory identity changed while enumerating")]
        return paths, findings
    except FileNotFoundError:
        return [], [Finding(repository_root, "no GitHub Actions workflows found")]
    except OSError as exc:
        return [], [Finding(workflow_dir, f"cannot enumerate workflows: {exc}")]


_impl._read_workflow = _read_workflow
_impl.workflow_paths = workflow_paths

audit_workflow = _impl.audit_workflow
audit_repository = _impl.audit_repository
_event_names = _impl._event_names
main = _impl.main


if __name__ == "__main__":
    raise SystemExit(main())

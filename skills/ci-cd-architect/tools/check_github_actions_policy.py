#!/usr/bin/env python3
"""Hardened entrypoint for the trusted GitHub Actions policy auditor."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import check_github_actions_policy_impl as _impl

MAX_DISCOVERY_ENTRIES = 4096
MAX_WORKFLOW_FILES = _impl.MAX_WORKFLOW_FILES
MAX_WORKFLOW_BYTES = _impl.MAX_WORKFLOW_BYTES
MAX_TOTAL_BYTES = _impl.MAX_TOTAL_BYTES
Finding = _impl.Finding


def _supports_component_nofollow() -> bool:
    return bool(
        getattr(os, "O_NOFOLLOW", 0)
        and getattr(os, "O_DIRECTORY", 0)
        and os.open in getattr(os, "supports_dir_fd", set())
    )


def _open_component_safe(path: Path, flags: int) -> int:
    """Open an absolute path without following intermediate or final symlinks."""
    absolute = path.absolute()
    parts = absolute.parts
    if len(parts) < 2:
        raise OSError("input path has no final component")
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory = os.open(parts[0], directory_flags)
    try:
        for component in parts[1:-1]:
            child = os.open(component, directory_flags, dir_fd=directory)
            os.close(directory)
            directory = child
        return os.open(parts[-1], flags | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory)
    finally:
        os.close(directory)


def _open_stable(path: Path, flags: int) -> tuple[int, os.stat_result | None]:
    """Open with component no-follow where available, otherwise bind path identity."""
    if _supports_component_nofollow():
        return _open_component_safe(path, flags), None
    expected = os.lstat(path)
    if stat.S_ISLNK(expected.st_mode):
        raise OSError("refusing to follow a symlink")
    descriptor = os.open(path, flags)
    metadata = os.fstat(descriptor)
    current = os.lstat(path)
    if not os.path.samestat(expected, metadata) or not os.path.samestat(current, metadata):
        os.close(descriptor)
        raise OSError("path identity changed while opening")
    return descriptor, expected


def _read_workflow(path: Path, repository_root: Path) -> tuple[str | None, str | None]:
    """Read a bounded, stable workflow without following replaced path components."""
    try:
        root = repository_root.resolve(strict=True)
        candidate = path.absolute()
        candidate.relative_to(root)
        descriptor, expected = _open_stable(candidate, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    except (OSError, ValueError) as exc:
        return None, f"cannot read workflow safely: {exc}"

    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            return None, "workflow path must be a regular file"
        if metadata.st_size > MAX_WORKFLOW_BYTES:
            return None, f"workflow exceeds {MAX_WORKFLOW_BYTES} byte limit"
        payload = b""
        remaining = MAX_WORKFLOW_BYTES + 1
        chunks: list[bytes] = []
        while remaining > 0:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if expected is not None:
            current = os.lstat(candidate)
            if not os.path.samestat(current, metadata):
                return None, "workflow identity changed while reading"
    except OSError as exc:
        return None, f"cannot read workflow safely: {exc}"
    finally:
        os.close(descriptor)

    if len(payload) > MAX_WORKFLOW_BYTES:
        return None, f"workflow exceeds {MAX_WORKFLOW_BYTES} byte limit"
    try:
        return payload.decode("utf-8"), None
    except UnicodeError as exc:
        return None, f"cannot read workflow safely: {exc}"


def workflow_paths(repository_root: Path) -> tuple[list[Path], list[Finding]]:
    """Enumerate workflow candidates incrementally under a global entry budget."""
    workflow_dir = repository_root / ".github" / "workflows"
    findings: list[Finding] = []
    paths: list[Path] = []
    total_bytes = 0
    entries_seen = 0

    try:
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor, expected = _open_stable(workflow_dir, directory_flags)
    except FileNotFoundError:
        return [], [Finding(repository_root, "no GitHub Actions workflows found")]
    except OSError as exc:
        return [], [Finding(workflow_dir, f"cannot enumerate workflows: {exc}")]

    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            return [], [Finding(workflow_dir, "workflow directory must be a regular directory")]
        scandir_target: int | Path = descriptor if os.scandir in getattr(os, "supports_fd", set()) else workflow_dir
        with os.scandir(scandir_target) as entries:
            for entry in entries:
                entries_seen += 1
                if entries_seen > MAX_DISCOVERY_ENTRIES:
                    findings.append(
                        Finding(workflow_dir, f"workflow directory entry count exceeds {MAX_DISCOVERY_ENTRIES}")
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
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                    findings.append(Finding(entry_path, "workflow path must be a regular non-symlink file"))
                    continue
                total_bytes += metadata.st_size
                if total_bytes > MAX_TOTAL_BYTES:
                    findings.append(Finding(workflow_dir, f"workflow bytes exceed {MAX_TOTAL_BYTES} total limit"))
                    break
                paths.append(entry_path)
        if expected is not None:
            current = os.lstat(workflow_dir)
            if not os.path.samestat(current, os.fstat(descriptor)):
                return [], [Finding(workflow_dir, "workflow directory identity changed while enumerating")]
    except OSError as exc:
        return [], [Finding(workflow_dir, f"cannot enumerate workflows: {exc}")]
    finally:
        os.close(descriptor)

    paths.sort(key=lambda item: item.name)
    return paths, findings


_impl._read_workflow = _read_workflow
_impl.workflow_paths = workflow_paths

audit_workflow = _impl.audit_workflow
audit_repository = _impl.audit_repository
_event_names = _impl._event_names
main = _impl.main


if __name__ == "__main__":
    raise SystemExit(main())

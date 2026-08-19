#!/usr/bin/env python3
"""Hardened entrypoint for the trusted GitHub Actions policy auditor."""

from __future__ import annotations

import argparse
import os
import stat
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPOSITORY_ROOT = TOOLS.parents[2]
CONTRACTS = REPOSITORY_ROOT / "contracts"
if str(CONTRACTS) not in sys.path:
    sys.path.insert(0, str(CONTRACTS))

import check_github_actions_policy_impl as _impl  # noqa: E402
import yaml  # noqa: E402
from confined_io import ConfinedReadError, read_utf8_bounded  # noqa: E402
from confined_io import component_snapshot as _component_snapshot  # noqa: E402
from confined_io import is_link_or_reparse as _is_link_or_reparse  # noqa: E402
from confined_io import open_stable as _confined_open_stable  # noqa: E402
from confined_io import snapshot_is_current as _snapshot_is_current  # noqa: E402
from confined_io import supports_component_nofollow as _supports_component_nofollow  # noqa: E402

MAX_DISCOVERY_ENTRIES = 4096
MAX_POLICY_BYTES = 64 * 1024
POLICY_PATH = Path(".github/workflow-policy.yaml")
MAX_WORKFLOW_FILES = _impl.MAX_WORKFLOW_FILES
MAX_WORKFLOW_BYTES = _impl.MAX_WORKFLOW_BYTES
MAX_TOTAL_BYTES = _impl.MAX_TOTAL_BYTES
Finding = _impl.Finding


def _open_stable(
    path: Path,
    flags: int,
) -> tuple[int, tuple[tuple[Path, os.stat_result], ...] | None]:
    return _confined_open_stable(
        path,
        flags,
        component_nofollow=_supports_component_nofollow(),
    )


def _read_workflow(
    path: Path,
    repository_root: Path,
) -> tuple[str | None, str | None]:
    try:
        text, _count = read_utf8_bounded(
            path,
            repository_root,
            MAX_WORKFLOW_BYTES,
        )
        return text, None
    except ConfinedReadError as error:
        if error.code == "input.too-large":
            return None, f"workflow exceeds {MAX_WORKFLOW_BYTES} byte limit"
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
            findings.append(
                Finding(
                    workflow_dir,
                    f"workflow count exceeds {MAX_WORKFLOW_FILES}",
                )
            )
            break
        entry_path = workflow_dir / entry.name
        try:
            metadata = entry.stat(follow_symlinks=False)
        except OSError as exc:
            findings.append(Finding(entry_path, f"cannot inspect workflow: {exc}"))
            continue
        if _is_link_or_reparse(metadata) or not stat.S_ISREG(metadata.st_mode):
            findings.append(
                Finding(
                    entry_path,
                    "workflow path must be a regular non-symlink file",
                )
            )
            continue
        total_bytes += metadata.st_size
        if total_bytes > MAX_TOTAL_BYTES:
            findings.append(
                Finding(
                    workflow_dir,
                    f"workflow bytes exceed {MAX_TOTAL_BYTES} total limit",
                )
            )
            break
        paths.append(entry_path)
    paths.sort(key=lambda item: item.name)
    return paths, findings


def workflow_paths(
    repository_root: Path,
) -> tuple[list[Path], list[Finding]]:
    workflow_dir = repository_root / ".github" / "workflows"
    if _supports_component_nofollow() and os.scandir in getattr(os, "supports_fd", set()):
        try:
            descriptor, _ = _open_stable(
                workflow_dir,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
        except FileNotFoundError:
            return [], [Finding(repository_root, "no GitHub Actions workflows found")]
        except OSError as exc:
            return [], [Finding(workflow_dir, f"cannot enumerate workflows: {exc}")]
        try:
            if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                return [], [
                    Finding(
                        workflow_dir,
                        "workflow directory must be a regular directory",
                    )
                ]
            with os.scandir(descriptor) as entries:
                return _collect_workflow_entries(entries, workflow_dir)
        except OSError as exc:
            return [], [Finding(workflow_dir, f"cannot enumerate workflows: {exc}")]
        finally:
            os.close(descriptor)

    try:
        snapshot = _component_snapshot(workflow_dir)
        if not stat.S_ISDIR(snapshot[-1][1].st_mode):
            return [], [
                Finding(
                    workflow_dir,
                    "workflow directory must be a regular directory",
                )
            ]
        with os.scandir(workflow_dir) as entries:
            paths, findings = _collect_workflow_entries(
                entries,
                workflow_dir,
            )
        if not _snapshot_is_current(snapshot):
            return [], [
                Finding(
                    workflow_dir,
                    "workflow directory identity changed while enumerating",
                )
            ]
        return paths, findings
    except FileNotFoundError:
        return [], [Finding(repository_root, "no GitHub Actions workflows found")]
    except OSError as exc:
        return [], [Finding(workflow_dir, f"cannot enumerate workflows: {exc}")]


def _permissions_write(value: object) -> bool:
    return _impl._permission_has_write(dict(value) if isinstance(value, Mapping) else value)


def _privileged_local_reusable_findings(
    path: Path,
    repository_root: Path,
) -> list[Finding]:
    text, error = _read_workflow(path, repository_root)
    if error or text is None:
        return []
    try:
        document = yaml.load(text, Loader=_impl._UniqueKeyLoader)
    except yaml.YAMLError:
        return []
    if not isinstance(document, Mapping):
        return []
    jobs = document.get("jobs")
    if not isinstance(jobs, Mapping):
        return []
    findings: list[Finding] = []
    for job_name, raw_job in jobs.items():
        if not isinstance(raw_job, Mapping):
            continue
        reusable = raw_job.get("uses")
        effective_permissions = raw_job.get("permissions", document.get("permissions"))
        if (
            isinstance(reusable, str)
            and reusable.startswith("./.github/workflows/")
            and _permissions_write(effective_permissions)
        ):
            findings.append(
                Finding(
                    path,
                    f"job {job_name}: write-enabled local reusable workflow "
                    "calls are forbidden until the called workflow is "
                    "recursively audited",
                )
            )
    return findings


def audit_workflow(
    path: Path,
    repository_root: Path | None = None,
    *,
    profile: str | None = None,
) -> list[Finding]:
    root = (repository_root or path.parent).resolve()
    findings = _impl.audit_workflow(
        path,
        root,
        reader=_read_workflow,
        profile=profile,
    )
    findings.extend(_privileged_local_reusable_findings(path, root))
    return findings


def _repository_profiles(
    repository_root: Path,
) -> tuple[dict[str, str], list[Finding]]:
    policy_path = repository_root / POLICY_PATH
    if not os.path.lexists(policy_path):
        return {}, []
    try:
        raw_text, _count = read_utf8_bounded(
            policy_path,
            repository_root,
            MAX_POLICY_BYTES,
        )
        document = yaml.load(raw_text, Loader=_impl._UniqueKeyLoader)
    except ConfinedReadError as error:
        return {}, [
            Finding(
                policy_path,
                f"cannot read workflow policy safely: {error.message}",
            )
        ]
    except yaml.YAMLError as error:
        return {}, [Finding(policy_path, f"cannot parse workflow policy: {error}")]
    if not isinstance(document, Mapping) or document.get("schema_version") != 1:
        return {}, [
            Finding(
                policy_path,
                "workflow policy must be a schema_version 1 mapping",
            )
        ]
    if set(document) != {"schema_version", "workflows"}:
        return {}, [Finding(policy_path, "workflow policy contains unsupported fields")]
    raw_workflows = document.get("workflows")
    if not isinstance(raw_workflows, Mapping):
        return {}, [Finding(policy_path, "workflow policy workflows must be a mapping")]

    profiles: dict[str, str] = {}
    findings: list[Finding] = []
    for raw_path, raw_profile in raw_workflows.items():
        if not isinstance(raw_path, str) or not isinstance(raw_profile, str):
            findings.append(
                Finding(
                    policy_path,
                    "workflow policy paths and profiles must be strings",
                )
            )
            continue
        candidate = Path(raw_path)
        if (
            candidate.is_absolute()
            or "\\" in raw_path
            or ".." in candidate.parts
            or candidate.parts[:2] != (".github", "workflows")
            or candidate.suffix.casefold() not in _impl._WORKFLOW_SUFFIXES
        ):
            findings.append(
                Finding(
                    policy_path,
                    f"invalid governed workflow path: {raw_path}",
                )
            )
            continue
        selected_profile = raw_profile.casefold()
        if selected_profile not in _impl._PROFILES:
            findings.append(
                Finding(
                    policy_path,
                    f"unknown profile for {raw_path}: {raw_profile}",
                )
            )
            continue
        profiles[candidate.as_posix()] = selected_profile
    return profiles, findings


def audit_repository(repository_root: Path) -> list[Finding]:
    root = repository_root.resolve()
    paths, findings = workflow_paths(root)
    profiles, policy_findings = _repository_profiles(root)
    findings.extend(policy_findings)
    discovered = {path.relative_to(root).as_posix() for path in paths}
    for governed_path in sorted(set(profiles) - discovered):
        findings.append(
            Finding(
                root / POLICY_PATH,
                f"governed workflow does not exist: {governed_path}",
            )
        )
    for path in paths:
        relative = path.relative_to(root).as_posix()
        findings.extend(audit_workflow(path, root, profile=profiles.get(relative)))
    return findings


_event_names = _impl._event_names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "repository_root",
        nargs="?",
        type=Path,
        default=Path.cwd(),
    )
    parser.add_argument(
        "--profile",
        choices=("pull-request", "trusted-ci", "protected-release"),
        help="Override profile when auditing one workflow path",
    )
    parser.add_argument(
        "--workflow",
        type=Path,
        help="Audit one workflow instead of repository discovery",
    )
    args = parser.parse_args()
    findings = (
        audit_workflow(
            args.workflow,
            args.repository_root,
            profile=args.profile,
        )
        if args.workflow is not None
        else audit_repository(args.repository_root)
    )
    if findings:
        for finding in findings:
            print(f"ERROR: {finding.render()}")
        return 1
    print("GitHub Actions policy: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

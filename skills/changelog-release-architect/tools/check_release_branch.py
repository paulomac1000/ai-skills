#!/usr/bin/env python3
"""Validate one-version-per-release-boundary history and changelog alignment."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tomllib
from collections.abc import Iterable
from pathlib import Path

import yaml

SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?$")
PY_VERSION = re.compile(r"^\s*__version__\s*=\s*['\"]([^'\"]+)['\"]\s*$", re.MULTILINE)
HEADING = re.compile(r"^##\s+\[?(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)\]?(?:\s+[-—].*)?\s*$", re.MULTILINE)


def _git(root: Path, *args: str, allow_failure: bool = False) -> str | None:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode == 0:
        return completed.stdout
    if allow_failure:
        return None
    detail = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
    raise ValueError(detail)


def _show(root: Path, revision: str, path: str) -> str | None:
    return _git(root, "show", f"{revision}:{path}", allow_failure=True)


def _parse_version(path: str, text: str) -> str:
    suffix = Path(path).suffix.casefold()
    if suffix in {".yaml", ".yml"}:
        value = yaml.safe_load(text)
        if not isinstance(value, dict) or not isinstance(value.get("version"), str):
            raise ValueError(f"{path}: top-level version is missing")
        return value["version"]
    if suffix == ".toml":
        value = tomllib.loads(text)
        project = value.get("project")
        if not isinstance(project, dict) or not isinstance(project.get("version"), str):
            raise ValueError(f"{path}: project.version is missing")
        return project["version"]
    if suffix == ".json":
        value = json.loads(text)
        if not isinstance(value, dict) or not isinstance(value.get("version"), str):
            raise ValueError(f"{path}: top-level version is missing")
        return value["version"]
    if suffix == ".py":
        match = PY_VERSION.search(text)
        if not match:
            raise ValueError(f"{path}: __version__ is missing")
        return match.group(1)
    value = text.strip()
    if not value:
        raise ValueError(f"{path}: version file is empty")
    return value


def _stable_triplet(value: str) -> tuple[int, int, int] | None:
    match = SEMVER.fullmatch(value)
    if not match or match.group(4):
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _direct_transition(base: str, target: str) -> bool:
    old = _stable_triplet(base)
    new = _stable_triplet(target)
    if old is None or new is None:
        return True
    major, minor, patch = old
    return new in {
        (major, minor, patch + 1),
        (major, minor + 1, 0),
        (major + 1, 0, 0),
    }


def _collapse(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if not result or result[-1] != value:
            result.append(value)
    return result


def validate_release_branch(
    root: Path,
    base_ref: str,
    version_paths: Iterable[str],
    changelog_path: str | None = "CHANGELOG.md",
) -> list[str]:
    root = root.resolve()
    findings: list[str] = []
    try:
        merge_base_output = _git(root, "merge-base", base_ref, "HEAD")
        assert merge_base_output is not None
        merge_base = merge_base_output.strip()
    except (OSError, subprocess.SubprocessError, ValueError, AssertionError) as exc:
        return [f"BASE_REF_AMBIGUOUS: cannot resolve merge base for {base_ref}: {exc}"]

    current_versions: dict[str, str] = {}
    baseline_versions: dict[str, str] = {}
    for relative in sorted(set(version_paths)):
        current_path = root / relative
        if not current_path.is_file():
            base_text = _show(root, merge_base, relative)
            if base_text is not None:
                findings.append(f"VERSION_SOURCE_CONFLICT: {relative} was removed from the candidate")
            continue
        try:
            current_versions[relative] = _parse_version(relative, current_path.read_text(encoding="utf-8"))
        except (
            OSError,
            UnicodeError,
            ValueError,
            json.JSONDecodeError,
            tomllib.TOMLDecodeError,
            yaml.YAMLError,
        ) as exc:
            findings.append(f"VERSION_SOURCE_CONFLICT: {exc}")
            continue

        base_text = _show(root, merge_base, relative)
        if base_text is None:
            continue
        try:
            base_version = _parse_version(relative, base_text)
            baseline_versions[relative] = base_version
            commits_output = _git(root, "rev-list", "--reverse", f"{merge_base}..HEAD", "--", relative) or ""
            versions = [base_version]
            for commit in commits_output.splitlines():
                text = _show(root, commit.strip(), relative)
                if text is not None:
                    versions.append(_parse_version(relative, text))
            transitions = _collapse(versions)
            if len(transitions) > 2:
                findings.append(f"MULTIPLE_VERSION_TRANSITIONS: {relative} contains {' -> '.join(transitions)}")
            target = current_versions[relative]
            if target != base_version and not _direct_transition(base_version, target):
                findings.append(
                    "VERSION_SOURCE_CONFLICT: "
                    f"{relative} target {target} is not one direct SemVer transition from {base_version}"
                )
        except (
            OSError,
            UnicodeError,
            ValueError,
            json.JSONDecodeError,
            tomllib.TOMLDecodeError,
            yaml.YAMLError,
        ) as exc:
            findings.append(f"VERSION_SOURCE_CONFLICT: {relative}: {exc}")

    current_set = set(current_versions.values())
    if len(current_set) > 1:
        detail = ", ".join(f"{path}={value}" for path, value in sorted(current_versions.items()))
        findings.append(f"VERSION_MIRROR_DRIFT: current version sources disagree: {detail}")

    base_set = set(baseline_versions.values())
    if len(base_set) > 1:
        detail = ", ".join(f"{path}={value}" for path, value in sorted(baseline_versions.items()))
        findings.append(f"VERSION_SOURCE_CONFLICT: baseline version sources disagree: {detail}")

    mirror_target = next(iter(current_set)) if len(current_set) == 1 else None
    baseline = next(iter(base_set)) if len(base_set) == 1 else None

    if changelog_path:
        current_changelog = root / changelog_path
        if current_changelog.is_file():
            try:
                current_headings = set(HEADING.findall(current_changelog.read_text(encoding="utf-8")))
                base_changelog = _show(root, merge_base, changelog_path)
                base_headings = set(HEADING.findall(base_changelog or ""))
                introduced = sorted(current_headings - base_headings)
                if len(introduced) > 1:
                    findings.append(f"MULTIPLE_RELEASE_HEADINGS: {changelog_path} introduces {', '.join(introduced)}")
                elif len(introduced) == 1 and mirror_target and introduced[0] != mirror_target:
                    findings.append(
                        f"VERSION_MIRROR_DRIFT: changelog target {introduced[0]} does not match version target {mirror_target}"
                    )
                elif len(introduced) == 1 and baseline and mirror_target == baseline:
                    findings.append(
                        f"VERSION_SOURCE_CONFLICT: changelog introduces {introduced[0]} without a version transition"
                    )
            except (OSError, UnicodeError) as exc:
                findings.append(f"CHANGELOG_EVIDENCE_MISSING: cannot read {changelog_path}: {exc}")

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--version-path", action="append", default=[])
    parser.add_argument("--changelog", default="CHANGELOG.md")
    args = parser.parse_args(argv)
    if not args.version_path:
        parser.error("at least one --version-path is required")
    findings = validate_release_branch(args.repository_root, args.base, args.version_path, args.changelog or None)
    for finding in findings:
        print(f"ERROR: {finding}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

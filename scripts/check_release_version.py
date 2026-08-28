#!/usr/bin/env python3
"""Validate stable skill bumps and the repository release-boundary contract."""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol, cast

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    # ``python scripts/check_release_version.py`` places only ``scripts/`` on
    # sys.path. The exact CI command must work without caller PYTHONPATH state.
    sys.path.insert(0, str(ROOT))

from contracts.semver import parse_semver  # noqa: E402

RELEASE_TOOL = ROOT / "skills/changelog-release-architect/tools/check_release_branch.py"


class ReleaseTool(Protocol):
    """Typed surface exported by the canonical release validator."""

    def validate_release_branch(
        self,
        root: Path,
        base_ref: str,
        version_paths: Iterable[str],
        changelog_path: str | None = "CHANGELOG.md",
    ) -> list[str]: ...


def _load_release_tool() -> ReleaseTool:
    spec = importlib.util.spec_from_file_location("changelog_release_check", RELEASE_TOOL)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load release validator: {RELEASE_TOOL}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return cast(ReleaseTool, module)


def _git_show(base: str, path: str) -> str | None:
    completed = subprocess.run(  # noqa: S603 - fixed git executable, explicit revision/path.
        ["git", "show", f"{base}:{path}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.stdout if completed.returncode == 0 else None


def _git_output(argv: list[str], operation: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed git executable and explicit argv.
        ["git", *argv],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise ValueError(f"{operation}: {detail}")
    return completed.stdout


def _ensure_history(base: str) -> None:
    completed = subprocess.run(  # noqa: S603 - fixed git executable and trusted CI base SHA.
        ["git", "merge-base", base, "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode == 0:
        return
    shallow = ROOT / ".git/shallow"
    if shallow.is_file():
        _git_output(["fetch", "--no-tags", "--unshallow", "origin"], "cannot fetch release history")
    _git_output(["merge-base", base, "HEAD"], "cannot resolve release merge base")


def _changed_paths(base: str) -> set[str]:
    output = _git_output(["diff", "--name-only", base, "HEAD"], "cannot compare release base")
    return {line.strip() for line in output.splitlines() if line.strip()}


def _base_manifest_paths(base: str) -> set[str]:
    output = _git_output(
        ["ls-tree", "-r", "--name-only", base, "--", "skills"],
        "cannot enumerate stable skills at release base",
    )
    return {
        line.strip()
        for line in output.splitlines()
        if line.strip().startswith("skills/") and line.strip().endswith("/manifest.yaml")
    }


def _current_manifest_paths() -> set[str]:
    return {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "skills").glob("*/manifest.yaml")
        if path.is_file()
    }


def _stable_triplet(value: object, skill_name: str) -> tuple[int, int, int]:
    parsed = parse_semver(value)
    if parsed.prerelease:
        raise ValueError(f"{skill_name}: stable skill version must not be a prerelease")
    return parsed.major, parsed.minor, parsed.patch


def validate_version_bumps(base: str) -> list[str]:
    try:
        _ensure_history(base)
        changed = _changed_paths(base)
        base_manifests = _base_manifest_paths(base)
        current_manifests = _current_manifest_paths()
        release_tool = _load_release_tool()
    except (OSError, subprocess.SubprocessError, ValueError, ImportError) as exc:
        return [f"release base could not be validated: {exc}"]

    findings = release_tool.validate_release_branch(
        ROOT,
        base,
        sorted(base_manifests | current_manifests),
        "CHANGELOG.md",
    )
    shared_contract_change = any(path.startswith("contracts/") for path in changed)

    for relative in sorted(base_manifests):
        old_text = _git_show(base, relative)
        if old_text is None:
            findings.append(f"{relative}: base manifest could not be loaded")
            continue
        previous = yaml.safe_load(old_text)
        if not isinstance(previous, dict) or previous.get("maturity") != "stable":
            continue
        skill_name = Path(relative).parent.name
        current_path = ROOT / relative
        if not current_path.is_file():
            findings.append(f"{skill_name}: previously stable skill manifest was removed")
            continue
        current = yaml.safe_load(current_path.read_text(encoding="utf-8"))
        if not isinstance(current, dict) or current.get("maturity") != "stable":
            findings.append(f"{skill_name}: previously stable skill cannot be downgraded from stable maturity")
            continue
        try:
            previous_version = _stable_triplet(previous.get("version"), skill_name)
            current_version = _stable_triplet(current.get("version"), skill_name)
        except ValueError as exc:
            findings.append(str(exc))
            continue
        if current_version < previous_version:
            findings.append(f"{skill_name}: stable skill version must not decrease")
            continue
        skill_prefix = f"skills/{skill_name}/"
        semantic_change = shared_contract_change or any(path.startswith(skill_prefix) for path in changed)
        if semantic_change and current_version <= previous_version:
            findings.append(f"{skill_name}: stable shipped content changed without increasing the skill version")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    args = parser.parse_args(argv)
    findings = validate_version_bumps(args.base)
    for finding in findings:
        print(f"ERROR: {finding}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Require stable skill versions to change when their shipped implementation changes."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import yaml

from contracts.semver import parse_semver

ROOT = Path(__file__).resolve().parents[1]


def _git_show(base: str, path: str) -> str | None:
    completed = subprocess.run(  # noqa: S603 - fixed git executable, validated revision supplied by trusted CI.
        ["git", "show", f"{base}:{path}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.stdout if completed.returncode == 0 else None


def _changed_paths(base: str) -> set[str]:
    # CI fetches the immutable base object shallowly. Comparing the two endpoint
    # trees does not require merge-base history and is exactly what this gate needs.
    completed = subprocess.run(  # noqa: S603
        ["git", "diff", "--name-only", base, "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return {line.strip() for line in completed.stdout.splitlines() if line.strip()}


def _base_manifest_paths(base: str) -> set[str]:
    completed = subprocess.run(  # noqa: S603
        ["git", "ls-tree", "-r", "--name-only", base, "--", "skills"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return {
        line.strip()
        for line in completed.stdout.splitlines()
        if line.strip().startswith("skills/") and line.strip().endswith("/manifest.yaml")
    }


def _stable_triplet(value: object, skill_name: str) -> tuple[int, int, int]:
    parsed = parse_semver(value)
    if parsed.prerelease:
        raise ValueError(f"{skill_name}: stable skill version must not be a prerelease")
    return parsed.major, parsed.minor, parsed.patch


def validate_version_bumps(base: str) -> list[str]:
    changed = _changed_paths(base)
    shared_contract_change = any(path.startswith("contracts/") for path in changed)
    findings: list[str] = []
    for relative in sorted(_base_manifest_paths(base)):
        old_text = _git_show(base, relative)
        if old_text is None:
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

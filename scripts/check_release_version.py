#!/usr/bin/env python3
"""Require stable skill versions to change when their shipped implementation changes."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import yaml

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


def validate_version_bumps(base: str) -> list[str]:
    changed = _changed_paths(base)
    shared_contract_change = any(path.startswith("contracts/") for path in changed)
    findings: list[str] = []
    for manifest_path in sorted((ROOT / "skills").glob("*/manifest.yaml")):
        relative = manifest_path.relative_to(ROOT).as_posix()
        current = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(current, dict) or current.get("maturity") != "stable":
            continue
        old_text = _git_show(base, relative)
        if old_text is None:
            continue
        previous = yaml.safe_load(old_text)
        if not isinstance(previous, dict):
            continue
        skill_prefix = f"skills/{manifest_path.parent.name}/"
        semantic_change = shared_contract_change or any(path.startswith(skill_prefix) for path in changed)
        if semantic_change and current.get("version") == previous.get("version"):
            findings.append(f"{manifest_path.parent.name}: stable shipped content changed without a skill version bump")
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

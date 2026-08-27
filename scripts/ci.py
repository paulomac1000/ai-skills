#!/usr/bin/env python3
"""Run the production quality gates shared with GitHub Actions."""

from __future__ import annotations

import compileall
import json
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

from ci_environment import build_clean_environment, configured_passthrough
from quality_targets import (
    BANDIT_PATHS,
    POLICY_COVERAGE_PATHS,
    QUALITY_PATHS,
    SECURITY_BOUNDARY_BRANCH_COVERAGE_FLOORS,
    SECURITY_BOUNDARY_COVERAGE_FLOORS,
    TYPE_PATHS,
)
from select_lock import selected_lock

ROOT = Path(__file__).resolve().parents[1]
COMMAND_TIMEOUT_SECONDS = 900


def run(*command: str) -> None:
    """Run one visible, bounded quality command from the repository root."""
    print("+", " ".join(command), flush=True)
    environment = build_clean_environment(extra_allowed=configured_passthrough())
    subprocess.run(command, cwd=ROOT, env=environment, check=True, timeout=COMMAND_TIMEOUT_SECONDS)


def _branch_coverage_percentage(report: Mapping[str, object], source_path: str) -> float:
    """Return branch-only coverage for one exact source path from coverage.py JSON."""
    raw_files = report.get("files")
    if not isinstance(raw_files, Mapping):
        raise RuntimeError("coverage JSON has no files mapping")
    files = {str(path).replace("\\", "/"): value for path, value in raw_files.items()}
    raw_file = files.get(source_path)
    if not isinstance(raw_file, Mapping):
        raise RuntimeError(f"coverage JSON has no measured file {source_path}")
    raw_summary = raw_file.get("summary")
    if not isinstance(raw_summary, Mapping):
        raise RuntimeError(f"coverage JSON has no summary for {source_path}")
    total = raw_summary.get("num_branches")
    covered = raw_summary.get("covered_branches")
    if type(total) is not int or type(covered) is not int or total <= 0 or not 0 <= covered <= total:
        raise RuntimeError(f"coverage JSON has invalid branch counters for {source_path}")
    return (covered * 100.0) / total


def _enforce_security_branch_coverage() -> None:
    """Fail when a security-boundary module drops below its branch-only baseline."""
    with tempfile.TemporaryDirectory(prefix="ai-skills-branch-coverage-") as temporary:
        report_path = Path(temporary) / "coverage.json"
        run(sys.executable, "-m", "coverage", "json", "-o", str(report_path))
        document = json.loads(report_path.read_text(encoding="utf-8"))
        if not isinstance(document, Mapping):
            raise RuntimeError("coverage JSON root must be an object")
        for source_path, floor in SECURITY_BOUNDARY_BRANCH_COVERAGE_FLOORS:
            percentage = _branch_coverage_percentage(document, source_path)
            print(f"branch coverage {source_path}: {percentage:.2f}% (required {floor}%)", flush=True)
            if percentage + 1e-9 < floor:
                raise RuntimeError(
                    f"branch coverage for {source_path} is {percentage:.2f}%; required minimum is {floor}%"
                )


def main() -> int:
    """Return zero only when source, policy, security, docs, locks, and tests pass."""
    for directory in (ROOT / "contracts", ROOT / "scripts", ROOT / "skills"):
        if not compileall.compile_dir(directory, quiet=1):
            return 1

    run(sys.executable, "-m", "pip", "check")
    run(sys.executable, "-m", "ruff", "check", *QUALITY_PATHS)
    run(sys.executable, "-m", "ruff", "format", "--check", *QUALITY_PATHS)
    run(sys.executable, "-m", "mypy", *TYPE_PATHS)
    run(sys.executable, "-m", "bandit", "-q", "-lll", "-iii", "-r", *BANDIT_PATHS)
    run(sys.executable, "-m", "pip_audit", "-r", str(selected_lock()), "--progress-spinner", "off")
    run(
        sys.executable,
        "skills/afds-doc-writer/validate.py",
        "README.md",
        "RECOVERY_AUDIT.md",
        "contracts",
        "skills",
    )
    run(sys.executable, "contracts/validate_consumer_feedback.py")
    run(
        sys.executable,
        "-m",
        "coverage",
        "run",
        "--branch",
        "-m",
        "pytest",
        "-q",
        "-m",
        "not container",
    )
    run(
        sys.executable,
        "-m",
        "coverage",
        "report",
        f"--include={','.join(POLICY_COVERAGE_PATHS)}",
        "--fail-under=80",
    )
    for path, floor in SECURITY_BOUNDARY_COVERAGE_FLOORS:
        run(
            sys.executable,
            "-m",
            "coverage",
            "report",
            f"--include={path}",
            f"--fail-under={floor}",
        )
    _enforce_security_branch_coverage()
    run(
        sys.executable,
        "-m",
        "coverage",
        "report",
        (
            "--include=skills/mcp-server-architect/tools/generate_python_server.py,"
            "skills/mcp-server-architect/tools/generate_python_server_impl.py,"
            "skills/mcp-server-architect/tools/generate_dotnet_server.py"
        ),
        "--fail-under=85",
    )
    run(
        sys.executable,
        "-m",
        "coverage",
        "report",
        "--include=scripts/*.py",
        "--fail-under=75",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

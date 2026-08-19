#!/usr/bin/env python3
"""Run the production quality gates shared with GitHub Actions."""

from __future__ import annotations

import compileall
import subprocess
import sys
from pathlib import Path

from ci_environment import build_clean_environment, configured_passthrough
from quality_targets import (
    BANDIT_PATHS,
    POLICY_COVERAGE_PATHS,
    QUALITY_PATHS,
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

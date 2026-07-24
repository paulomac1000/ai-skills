#!/usr/bin/env python3
"""Run the production quality gates shared with GitHub Actions."""

from __future__ import annotations

import compileall
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMAND_TIMEOUT_SECONDS = 900
QUALITY_PATHS = (
    "scripts/ci.py",
    "skills/afds-doc-writer/validate.py",
    "skills/mcp-server-consumer/tools",
    "skills/mcp-server-architect/tools/generate_python_server.py",
    "skills/mcp-server-architect/tools/generate_dotnet_server.py",
)
TYPE_PATHS = (
    "scripts/ci.py",
    "skills/afds-doc-writer/validate.py",
    "skills/mcp-server-consumer/tools/decision_engine.py",
    "skills/mcp-server-architect/tools/generate_python_server.py",
    "skills/mcp-server-architect/tools/generate_dotnet_server.py",
)


def run(*command: str) -> None:
    """Run one visible, bounded quality command from the repository root."""
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True, timeout=COMMAND_TIMEOUT_SECONDS)


def main() -> int:
    """Return zero only when source, policy, security, docs, and tests pass."""
    for directory in (ROOT / "scripts", ROOT / "skills"):
        if not compileall.compile_dir(directory, quiet=1):
            return 1

    run(sys.executable, "-m", "ruff", "check", *QUALITY_PATHS)
    run(sys.executable, "-m", "ruff", "format", "--check", *QUALITY_PATHS)
    run(sys.executable, "-m", "mypy", *TYPE_PATHS)
    run(
        sys.executable,
        "-m",
        "bandit",
        "-q",
        "-lll",
        "-iii",
        "-r",
        "scripts",
        "skills/afds-doc-writer",
        "skills/mcp-server-consumer/tools",
        "skills/mcp-server-architect/tools",
    )
    run(sys.executable, "-m", "pip_audit", "-r", "requirements-dev.txt", "--progress-spinner", "off")
    run(
        sys.executable,
        "skills/afds-doc-writer/validate.py",
        "README.md",
        "RECOVERY_AUDIT.md",
        "skills",
    )
    run(sys.executable, "-m", "coverage", "run", "--branch", "-m", "pytest", "-q")
    run(
        sys.executable,
        "-m",
        "coverage",
        "report",
        "--include=skills/afds-doc-writer/*.py,skills/mcp-server-consumer/tools/*.py",
        "--fail-under=80",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

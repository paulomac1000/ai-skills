#!/usr/bin/env python3
"""Run the production quality gates shared with GitHub Actions."""

from __future__ import annotations

import compileall
import subprocess
import sys
from pathlib import Path

from select_lock import selected_lock

ROOT = Path(__file__).resolve().parents[1]
COMMAND_TIMEOUT_SECONDS = 900
QUALITY_PATHS = (
    "contracts",
    "scripts/ci.py",
    "scripts/install_locked.py",
    "scripts/select_lock.py",
    "skills/afds-doc-writer/validate.py",
    "skills/agents-md-architect/tools/discover_repository.py",
    "skills/agents-md-architect/tools/audit_agents_md.py",
    "skills/agents-md-architect/tools/validate_agents_md.py",
    "skills/mcp-server-consumer/tools",
    "skills/mcp-server-architect/tools/generate_python_server.py",
    "skills/mcp-server-architect/tools/generate_python_server_impl.py",
    "skills/mcp-server-architect/tools/generate_dotnet_server.py",
)
TYPE_PATHS = (
    "contracts/semver.py",
    "contracts/evidence.py",
    "contracts/validate_adoption.py",
    "contracts/write_evidence_report.py",
    "contracts/run_evidence_command.py",
    "scripts/ci.py",
    "scripts/install_locked.py",
    "scripts/select_lock.py",
    "skills/afds-doc-writer/validate.py",
    "skills/agents-md-architect/tools/discover_repository.py",
    "skills/agents-md-architect/tools/audit_agents_md.py",
    "skills/agents-md-architect/tools/validate_agents_md.py",
    "skills/mcp-server-consumer/tools/decision_engine.py",
    "skills/mcp-server-architect/tools/generate_python_server.py",
    "skills/mcp-server-architect/tools/generate_python_server_impl.py",
    "skills/mcp-server-architect/tools/generate_dotnet_server.py",
)


def run(*command: str) -> None:
    """Run one visible, bounded quality command from the repository root."""
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True, timeout=COMMAND_TIMEOUT_SECONDS)


def main() -> int:
    """Return zero only when source, policy, security, docs, locks, and tests pass."""
    for directory in (ROOT / "contracts", ROOT / "scripts", ROOT / "skills"):
        if not compileall.compile_dir(directory, quiet=1):
            return 1

    run(sys.executable, "-m", "pip", "check")
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
        "contracts",
        "scripts",
        "skills/afds-doc-writer",
        "skills/agents-md-architect/tools",
        "skills/mcp-server-consumer/tools",
        "skills/mcp-server-architect/tools",
    )
    run(sys.executable, "-m", "pip_audit", "-r", str(selected_lock()), "--progress-spinner", "off")
    run(
        sys.executable,
        "skills/afds-doc-writer/validate.py",
        "README.md",
        "RECOVERY_AUDIT.md",
        "contracts",
        "skills",
    )
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
        "--include=contracts/*.py,skills/afds-doc-writer/*.py,skills/agents-md-architect/tools/*.py,skills/mcp-server-consumer/tools/*.py",
        "--fail-under=80",
    )
    run(
        sys.executable,
        "-m",
        "coverage",
        "report",
        "--include=skills/mcp-server-architect/tools/generate_python_server.py,skills/mcp-server-architect/tools/generate_python_server_impl.py,skills/mcp-server-architect/tools/generate_dotnet_server.py",
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

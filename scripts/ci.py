#!/usr/bin/env python3
"""Run the deterministic checks used by local development and GitHub Actions."""

from __future__ import annotations

import compileall
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMAND_TIMEOUT_SECONDS = 300


def run(*command: str) -> None:
    """Run one trusted repository command with a bounded execution time."""
    print("+", " ".join(command), flush=True)
    subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )


def main() -> int:
    """Compile sources, validate documentation, and execute the test suite."""
    for directory in (ROOT / "scripts", ROOT / "skills"):
        if not compileall.compile_dir(directory, quiet=1):
            return 1

    run(sys.executable, "skills/afds-doc-writer/validate.py", "README.md", "skills")
    run(sys.executable, "-m", "pytest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

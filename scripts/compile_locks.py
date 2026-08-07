#!/usr/bin/env python3
"""Regenerate all hashed Python locks for the active supported target tuple."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from select_lock import lock_id

ROOT = Path(__file__).resolve().parents[1]
GENERATOR_LOCK_ROOT = ROOT / "skills/mcp-server-architect/locks"


def _compile(source: Path, output: Path) -> None:
    command = [
        sys.executable,
        "-m",
        "piptools",
        "compile",
        "--allow-unsafe",
        "--generate-hashes",
        "--strip-extras",
        f"--output-file={output.relative_to(ROOT)}",
        str(source.relative_to(ROOT)),
    ]
    subprocess.run(command, cwd=ROOT, check=True, timeout=900)


def outputs_for_target(identifier: str) -> tuple[Path, Path, Path]:
    """Return root-dev, generated-runtime, and generated-dev lock paths."""
    return (
        ROOT / f"requirements-dev-{identifier}.lock",
        GENERATOR_LOCK_ROOT / f"runtime-{identifier}.lock",
        GENERATOR_LOCK_ROOT / f"dev-{identifier}.lock",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform")
    parser.add_argument("--architecture")
    parser.add_argument("--python-version")
    args = parser.parse_args(argv)

    identifier = lock_id(
        args.platform or sys.platform,
        args.architecture,
        args.python_version,
    )
    root_dev, runtime, generator_dev = outputs_for_target(identifier)
    _compile(ROOT / "requirements-dev.in", root_dev)
    _compile(GENERATOR_LOCK_ROOT / "python-runtime.in", runtime)
    _compile(GENERATOR_LOCK_ROOT / "python-dev.in", generator_dev)
    for path in (root_dev, runtime, generator_dev):
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(
                f"lock compiler did not produce {path.relative_to(ROOT)}"
            )
    print(identifier)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

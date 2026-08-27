#!/usr/bin/env python3
"""Compile deterministic lock files for the current native target only."""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from select_lock import lock_id, normalize_architecture, normalize_platform, normalize_python_version

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


def _native_target() -> tuple[str, str, str]:
    return (
        normalize_platform(sys.platform),
        normalize_architecture(platform.machine()),
        normalize_python_version(f"{sys.version_info.major}.{sys.version_info.minor}"),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform")
    parser.add_argument("--architecture")
    parser.add_argument("--python-version")
    args = parser.parse_args(argv)

    requested = (
        normalize_platform(args.platform or sys.platform),
        normalize_architecture(args.architecture or platform.machine()),
        normalize_python_version(args.python_version or f"{sys.version_info.major}.{sys.version_info.minor}"),
    )
    native = _native_target()
    if requested != native:
        parser.error(
            "lock compilation is native-only: requested "
            f"{requested[0]}/{requested[1]}/py{requested[2]} but interpreter is "
            f"{native[0]}/{native[1]}/py{native[2]}"
        )

    identifier = lock_id(*requested)
    root_dev, runtime, generator_dev = outputs_for_target(identifier)
    _compile(ROOT / "requirements-dev.in", root_dev)
    _compile(GENERATOR_LOCK_ROOT / "python-runtime.in", runtime)
    _compile(GENERATOR_LOCK_ROOT / "python-dev.in", generator_dev)
    for path in (root_dev, runtime, generator_dev):
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"lock compiler did not produce {path.relative_to(ROOT)}")
    print(identifier)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

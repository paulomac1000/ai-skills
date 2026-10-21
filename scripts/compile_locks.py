#!/usr/bin/env python3
"""Compile deterministic lock files for the current native target only.

The generator is the only supported way to produce a lock file. It also
verifies, in check mode, that the committed lock files are exactly what the
native regeneration produces, so a declared requirement can never ship with a
stale lock. The verification runs in an isolated workspace and never writes
to the committed locks.

The committed lock is the generator's starting constraint, so the check
compares the committed lock with the regeneration that the canonical
generator produces from the committed requirement. The upstream index is
mutable, so re-resolving every transitive version is a separate refresh
operation that proposes a diff, not a reproducibility verdict.
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    # ``python scripts/compile_locks.py`` places only ``scripts/`` on
    # sys.path. The exact CI command must work without caller PYTHONPATH state.
    sys.path.insert(0, str(ROOT))

from scripts.select_lock import (  # noqa: E402
    lock_id,
    normalize_architecture,
    normalize_platform,
    normalize_python_version,
)

GENERATOR_LOCK_ROOT = ROOT / "skills/mcp-server-architect/locks"

# The declared lock inputs and the lock each one produces, in the order the
# generator compiles them. The relative paths are the ones the generated
# header records, so the output is comparable byte for byte.
LOCK_SOURCES: tuple[tuple[str, str], ...] = (
    ("requirements-dev.in", "requirements-dev-{identifier}.lock"),
    (
        "skills/mcp-server-architect/locks/python-runtime.in",
        "skills/mcp-server-architect/locks/runtime-{identifier}.lock",
    ),
    (
        "skills/mcp-server-architect/locks/python-dev.in",
        "skills/mcp-server-architect/locks/dev-{identifier}.lock",
    ),
)


def _compile_in_workspace(workspace: Path, source_relative: str, output_relative: str) -> None:
    """Compile one declared lock inside a workspace.

    The relative paths are the ones the generated header records, so the
    output is comparable byte for byte with a committed lock. The compiler
    output is captured, so a passing check stays quiet and a failing one
    reports the compiler's own diagnostics.
    """
    output = workspace / output_relative
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "piptools",
        "compile",
        "--allow-unsafe",
        "--generate-hashes",
        "--strip-extras",
        f"--output-file={output_relative}",
        source_relative,
    ]
    subprocess.run(
        command,
        cwd=workspace,
        check=True,
        timeout=900,
        capture_output=True,
        text=True,
    )


def outputs_for_target(identifier: str, *, root: Path = ROOT) -> tuple[Path, Path, Path]:
    """Return root-dev, generated-runtime, and generated-dev lock paths."""
    return (
        root / f"requirements-dev-{identifier}.lock",
        root / "skills/mcp-server-architect/locks" / f"runtime-{identifier}.lock",
        root / "skills/mcp-server-architect/locks" / f"dev-{identifier}.lock",
    )


def _native_target() -> tuple[str, str, str]:
    return (
        normalize_platform(sys.platform),
        normalize_architecture(platform.machine()),
        normalize_python_version(f"{sys.version_info.major}.{sys.version_info.minor}"),
    )


def _mirror_inputs(root: Path, workspace: Path, identifier: str) -> list[str]:
    """Copy the declared lock inputs and the committed locks into a workspace.

    The committed lock is the generator's starting constraint, so the
    regeneration keeps the pinned versions instead of re-resolving a mutable
    upstream. The upstream index is not an immutable identity, so an exact
    byte-equality claim against a fresh resolution is not sound; the claim
    this check makes is that the committed lock is what the canonical
    generator produces from the committed requirement.
    """
    missing: list[str] = []
    for source_relative, output_relative in LOCK_SOURCES:
        source = root / source_relative
        if not source.is_file():
            missing.append(f"LOCK_INPUT_MISSING:{source_relative}")
            continue
        destination = workspace / source_relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        committed = root / output_relative.format(identifier=identifier)
        if committed.is_file():
            seed = workspace / output_relative.format(identifier=identifier)
            seed.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(committed, seed)
    return missing


def verify_lock_reproducibility(
    root: Path,
    identifier: str,
    *,
    compiler: Callable[[Path, str, str], None] | None = None,
    emit_dir: Path | None = None,
) -> list[str]:
    """Return the findings for committed locks that differ from a regeneration.

    The regeneration runs in an isolated workspace that mirrors the declared
    layout, so the committed lock files are never written to. A missing lock,
    a missing regeneration and a failed compilation are all findings, so the
    check fails closed rather than accepting an unproven lock. When
    `emit_dir` is given, the regenerated locks are copied there, so the same
    regeneration that produced the verdict is the evidence a repair uses.
    """
    findings: list[str] = []
    with tempfile.TemporaryDirectory(prefix="ai-skills-lock-check-") as temporary:
        workspace = Path(temporary) / "workspace"
        workspace.mkdir()
        findings.extend(_mirror_inputs(root, workspace, identifier))
        if findings:
            return findings
        for source_relative, output_relative in LOCK_SOURCES:
            resolved_output = output_relative.format(identifier=identifier)
            try:
                if compiler is None:
                    _compile_in_workspace(workspace, source_relative, resolved_output)
                else:
                    compiler(workspace, source_relative, resolved_output)
            except (OSError, subprocess.SubprocessError):
                findings.append(f"LOCK_COMPILE_FAILED:{resolved_output}")
                continue
            output = workspace / resolved_output
            if not output.is_file() or output.stat().st_size == 0:
                findings.append(f"LOCK_OUTPUT_MISSING:{resolved_output}")
                continue
            if emit_dir is not None:
                emitted = emit_dir / resolved_output
                emitted.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(output, emitted)
            committed = root / resolved_output
            if not committed.is_file():
                findings.append(f"LOCK_COMMITTED_MISSING:{resolved_output}")
                continue
            if committed.read_bytes() != output.read_bytes():
                findings.append(f"LOCK_REPRODUCIBILITY_DRIFT:{resolved_output}")
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform")
    parser.add_argument("--architecture")
    parser.add_argument("--python-version")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify that the committed locks equal a native regeneration, and write nothing",
    )
    parser.add_argument(
        "--emit-dir",
        type=Path,
        help="write the regenerated locks to this directory; used with --check",
    )
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
    if args.check:
        findings = verify_lock_reproducibility(ROOT, identifier, emit_dir=args.emit_dir)
        for finding in findings:
            print("LOCK_CHECK_FAILED: " + finding, file=sys.stderr)
        if findings:
            return 1
        print(f"lock reproducibility verified for {identifier}")
        return 0

    root_dev, runtime, generator_dev = outputs_for_target(identifier)
    for source_relative, output_relative in LOCK_SOURCES:
        _compile_in_workspace(ROOT, source_relative, output_relative.format(identifier=identifier))
    for path in (root_dev, runtime, generator_dev):
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"lock compiler did not produce {path.relative_to(ROOT)}")
    print(identifier)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

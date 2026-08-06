#!/usr/bin/env python3
"""Public entry point for the canonical Python MCP server generator."""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from collections.abc import Sequence
from pathlib import Path

_IMPLEMENTATION_PATH = Path(__file__).with_name("generate_python_server_impl.py")
_SPEC = importlib.util.spec_from_file_location("mcp_python_generator_implementation", _IMPLEMENTATION_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Cannot load generator implementation: {_IMPLEMENTATION_PATH}")
_implementation = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _implementation
_SPEC.loader.exec_module(_implementation)

PACKAGE_RE = _implementation.PACKAGE_NAME
SERVER_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,128}$")
RESERVED_PACKAGE_NAMES = _implementation.RESERVED_PACKAGE_NAMES
LOCK_NAMES = _implementation.LOCK_NAMES
LOCK_IDS = tuple(name.removeprefix("runtime-").removesuffix(".lock") for name in LOCK_NAMES if name.startswith("runtime-"))
SOURCE_NAMES = ("python-runtime.in", "python-dev.in")
project_files = _implementation.project_files
validate_generated_project = _implementation.validate_generated_project


def generate_project(destination: Path, package_name: str, server_name: str) -> list[Path]:
    """Render and atomically publish a project using the historical public argument order."""
    files = project_files(package_name, server_name)
    _implementation.generate_project(package_name, destination, server_name)
    return [Path(path) for path in sorted(files)]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("package_name")
    parser.add_argument("--server-name")
    args = parser.parse_args(argv)
    server_name = args.server_name or args.package_name.replace("_", " ").title()
    try:
        generate_project(args.destination, args.package_name, server_name)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    print(args.destination.resolve(strict=False))
    return 0


__all__ = [
    "PACKAGE_RE",
    "SERVER_RE",
    "RESERVED_PACKAGE_NAMES",
    "LOCK_IDS",
    "LOCK_NAMES",
    "SOURCE_NAMES",
    "project_files",
    "validate_generated_project",
    "generate_project",
    "main",
]

if __name__ == "__main__":
    raise SystemExit(main())

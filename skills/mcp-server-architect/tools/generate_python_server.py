#!/usr/bin/env python3
"""Public entry point for the canonical Python MCP server generator."""

from __future__ import annotations

import argparse
import importlib.util
import keyword
import os
import re
import shutil
import stat
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_IMPLEMENTATION_PATH = Path(__file__).with_name("generate_python_server_impl.py")
_SPEC = importlib.util.spec_from_file_location(
    "mcp_python_generator_implementation",
    _IMPLEMENTATION_PATH,
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Cannot load generator implementation: {_IMPLEMENTATION_PATH}")
_implementation = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _implementation
_SPEC.loader.exec_module(_implementation)

PACKAGE_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
SERVER_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,128}$")
_WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}
RESERVED_PACKAGE_NAMES = frozenset(sys.stdlib_module_names) | {
    "contracts",
    "mcp",
    "pytest",
    "scripts",
    "tests",
    "uvicorn",
    *_WINDOWS_RESERVED_NAMES,
}
LOCK_NAMES = _implementation.LOCK_NAMES
LOCK_IDS = tuple(
    name.removeprefix("runtime-").removesuffix(".lock") for name in LOCK_NAMES if name.startswith("runtime-")
)
SOURCE_NAMES = ("python-runtime.in", "python-dev.in")
_BASE_PROJECT_FILES = _implementation.project_files
validate_generated_project = _implementation.validate_generated_project
_FILE_ATTRIBUTE_REPARSE_POINT = 0x0400


def _validate_public_identity(package_name: str, server_name: str) -> None:
    if not PACKAGE_RE.fullmatch(package_name) or keyword.iskeyword(package_name):
        raise ValueError("package name must be a non-keyword matching ^[a-z][a-z0-9_]{1,63}$")
    if package_name.casefold() in RESERVED_PACKAGE_NAMES:
        raise ValueError(f"package name is reserved: {package_name}")
    if not SERVER_RE.fullmatch(server_name):
        raise ValueError("server name must contain 1-128 printable characters")


def project_files(package_name: str, server_name: str) -> dict[str, str]:
    """Return a validated rendered project while preserving the public helper."""
    _validate_public_identity(package_name, server_name)
    return _BASE_PROJECT_FILES(package_name, server_name)


_implementation_dynamic: Any = _implementation
_implementation_dynamic.project_files = project_files


def _is_link_or_reparse(metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)


def _reject_symlink_components(path: Path) -> None:
    """Reject symlink/reparse components in the lexical path without resolving through them."""
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if not os.path.lexists(current):
            break
        try:
            metadata = os.lstat(current)
        except OSError as exc:
            raise ValueError(f"cannot inspect destination component: {current}") from exc
        if _is_link_or_reparse(metadata):
            raise ValueError(f"destination path must not contain symlinks or reparse points: {current}")


def generate_project(
    destination: Path,
    package_name: str,
    server_name: str,
) -> list[Path]:
    """Render and atomically publish a project using the stable public API."""
    files = project_files(package_name, server_name)
    validate_generated_project(files, package_name)

    expanded = destination.expanduser()
    if os.path.lexists(expanded):
        raise FileExistsError(expanded)
    _reject_symlink_components(expanded)
    parent = expanded.parent.resolve(strict=False)
    parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_components(expanded)
    if not parent.is_dir():
        raise ValueError("destination parent must be a regular directory")
    destination = parent / expanded.name
    if os.path.lexists(destination):
        raise FileExistsError(destination)

    staging: Path | None = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=parent))
    try:
        _implementation._write_files(staging, files)
        _implementation._rename_noreplace(staging, destination)
        staging = None
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging)
    return [Path(path) for path in sorted(files)]


def build_parser() -> argparse.ArgumentParser:
    """Build a CLI supporting the canonical and explicit legacy syntax."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "legacy_package_name",
        nargs="?",
        help=(
            "Deprecated positional package name. Prefer --package so package "
            "identity cannot be confused with the destination."
        ),
    )
    parser.add_argument("--package", dest="package_name")
    parser.add_argument(
        "--name",
        "--server-name",
        dest="server_name",
        help="Human-readable MCP server name.",
    )
    return parser


def _resolved_identity(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> tuple[str, str]:
    explicit = args.package_name
    legacy = args.legacy_package_name
    if explicit and legacy and explicit != legacy:
        parser.error("package name was supplied twice with different values; use only --package")
    package_name = explicit or legacy
    if not package_name:
        parser.error("missing package name; use --package <package_name>")
    server_name = args.server_name or package_name.replace("_", " ").title()
    return package_name, server_name


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    package_name, server_name = _resolved_identity(parser, args)
    try:
        generate_project(args.destination, package_name, server_name)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Generated {args.destination.resolve(strict=False)}")
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
    "build_parser",
    "main",
]

if __name__ == "__main__":
    raise SystemExit(main())

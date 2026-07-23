#!/usr/bin/env python3
"""Generate a deterministic, production-shaped .NET MCP server baseline."""

from __future__ import annotations

import argparse
import ctypes
import errno
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

NAMESPACE_RE = re.compile(r"[A-Z][A-Za-z0-9]{1,62}$")
SERVER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{1,78}$")
RESERVED_NAMESPACES = frozenset({"System", "Microsoft", "ModelContextProtocol", "InventoryMcp"})
TEMPLATE_ROOT = Path(__file__).with_name("dotnet-template")
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1
_RENAME_EXCL = 0x00000004


def _validate(namespace: str, server_name: str) -> None:
    if not NAMESPACE_RE.fullmatch(namespace) or namespace in RESERVED_NAMESPACES:
        raise ValueError("namespace must be a non-reserved PascalCase identifier with 2-63 characters")
    if not SERVER_RE.fullmatch(server_name):
        raise ValueError("server name must be 2-79 safe display characters")


def _render(value: str, *, namespace: str, server_name: str) -> str:
    return value.replace("__NAMESPACE__", namespace).replace("__SERVER_NAME__", server_name)


def project_files(namespace: str, server_name: str) -> dict[str, str]:
    """Return every generated UTF-8 file keyed by its rendered relative path."""
    _validate(namespace, server_name)
    if not TEMPLATE_ROOT.is_dir():
        raise FileNotFoundError(f"template directory is missing: {TEMPLATE_ROOT}")

    files: dict[str, str] = {}
    for source in sorted(path for path in TEMPLATE_ROOT.rglob("*") if path.is_file()):
        relative = source.relative_to(TEMPLATE_ROOT).as_posix()
        if relative.endswith(".template"):
            relative = relative[: -len(".template")]
        rendered_path = _render(relative, namespace=namespace, server_name=server_name)
        content = _render(source.read_text(encoding="utf-8"), namespace=namespace, server_name=server_name)
        files[rendered_path] = content.rstrip() + "\n"
    if not files:
        raise RuntimeError("the .NET template is empty")
    return files


def _raise_rename_error(error_number: int, destination: Path) -> None:
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(error_number, "generation target already exists", destination)
    raise OSError(error_number, os.strerror(error_number), destination)


def _rename_noreplace(source: Path, destination: Path) -> None:
    """Atomically publish one directory without replacing any destination object."""
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)

    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise RuntimeError("atomic no-replace rename requires renameat2 on this Linux runtime")
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        renameat2.restype = ctypes.c_int
        if renameat2(_AT_FDCWD, source_bytes, _AT_FDCWD, destination_bytes, _RENAME_NOREPLACE) != 0:
            _raise_rename_error(ctypes.get_errno(), destination)
        return

    if sys.platform == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        renamex_np = getattr(libc, "renamex_np", None)
        if renamex_np is None:
            raise RuntimeError("atomic no-replace rename requires renamex_np on this macOS runtime")
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
        if renamex_np(source_bytes, destination_bytes, _RENAME_EXCL) != 0:
            _raise_rename_error(ctypes.get_errno(), destination)
        return

    if os.name == "nt":
        # Windows os.rename is no-replace and raises FileExistsError when dst exists.
        os.rename(source, destination)
        return

    raise RuntimeError("this platform has no configured atomic no-replace directory rename")


def generate_project(target: Path, namespace: str, server_name: str) -> list[Path]:
    """Create a complete project atomically and never replace an existing target."""
    expanded = target.expanduser()
    target = expanded.parent.resolve(strict=False) / expanded.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(target):
        raise FileExistsError(errno.EEXIST, "generation target already exists", target)

    files = project_files(namespace, server_name)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent))
    try:
        for relative, content in sorted(files.items()):
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8", newline="\n")

        _rename_noreplace(staging, target)
        staging = None
        return [Path(relative) for relative in sorted(files)]
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    generated = generate_project(args.target, args.namespace, args.name)
    print(f"generated {len(generated)} files in {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

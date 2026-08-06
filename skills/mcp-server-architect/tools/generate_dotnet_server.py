#!/usr/bin/env python3
"""Generate a deterministic, production-shaped .NET MCP server baseline."""

from __future__ import annotations

import argparse
import ctypes
import errno
import os
import platform
import re
import shutil
import stat
import tempfile
from pathlib import Path

_NAMESPACE_SEGMENT = r"[A-Z][A-Za-z0-9]{0,62}"
NAMESPACE_RE = re.compile(rf"{_NAMESPACE_SEGMENT}(?:\.{_NAMESPACE_SEGMENT})*$")
SERVER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{1,78}$")
RESERVED_NAMESPACE_ROOTS = frozenset({"System", "Microsoft", "ModelContextProtocol"})
RESERVED_NAMESPACES = RESERVED_NAMESPACE_ROOTS | {"InventoryMcp"}
TEMPLATE_ROOT = Path(__file__).with_name("dotnet-template")
SKILL_ROOT = Path(__file__).resolve().parent.parent
REPOSITORY_ROOT = SKILL_ROOT.parents[1]
CONTRACT_ROOT = REPOSITORY_ROOT / "contracts"
COPIED_CONTRACTS = ("capability-manifest.schema.json",)
MAX_TEMPLATE_BYTES = 2 * 1024 * 1024
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1
_RENAME_EXCL = 0x00000004


def _validate(namespace: str, server_name: str) -> None:
    """Validate portable project identity before touching the filesystem."""
    root = namespace.partition(".")[0]
    if (
        len(namespace) > 191
        or not NAMESPACE_RE.fullmatch(namespace)
        or namespace in RESERVED_NAMESPACES
        or root in RESERVED_NAMESPACE_ROOTS
    ):
        raise ValueError(
            "namespace must be 1-191 characters of dot-separated, "
            "non-reserved PascalCase identifiers"
        )
    if not SERVER_RE.fullmatch(server_name):
        raise ValueError("server name must be 2-79 safe display characters")


def _read_regular_utf8(path: Path, *, maximum: int = MAX_TEMPLATE_BYTES) -> str:
    """Read one bounded non-symlink UTF-8 template or contract."""
    if path.is_symlink():
        raise ValueError(f"generator input must not be a symlink: {path}")
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"generator input must be a regular file: {path}")
    if metadata.st_size > maximum:
        raise ValueError(f"generator input exceeds {maximum} bytes: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"generator input must be UTF-8: {path}") from exc


def _render(value: str, *, namespace: str, server_name: str) -> str:
    """Render one template path or body using the validated project identity."""
    return (
        value.replace("__NAMESPACE_LOWER__", namespace.lower())
        .replace("__NAMESPACE__", namespace)
        .replace("__SERVER_NAME__", server_name)
    )


def project_files(namespace: str, server_name: str) -> dict[str, str]:
    """Return every generated UTF-8 file keyed by its rendered relative path."""
    _validate(namespace, server_name)
    if not TEMPLATE_ROOT.is_dir() or TEMPLATE_ROOT.is_symlink():
        raise FileNotFoundError(
            f"template directory is missing or unsafe: {TEMPLATE_ROOT}"
        )

    files: dict[str, str] = {}
    for source in sorted(TEMPLATE_ROOT.rglob("*")):
        if source.is_dir():
            continue
        relative = source.relative_to(TEMPLATE_ROOT).as_posix()
        if relative.endswith(".template"):
            relative = relative[: -len(".template")]
        rendered_path = _render(
            relative,
            namespace=namespace,
            server_name=server_name,
        )
        if rendered_path in files:
            raise ValueError(f"duplicate generated path: {rendered_path}")
        content = _render(
            _read_regular_utf8(source),
            namespace=namespace,
            server_name=server_name,
        )
        files[rendered_path] = content.rstrip() + "\n"

    for contract_name in COPIED_CONTRACTS:
        destination = f"contracts/{contract_name}"
        if destination in files:
            raise ValueError(f"duplicate generated path: {destination}")
        files[destination] = (
            _read_regular_utf8(CONTRACT_ROOT / contract_name).rstrip() + "\n"
        )

    if not files:
        raise RuntimeError("the .NET template is empty")
    return files


def _raise_rename_error(error_number: int, destination: Path) -> None:
    """Translate platform rename errors without hiding unexpected failures."""
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(
            error_number,
            "generation target already exists",
            destination,
        )
    raise OSError(error_number, os.strerror(error_number), destination)


def _rename_noreplace(source: Path, destination: Path) -> None:
    """Atomically publish one directory without replacing any destination object."""
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)
    operating_system = platform.system()

    if operating_system == "Linux":
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise RuntimeError(
                "atomic no-replace rename requires renameat2 on this Linux runtime"
            )
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        if (
            renameat2(
                _AT_FDCWD,
                source_bytes,
                _AT_FDCWD,
                destination_bytes,
                _RENAME_NOREPLACE,
            )
            != 0
        ):
            _raise_rename_error(ctypes.get_errno(), destination)
        return

    if operating_system == "Darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        renamex_np = getattr(libc, "renamex_np", None)
        if renamex_np is None:
            raise RuntimeError(
                "atomic no-replace rename requires renamex_np on this macOS runtime"
            )
        renamex_np.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renamex_np.restype = ctypes.c_int
        if renamex_np(source_bytes, destination_bytes, _RENAME_EXCL) != 0:
            _raise_rename_error(ctypes.get_errno(), destination)
        return

    if operating_system == "Windows":
        os.rename(source, destination)
        return

    raise RuntimeError(
        "this platform has no configured atomic no-replace directory rename"
    )


def generate_project(target: Path, namespace: str, server_name: str) -> list[Path]:
    """Create a complete project atomically and never replace an existing target."""
    expanded = target.expanduser()
    target = expanded.parent.resolve(strict=False) / expanded.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(target):
        raise FileExistsError(
            errno.EEXIST,
            "generation target already exists",
            target,
        )

    files = project_files(namespace, server_name)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent)
    )
    published = False
    try:
        for relative, content in sorted(files.items()):
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8", newline="\n")

        _rename_noreplace(staging, target)
        published = True
        return [Path(relative) for relative in sorted(files)]
    finally:
        if not published:
            shutil.rmtree(staging, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser separately so command-line validation is testable."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--name", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Generate one project from validated command-line arguments."""
    args = build_parser().parse_args(argv)
    generated = generate_project(args.target, args.namespace, args.name)
    print(f"generated {len(generated)} files in {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

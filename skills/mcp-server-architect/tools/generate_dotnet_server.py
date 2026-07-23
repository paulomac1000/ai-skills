#!/usr/bin/env python3
"""Generate a deterministic, production-shaped .NET MCP server baseline."""

from __future__ import annotations

import argparse
import re
import shutil
import tempfile
from pathlib import Path

NAMESPACE_RE = re.compile(r"[A-Z][A-Za-z0-9]{1,62}$")
SERVER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{1,78}$")
RESERVED_NAMESPACES = frozenset({"System", "Microsoft", "ModelContextProtocol", "InventoryMcp"})
TEMPLATE_ROOT = Path(__file__).with_name("dotnet-template")


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


def generate_project(target: Path, namespace: str, server_name: str) -> list[Path]:
    """Atomically create a project and refuse to overwrite an existing target."""
    target = target.resolve()
    if target.exists():
        raise FileExistsError(f"target already exists: {target}")
    files = project_files(namespace, server_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent))
    try:
        for relative, content in sorted(files.items()):
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8", newline="\n")
        staging.replace(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return [Path(relative) for relative in sorted(files)]


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

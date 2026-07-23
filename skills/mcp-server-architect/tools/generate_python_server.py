#!/usr/bin/env python3
"""Public entry point for the executable Python MCP server generator."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_IMPLEMENTATION_PATH = Path(__file__).with_name("generate_python_server_impl.py")
_SPEC = importlib.util.spec_from_file_location("mcp_python_generator_implementation", _IMPLEMENTATION_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Cannot load generator implementation: {_IMPLEMENTATION_PATH}")
_implementation = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _implementation
_SPEC.loader.exec_module(_implementation)

# A generated package must not shadow any direct runtime or test dependency.
RESERVED_PACKAGE_NAMES = frozenset(_implementation.RESERVED_PACKAGE_NAMES) | {"pytest"}
_implementation.RESERVED_PACKAGE_NAMES = RESERVED_PACKAGE_NAMES

PACKAGE_RE = _implementation.PACKAGE_RE
SERVER_RE = _implementation.SERVER_RE
project_files = _implementation.project_files
generate_project = _implementation.generate_project
main = _implementation.main

__all__ = [
    "PACKAGE_RE",
    "SERVER_RE",
    "RESERVED_PACKAGE_NAMES",
    "project_files",
    "generate_project",
    "main",
]

if __name__ == "__main__":
    main()

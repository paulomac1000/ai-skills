"""Regression tests for the canonical Python generator ownership boundary."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "skills/mcp-server-architect/tools/generate_python_server.py"
IMPLEMENTATION = PUBLIC.with_name("generate_python_server_impl.py")


def _top_level_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def test_only_public_generator_exposes_cli_and_publication() -> None:
    public_functions = _top_level_functions(PUBLIC)
    implementation_functions = _top_level_functions(IMPLEMENTATION)

    assert {"generate_project", "main"} <= public_functions
    assert "generate_project" not in implementation_functions
    assert "main" not in implementation_functions
    implementation = IMPLEMENTATION.read_text(encoding="utf-8")
    assert "if __name__ ==" not in implementation
    assert "argparse" not in implementation
    assert "tempfile" not in implementation
    assert "shutil.rmtree" not in implementation


def test_public_and_internal_package_syntax_agree() -> None:
    public = PUBLIC.read_text(encoding="utf-8")
    implementation = IMPLEMENTATION.read_text(encoding="utf-8")
    expected = r"^[a-z][a-z0-9_]{1,63}$"
    assert expected in public
    assert expected in implementation

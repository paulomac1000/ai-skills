"""Focused namespace compatibility tests for the .NET MCP generator."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "skills/mcp-server-architect/tools/generate_dotnet_server.py"


def load_generator():
    """Load the generator without relying on repository import side effects."""
    spec = importlib.util.spec_from_file_location("dotnet_namespace_generator", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_generator_accepts_dot_separated_pascal_case_namespace(tmp_path: Path) -> None:
    generator = load_generator()
    target = tmp_path / "server"
    generated = generator.generate_project(target, "Company.Product", "Company Product MCP")

    assert Path("src/Company.Product.Mcp.Server/Company.Product.Mcp.Server.csproj") in generated
    program = (target / "src/Company.Product.Mcp.Server/Program.cs").read_text(encoding="utf-8")
    assert "Company.Product.Mcp.Server" in program
    assert "__NAMESPACE__" not in program


@pytest.mark.parametrize(
    "namespace",
    (
        "Company..Product",
        "Company.product",
        "Company.Bad-Name",
        "System.Product",
        "Microsoft.Product",
        "ModelContextProtocol.Product",
    ),
)
def test_generator_rejects_unsafe_or_reserved_namespace_roots(namespace: str) -> None:
    generator = load_generator()
    with pytest.raises(ValueError):
        generator.project_files(namespace, "Valid Server")

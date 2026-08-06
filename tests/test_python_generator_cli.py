"""CLI compatibility tests for the canonical Python MCP generator."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "skills/mcp-server-architect/tools/generate_python_server.py"


def load_generator():
    spec = importlib.util.spec_from_file_location(
        "python_generator_cli_contract",
        GENERATOR,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_canonical_cli_uses_documented_package_and_name_options(
    tmp_path: Path,
) -> None:
    generator = load_generator()
    target = tmp_path / "canonical"
    assert generator.main(
        [
            str(target),
            "--package",
            "inventory_mcp",
            "--name",
            "Inventory MCP",
        ]
    ) == 0
    assert (target / "src/inventory_mcp/server.py").is_file()


def test_legacy_positional_package_and_server_name_alias_remain_supported(
    tmp_path: Path,
) -> None:
    generator = load_generator()
    target = tmp_path / "legacy"
    assert generator.main(
        [
            str(target),
            "inventory_mcp",
            "--server-name",
            "Inventory MCP",
        ]
    ) == 0
    assert (target / "src/inventory_mcp/server.py").is_file()


def test_conflicting_or_missing_package_identity_fails_closed(
    tmp_path: Path,
) -> None:
    generator = load_generator()
    with pytest.raises(SystemExit):
        generator.main([str(tmp_path / "missing")])
    with pytest.raises(SystemExit):
        generator.main(
            [
                str(tmp_path / "conflict"),
                "legacy_mcp",
                "--package",
                "canonical_mcp",
            ]
        )
    assert not (tmp_path / "missing").exists()
    assert not (tmp_path / "conflict").exists()


def test_skill_documents_the_actual_canonical_cli() -> None:
    skill = (
        ROOT / "skills/mcp-server-architect/SKILL.md"
    ).read_text(encoding="utf-8")
    assert (
        "generate_python_server.py <target> --package <package_name> "
        '--name "<Server Name>"'
    ) in skill

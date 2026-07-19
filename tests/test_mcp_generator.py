"""Executable contract for the Python MCP project generator."""

from __future__ import annotations

import compileall
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "skills/mcp-server-architect/tools/generate_python_server.py"
FULL_SHA = re.compile(r"[0-9a-f]{40}")


def load_generator():
    spec = importlib.util.spec_from_file_location("mcp_project_generator", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_generator_emits_complete_deterministic_project(tmp_path: Path) -> None:
    generator = load_generator()
    first = tmp_path / "first"
    second = tmp_path / "second"
    generated = generator.generate_project(first, "inventory_mcp", "Inventory MCP")
    generator.generate_project(second, "inventory_mcp", "Inventory MCP")

    expected = {
        Path("pyproject.toml"),
        Path("README.md"),
        Path("SECURITY.md"),
        Path("Dockerfile"),
        Path(".github/workflows/ci.yml"),
        Path("src/inventory_mcp/config.py"),
        Path("src/inventory_mcp/domain.py"),
        Path("src/inventory_mcp/kernel.py"),
        Path("src/inventory_mcp/manifests.py"),
        Path("src/inventory_mcp/server.py"),
        Path("tests/test_kernel.py"),
        Path("tests/test_manifests.py"),
        Path("tests/test_mcp_smoke.py"),
    }
    assert expected.issubset(set(generated))
    assert compileall.compile_dir(first / "src", quiet=1)
    assert compileall.compile_dir(first / "tests", quiet=1)

    for relative in generated:
        assert (first / relative).read_bytes() == (second / relative).read_bytes()


def test_generated_project_uses_public_sdk_and_fail_closed_controls(tmp_path: Path) -> None:
    generator = load_generator()
    target = tmp_path / "server"
    generator.generate_project(target, "inventory_mcp", "Inventory MCP")

    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((target / "src").rglob("*.py"))
    )
    assert "from mcp.server.fastmcp import Context, FastMCP" in source
    assert "InvocationKernel" in source
    assert "validate_manifests(REGISTERED_TOOLS)" in source
    assert "max_request_body_size=1_048_576" in source
    assert "write operations are disabled by operator policy" in source
    assert "expected_version" in source
    for forbidden in ("_tool_manager", "._mcp_server", "_lifespan_data", "run_until_complete"):
        assert forbidden not in source

    workflow = (target / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for line in workflow.splitlines():
        if "uses:" not in line:
            continue
        revision = line.rsplit("@", 1)[1].split()[0]
        assert FULL_SHA.fullmatch(revision)
    assert "persist-credentials: false" in workflow


def test_generator_refuses_invalid_or_existing_targets(tmp_path: Path) -> None:
    generator = load_generator()
    for package in ("Bad-Name", "a", "_hidden", "name.with.dot"):
        try:
            generator.project_files(package, "Valid Server")
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid package accepted: {package}")

    existing = tmp_path / "existing"
    existing.mkdir()
    try:
        generator.generate_project(existing, "valid_mcp", "Valid Server")
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing target was overwritten")


def test_generated_project_passes_its_own_real_client_suite(tmp_path: Path) -> None:
    generator = load_generator()
    target = tmp_path / "server"
    generator.generate_project(target, "inventory_mcp", "Inventory MCP")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(target / "src")
    subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests"],
        cwd=target,
        env=env,
        check=True,
        timeout=120,
    )

"""Exact-wheel and container acceptance for the canonical Python MCP generator."""

from __future__ import annotations

import hashlib
import importlib.util
import shutil
import subprocess
import sys
import venv
from pathlib import Path
from types import ModuleType

import pytest

from scripts.select_lock import lock_id

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "skills/mcp-server-architect/tools/generate_python_server.py"


def load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mcp_project_generator_artifact", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_checked(
    command: list[str],
    *,
    cwd: Path,
    timeout: int = 180,
) -> subprocess.CompletedProcess[str]:
    """Run one artifact-verification command and retain diagnostics on failure."""
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    assert completed.returncode == 0, (
        f"command failed: {' '.join(command)}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    return completed


def test_generated_project_builds_installs_and_smokes_exact_wheel(
    tmp_path: Path,
) -> None:
    generator = load_generator()
    target = tmp_path / "server"
    generator.generate_project(target, "inventory_mcp", "Inventory MCP")
    run_checked(
        [sys.executable, "-m", "build", "--wheel", "--no-isolation"],
        cwd=target,
    )
    wheels = list((target / "dist").glob("*.whl"))
    assert len(wheels) == 1

    environment = tmp_path / "artifact-venv"
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    runtime_lock = target / "locks" / f"runtime-{lock_id()}.lock"
    run_checked(
        [str(python), "-m", "pip", "install", "--require-hashes", "-r", str(runtime_lock)],
        cwd=tmp_path,
        timeout=900,
    )
    run_checked(
        [str(python), "-m", "pip", "install", "--no-deps", str(wheels[0])],
        cwd=tmp_path,
    )
    outside_checkout = tmp_path / "outside-checkout"
    outside_checkout.mkdir()
    run_checked(
        [
            str(python),
            str(target / "scripts/smoke_artifact.py"),
            "--distribution",
            "inventory-mcp",
            "--package",
            "inventory_mcp",
        ],
        cwd=outside_checkout,
    )


@pytest.mark.container
@pytest.mark.anyio
async def test_generated_container_is_non_root_and_passes_official_stdio_smoke(
    tmp_path: Path,
) -> None:
    if shutil.which("docker") is None:
        pytest.skip("docker is unavailable")
    from mcp import Client, StdioServerParameters
    from mcp.client.stdio import stdio_client

    generator = load_generator()
    target = tmp_path / "server"
    generator.generate_project(target, "inventory_mcp", "Inventory MCP")
    run_checked(
        [sys.executable, "-m", "build", "--wheel", "--no-isolation"],
        cwd=target,
    )
    wheels = list((target / "dist").glob("*.whl"))
    assert len(wheels) == 1
    wheel_digest = hashlib.sha256(wheels[0].read_bytes()).hexdigest()

    image = f"ai-skills-python-mcp:{tmp_path.name.lower()}"
    run_checked(
        [
            "docker",
            "build",
            "--build-arg",
            f"WHEEL=dist/{wheels[0].name}",
            "--build-arg",
            f"WHEEL_SHA256={wheel_digest}",
            "--tag",
            image,
            ".",
        ],
        cwd=target,
        timeout=300,
    )
    try:
        identity = run_checked(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "python",
                image,
                "-c",
                "import os, inventory_mcp, pathlib; "
                "assert os.getuid() != 0; "
                "p=pathlib.Path(inventory_mcp.__file__).resolve(); "
                "assert 'site-packages' in p.parts, p",
            ],
            cwd=target,
        )
        assert identity.returncode == 0
        parameters = StdioServerParameters(
            command="docker",
            args=["run", "--rm", "-i", image],
        )
        async with Client(stdio_client(parameters)) as client:
            tools = await client.list_tools()
            assert {"list_items", "put_item"} <= {tool.name for tool in tools.tools}
            result = await client.call_tool("list_items", {"limit": 1})
            assert result.is_error is False
            denied = await client.call_tool(
                "put_item",
                {
                    "item_id": "blocked",
                    "value": "Blocked",
                    "approval_record": "invalid",
                },
            )
            assert denied.is_error is True
    finally:
        subprocess.run(
            ["docker", "image", "rm", "--force", image],
            check=False,
            capture_output=True,
            text=True,
        )

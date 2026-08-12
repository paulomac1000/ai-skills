"""Executable contract for the canonical Python MCP project generator."""

from __future__ import annotations

import compileall
import importlib.util
import json
import shutil
import subprocess
import sys
import threading
import venv
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "skills/mcp-server-architect/tools/generate_python_server.py"
AUDITOR = ROOT / "skills/ci-cd-architect/tools/check_github_actions_policy.py"
TEMPLATE_ROOT = ROOT / "skills/mcp-server-architect/tools/python-template"


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_generator() -> ModuleType:
    """Load the generator from its stable public file entry point."""
    return _load_module(GENERATOR, "mcp_project_generator")


def load_workflow_auditor() -> ModuleType:
    """Load the same auditor used by repository and adoption gates."""
    tools = str(AUDITOR.parent)
    if tools not in sys.path:
        sys.path.insert(0, tools)
    return _load_module(AUDITOR, "generated_workflow_auditor")


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


def test_generator_emits_complete_deterministic_project(tmp_path: Path) -> None:
    generator = load_generator()
    first = tmp_path / "first"
    second = tmp_path / "second"
    generated = generator.generate_project(
        first,
        "inventory_mcp",
        "Inventory MCP",
    )
    generator.generate_project(second, "inventory_mcp", "Inventory MCP")

    expected = {
        Path("pyproject.toml"),
        Path("README.md"),
        Path("Dockerfile"),
        Path(".dockerignore"),
        Path(".github/workflows/ci.yml"),
        Path("src/inventory_mcp/server.py"),
        Path("src/inventory_mcp/kernel.py"),
        Path("src/inventory_mcp/manifest.py"),
        Path("src/inventory_mcp/security.py"),
        Path("src/inventory_mcp/contracts/capability-manifest.schema.json"),
        Path("src/inventory_mcp/capabilities/describe_capabilities.json"),
        Path("src/inventory_mcp/capabilities/list_items.json"),
        Path("src/inventory_mcp/capabilities/put_item.json"),
        Path("scripts/assert_junit.py"),
        Path("scripts/smoke_artifact.py"),
        Path("scripts/smoke_url.py"),
        Path("tests/test_generated_contract.py"),
        *(Path("locks") / name for name in generator.LOCK_NAMES),
    }
    assert expected <= set(generated)
    assert compileall.compile_dir(first / "src", quiet=1)
    assert compileall.compile_dir(first / "tests", quiet=1)
    assert compileall.compile_dir(first / "scripts", quiet=1)
    for relative in generated:
        assert (first / relative).read_bytes() == (second / relative).read_bytes()


def test_generator_has_one_canonical_template_source() -> None:
    facade = GENERATOR.read_text(encoding="utf-8")
    implementation = GENERATOR.with_name(
        "generate_python_server_impl.py"
    ).read_text(encoding="utf-8")
    assert "_replace_required" not in facade
    assert "_replace_required" not in implementation
    assert 'with_name("python-template")' in implementation
    assert list(TEMPLATE_ROOT.rglob("*.template"))
    assert "MCPServer(" not in implementation
    assert "FROM python:" not in implementation


def test_generated_project_uses_canonical_schema_and_public_sdk(
    tmp_path: Path,
) -> None:
    generator = load_generator()
    target = tmp_path / "server"
    generator.generate_project(target, "inventory_mcp", "Inventory MCP")

    copied_schema = (
        target / "src/inventory_mcp/contracts/capability-manifest.schema.json"
    )
    assert copied_schema.read_bytes() == (
        ROOT / "contracts/capability-manifest.schema.json"
    ).read_bytes()
    generator.validate_generated_project(
        generator.project_files("inventory_mcp", "Inventory MCP"),
        "inventory_mcp",
    )

    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((target / "src").rglob("*.py"))
    )
    assert "from mcp.server import MCPServer" in source
    assert "from mcp.server.mcpserver" not in source
    assert "_tool_manager" not in source
    assert "._mcp_server" not in source
    assert "MCP_ENABLE_WRITES" in source
    assert "arguments_digest" in source
    assert "hmac.compare_digest" in source
    assert "ContextVar" in source

    capability_paths = sorted(
        (target / "src/inventory_mcp/capabilities").glob("*.json")
    )
    assert capability_paths
    for path in capability_paths:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert not {"operational_impact", "active", "side_effects"}.intersection(
            manifest
        )
        assert manifest["active_state"] == "active"


def test_generated_workflow_passes_trusted_ci_policy(tmp_path: Path) -> None:
    generator = load_generator()
    target = tmp_path / "server"
    generator.generate_project(target, "inventory_mcp", "Inventory MCP")
    workflow = target / ".github/workflows/ci.yml"
    auditor = load_workflow_auditor()
    findings = auditor.audit_workflow(workflow, target, profile="trusted-ci")
    assert findings == [], "\n".join(
        f"{finding.path}: {finding.message}" for finding in findings
    )

    text = workflow.read_text(encoding="utf-8")
    assert "ubuntu-latest" not in text
    assert "concurrency:" in text
    assert "persist-credentials: false" in text
    assert "--junitxml=junit.xml" in text
    assert "--minimum-tests 1 --maximum-skips 0" in text
    assert "Smoke exact installed wheel outside checkout" in text
    assert "Build and smoke the exact-wheel container" in text


def test_generated_container_installs_only_the_exact_wheel(tmp_path: Path) -> None:
    generator = load_generator()
    target = tmp_path / "server"
    generator.generate_project(target, "inventory_mcp", "Inventory MCP")
    dockerfile = (target / "Dockerfile").read_text(encoding="utf-8")
    assert "python:3.12.11-slim-bookworm@sha256:" in dockerfile
    assert "COPY ${WHEEL} /tmp/application.whl" in dockerfile
    assert "--require-hashes -r /tmp/runtime.lock" in dockerfile
    assert "--no-deps /tmp/application.whl" in dockerfile
    assert "COPY src" not in dockerfile
    assert "pip install --no-cache-dir ." not in dockerfile


def test_generator_refuses_invalid_reserved_and_existing_targets(
    tmp_path: Path,
) -> None:
    generator = load_generator()
    invalid_names = (
        "a",
        "Bad-Name",
        "_hidden",
        "name.with.dot",
        "class",
        "async",
        "mcp",
        "uvicorn",
        "pytest",
        "json",
        "email",
        "con",
        "nul",
    )
    for package in invalid_names:
        with pytest.raises(ValueError):
            generator.project_files(package, "Valid Server")
    assert {
        "mcp",
        "uvicorn",
        "pytest",
        "json",
        "email",
        "con",
        "nul",
    } <= generator.RESERVED_PACKAGE_NAMES

    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(FileExistsError):
        generator.generate_project(existing, "valid_mcp", "Valid Server")


def test_generator_concurrent_create_has_one_winner_and_never_replaces(
    tmp_path: Path,
) -> None:
    """Exercise the operating-system-specific no-replace publish primitive."""
    generator = load_generator()
    target = tmp_path / "server"
    barrier = threading.Barrier(2)

    def generate() -> list[Path] | FileExistsError:
        barrier.wait(timeout=5)
        try:
            return generator.generate_project(
                target,
                "inventory_mcp",
                "Inventory MCP",
            )
        except FileExistsError as exception:
            return exception

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: generate(), range(2)))

    assert sum(isinstance(result, list) for result in results) == 1
    assert sum(isinstance(result, FileExistsError) for result in results) == 1
    assert (target / "src/inventory_mcp/server.py").is_file()
    assert not list(tmp_path.glob(".server.*"))


def test_generator_preserves_competing_target_created_before_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = load_generator()
    implementation = generator._implementation
    target = tmp_path / "server"
    original = implementation._rename_noreplace

    def create_competitor(source: Path, destination: Path) -> None:
        destination.mkdir()
        (destination / "sentinel.txt").write_text(
            "competitor",
            encoding="utf-8",
        )
        original(source, destination)

    monkeypatch.setattr(
        implementation,
        "_rename_noreplace",
        create_competitor,
    )
    with pytest.raises(FileExistsError):
        generator.generate_project(target, "inventory_mcp", "Inventory MCP")
    assert (target / "sentinel.txt").read_text(encoding="utf-8") == "competitor"
    assert not (target / "src").exists()
    assert not list(tmp_path.glob(".server.*"))


def test_generated_project_builds_installs_and_smokes_exact_wheel(
    tmp_path: Path,
) -> None:
    """Prove import and protocol behavior without PYTHONPATH or editable source."""
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
    venv.EnvBuilder(with_pip=True, system_site_packages=True).create(environment)
    python = environment / (
        "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
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
    """Build and invoke the exact generated image rather than inspecting Dockerfile text only."""
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

    image = f"ai-skills-python-mcp:{tmp_path.name.lower()}"
    run_checked(
        [
            "docker",
            "build",
            "--build-arg",
            f"WHEEL=dist/{wheels[0].name}",
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
            assert {"list_items", "put_item"} <= {
                tool.name for tool in tools.tools
            }
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

"""Executable contract for the Python MCP project generator."""

from __future__ import annotations

import compileall
import importlib.util
import re
import subprocess
import sys
import threading
import venv
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "skills/mcp-server-architect/tools/generate_python_server.py"
FULL_SHA = re.compile(r"[0-9a-f]{40}")


def load_generator():
    """Load the generator from its public file entry point."""
    spec = importlib.util.spec_from_file_location("mcp_project_generator", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_checked(command: list[str], *, cwd: Path, timeout: int = 180) -> subprocess.CompletedProcess[str]:
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
        f"command failed: {' '.join(command)}\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )
    return completed


def test_generator_emits_complete_deterministic_project(tmp_path: Path) -> None:
    generator = load_generator()
    first = tmp_path / "first"
    second = tmp_path / "second"
    generated = generator.generate_project(first, "inventory_mcp", "Inventory MCP")
    generator.generate_project(second, "inventory_mcp", "Inventory MCP")

    expected = {
        Path("pyproject.toml"),
        Path("requirements.lock"),
        Path("README.md"),
        Path("SECURITY.md"),
        Path("Dockerfile"),
        Path(".github/workflows/ci.yml"),
        Path("src/inventory_mcp/config.py"),
        Path("src/inventory_mcp/domain.py"),
        Path("src/inventory_mcp/http.py"),
        Path("src/inventory_mcp/kernel.py"),
        Path("src/inventory_mcp/manifests.py"),
        Path("src/inventory_mcp/server.py"),
        Path("tests/test_config.py"),
        Path("tests/test_http_limit.py"),
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
    source = "\n".join(path.read_text(encoding="utf-8") for path in sorted((target / "src").rglob("*.py")))
    for token in (
        "from mcp.server.fastmcp import Context, FastMCP",
        "InvocationKernel",
        "ApprovalRegistry",
        "secrets.token_urlsafe(32)",
        "max_records: int = 1_024",
        "record.principal == principal",
        "threading.Lock()",
        "approval registry capacity reached",
        "validate_manifests(REGISTERED_TOOLS)",
        "RequestBodyLimitMiddleware",
        "MCP_MAX_REQUEST_BODY_BYTES",
        "server.streamable_http_app()",
        "address.is_loopback",
        "write_enabled must be a boolean",
        "write operations are disabled by operator policy",
        "expected_version is mandatory",
        "expected_version: int",
        "too many request body chunks",
        "content-length mismatch",
        "await self._app(scope, replay_receive, send)",
    ):
        assert token in source
    assert "confirmed: bool" not in source
    assert "caller.confirmed" not in source
    assert "\nmcp = build_server" not in source
    for forbidden in (
        "_tool_manager",
        "._mcp_server",
        "_lifespan_data",
        "run_until_complete",
        "max_request_body_size=",
    ):
        assert forbidden not in source

    lock = (target / "requirements.lock").read_text(encoding="utf-8")
    for pin in (
        "mcp==1.28.1",
        "uvicorn==0.51.0",
        "pytest==9.1.1",
        "build==1.5.1",
        "setuptools==83.0.0",
        "wheel==0.47.0",
    ):
        assert pin in lock

    pyproject = (target / "pyproject.toml").read_text(encoding="utf-8")
    assert 'mcp>=1.28.1,<2' in pyproject
    assert 'setuptools==83.0.0' in pyproject

    dockerfile = (target / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY pyproject.toml README.md requirements.lock ./" in dockerfile
    assert "PIP_CONSTRAINT=/app/requirements.lock" in dockerfile

    workflow = (target / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for line in workflow.splitlines():
        if "uses:" not in line:
            continue
        revision = line.rsplit("@", 1)[1].split()[0]
        assert FULL_SHA.fullmatch(revision)
    assert "persist-credentials: false" in workflow
    assert "Build exact wheel" in workflow
    assert "Test exact wheel with the official MCP client" in workflow
    assert "--constraint requirements.lock" in workflow


def test_generator_refuses_invalid_reserved_and_existing_targets(tmp_path: Path) -> None:
    generator = load_generator()
    invalid_names = (
        "Bad-Name",
        "a",
        "_hidden",
        "name.with.dot",
        "class",
        "async",
        "mcp",
        "uvicorn",
        "pytest",
        "json",
        "email",
    )
    for package in invalid_names:
        try:
            generator.project_files(package, "Valid Server")
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid package accepted: {package}")
    assert {"mcp", "uvicorn", "pytest", "json", "email"}.issubset(generator.RESERVED_PACKAGE_NAMES)

    existing = tmp_path / "existing"
    existing.mkdir()
    try:
        generator.generate_project(existing, "valid_mcp", "Valid Server")
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing target was overwritten")


def test_generator_concurrent_create_has_one_winner_and_never_replaces(tmp_path: Path) -> None:
    """Exercise the operating-system-specific no-replace publish primitive."""
    generator = load_generator()
    target = tmp_path / "server"
    barrier = threading.Barrier(2)

    def generate():
        barrier.wait(timeout=5)
        try:
            return generator.generate_project(target, "inventory_mcp", "Inventory MCP")
        except FileExistsError as exception:
            return exception

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: generate(), range(2)))

    assert sum(isinstance(result, list) for result in results) == 1
    assert sum(isinstance(result, FileExistsError) for result in results) == 1
    assert (target / "src/inventory_mcp/server.py").is_file()
    assert not list(tmp_path.glob(".server-*/"))


def test_generated_project_builds_installs_and_tests_exact_wheel(tmp_path: Path) -> None:
    """Prove installability without PYTHONPATH or editable-source shortcuts."""
    generator = load_generator()
    target = tmp_path / "server"
    generator.generate_project(target, "inventory_mcp", "Inventory MCP")

    environment = tmp_path / "artifact-venv"
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

    run_checked(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--constraint",
            "requirements.lock",
            "build==1.5.1",
            "setuptools==83.0.0",
            "wheel==0.47.0",
        ],
        cwd=target,
    )
    run_checked([str(python), "-m", "build", "--wheel", "--no-isolation"], cwd=target)
    wheels = list((target / "dist").glob("*.whl"))
    assert len(wheels) == 1
    run_checked(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--constraint",
            "requirements.lock",
            str(wheels[0]),
            "pytest==9.1.1",
        ],
        cwd=target,
    )
    run_checked(
        [
            str(python),
            "-c",
            "import inventory_mcp, pathlib; "
            "p = pathlib.Path(inventory_mcp.__file__).resolve(); "
            "assert 'site-packages' in p.parts, p",
        ],
        cwd=target,
    )
    run_checked([str(python), "-m", "pytest", "-q", "tests"], cwd=target)

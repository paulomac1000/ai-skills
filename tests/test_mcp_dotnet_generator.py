"""Executable contract for the .NET MCP project generator."""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "skills/mcp-server-architect/tools/generate_dotnet_server.py"
FULL_SHA = re.compile(r"[0-9a-f]{40}")


def load_generator():
    spec = importlib.util.spec_from_file_location("dotnet_mcp_project_generator", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_generator_emits_complete_deterministic_project(tmp_path: Path) -> None:
    generator = load_generator()
    first = tmp_path / "first"
    second = tmp_path / "second"
    generated = generator.generate_project(first, "Acme", "Acme MCP")
    generator.generate_project(second, "Acme", "Acme MCP")

    expected = {
        Path("global.json"),
        Path("Directory.Build.props"),
        Path("Directory.Packages.props"),
        Path("README.md"),
        Path("SECURITY.md"),
        Path("Dockerfile"),
        Path(".github/workflows/ci.yml"),
        Path("src/Acme.Mcp.Domain/Acme.Mcp.Domain.csproj"),
        Path("src/Acme.Mcp.Domain/Inventory.cs"),
        Path("src/Acme.Mcp.Server/Acme.Mcp.Server.csproj"),
        Path("src/Acme.Mcp.Server/packages.lock.json"),
        Path("src/Acme.Mcp.Server/Program.cs"),
        Path("src/Acme.Mcp.Server/Tools.cs"),
        Path("src/Acme.Mcp.Server/InvocationKernel.cs"),
        Path("src/Acme.Mcp.Server/CapabilityManifest.cs"),
        Path("src/Acme.Mcp.Server/ApprovalRegistry.cs"),
        Path("src/Acme.Mcp.Server/ServerSettings.cs"),
        Path("tests/Acme.Mcp.Smoke/Acme.Mcp.Smoke.csproj"),
        Path("tests/Acme.Mcp.Smoke/packages.lock.json"),
        Path("tests/Acme.Mcp.Smoke/Program.cs"),
    }
    assert expected.issubset(set(generated))
    for relative in generated:
        assert (first / relative).read_bytes() == (second / relative).read_bytes()


def test_generated_project_uses_public_sdk_and_fail_closed_controls(tmp_path: Path) -> None:
    generator = load_generator()
    target = tmp_path / "server"
    generator.generate_project(target, "Acme", "Acme MCP")
    source = "\n".join(path.read_text(encoding="utf-8") for path in sorted((target / "src").rglob("*.cs")))

    for token in (
        "ModelContextProtocol",
        "WithStdioServerTransport",
        "WithHttpTransport",
        "options.Stateless = true",
        "AddAuthorizationFilters",
        "WithTools<CapabilityTools>",
        "WithTools<InventoryTools>",
        "ClaimsPrincipal? principal",
        "UseStructuredContent = true",
        "OutputSchemaType",
        "throw new McpException",
        "Capability manifests do not cover",
        "record.Principal",
        "RandomNumberGenerator.GetBytes(32)",
        "expectedVersion",
        "writes are disabled by operator policy",
        "ListenLocalhost",
        "MaxRequestBodySize",
        "RequireRateLimiting",
        "UseAuthorization();\n    app.UseRateLimiter();",
        "StringComparison.OrdinalIgnoreCase",
        "SHA256.HashData",
    ):
        assert token in source

    for forbidden in (
        "WithToolsFromAssembly",
        "EnableLegacySse",
        ".Result",
        ".Wait()",
        "HttpClient.Timeout =",
        "Task.Run(",
        "confirmed: bool",
    ):
        assert forbidden not in source

    build_props = (target / "Directory.Build.props").read_text(encoding="utf-8")
    assert "<RestorePackagesWithLockFile>true</RestorePackagesWithLockFile>" in build_props

    server_lock = (target / "src/Acme.Mcp.Server/packages.lock.json").read_text(encoding="utf-8")
    smoke_lock = (target / "tests/Acme.Mcp.Smoke/packages.lock.json").read_text(encoding="utf-8")
    for lock in (server_lock, smoke_lock):
        assert "Locked" not in lock
        assert "locked.mcp." not in lock
        assert "__NAMESPACE" not in lock
    assert "acme.mcp.domain" in server_lock
    assert "acme.mcp.server" in smoke_lock

    packages = (target / "Directory.Packages.props").read_text(encoding="utf-8")
    assert 'ModelContextProtocol" Version="1.4.1"' in packages
    assert 'ModelContextProtocol.AspNetCore" Version="1.4.1"' in packages

    smoke = (target / "tests/Acme.Mcp.Smoke/Program.cs").read_text(encoding="utf-8")
    assert "InheritEnvironmentVariables = false" in smoke
    assert "HttpTransportMode.StreamableHttp" in smoke
    assert "StructuredContent is null" in smoke
    assert '"WRITE_DISABLED"' in smoke
    assert '"APPROVAL_INVALID"' in smoke
    assert "writesEnabled: false" in smoke
    assert "writesEnabled: true" in smoke
    assert "VerifyApprovalContractAsync" in smoke
    assert "approvals.Issue" in smoke
    assert "other-principal" in smoke
    assert "Case-insensitive Bearer authentication was rejected" in smoke

    workflow = (target / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for line in workflow.splitlines():
        if "uses:" not in line:
            continue
        revision = line.rsplit("@", 1)[1].split()[0]
        assert FULL_SHA.fullmatch(revision)
    assert "persist-credentials: false" in workflow
    assert "--locked-mode" in workflow
    assert "Official-client stdio smoke" in workflow
    assert "Official-client Streamable HTTP smoke" in workflow
    assert "Smoke exact artifact over stdio" in workflow
    assert "Smoke exact artifact over Streamable HTTP" in workflow


def test_generator_refuses_invalid_reserved_and_existing_targets(tmp_path: Path) -> None:
    generator = load_generator()
    for namespace in ("a", "bad-name", "lowercase", "System", "Microsoft", "ModelContextProtocol", "InventoryMcp"):
        with pytest.raises(ValueError):
            generator.project_files(namespace, "Valid Server")

    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(FileExistsError):
        generator.generate_project(existing, "Acme", "Valid Server")

    dangling = tmp_path / "dangling"
    dangling.symlink_to(tmp_path / "missing-target", target_is_directory=True)
    with pytest.raises(FileExistsError):
        generator.generate_project(dangling, "Acme", "Valid Server")


def test_generator_concurrent_create_has_one_winner_and_never_replaces(tmp_path: Path) -> None:
    generator = load_generator()
    target = tmp_path / "server"
    barrier = threading.Barrier(2)

    def generate():
        barrier.wait(timeout=5)
        try:
            return generator.generate_project(target, "Acme", "Acme MCP")
        except FileExistsError as exception:
            return exception

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: generate(), range(2)))

    assert sum(isinstance(result, list) for result in results) == 1
    assert sum(isinstance(result, FileExistsError) for result in results) == 1
    assert (target / "src/Acme.Mcp.Server/Program.cs").is_file()
    assert not list(tmp_path.glob(".server-*/"))
    assert not (tmp_path / ".server.generation.lock").exists()


def test_generator_preserves_competing_target_created_before_publish(tmp_path: Path, monkeypatch) -> None:
    generator = load_generator()
    target = tmp_path / "server"
    original = generator._rename_noreplace

    def competing_publish(source: Path, destination: Path) -> None:
        destination.mkdir()
        (destination / "owner.txt").write_text("other process", encoding="utf-8")
        original(source, destination)

    monkeypatch.setattr(generator, "_rename_noreplace", competing_publish)
    with pytest.raises(FileExistsError):
        generator.generate_project(target, "Acme", "Acme MCP")

    assert (target / "owner.txt").read_text(encoding="utf-8") == "other process"
    assert not (target / "src").exists()
    assert not (tmp_path / ".server.generation.lock").exists()


@pytest.mark.skipif(shutil.which("dotnet") is None, reason="dotnet SDK is unavailable")
def test_generated_project_builds_and_passes_real_client_smoke(tmp_path: Path) -> None:
    generator = load_generator()
    target = tmp_path / "server"
    generator.generate_project(target, "Acme", "Acme MCP")
    project = "tests/Acme.Mcp.Smoke/Acme.Mcp.Smoke.csproj"
    server_dll = "src/Acme.Mcp.Server/bin/Release/net10.0/Acme.Mcp.Server.dll"
    smoke_dll = "tests/Acme.Mcp.Smoke/bin/Release/net10.0/Acme.Mcp.Smoke.dll"
    published = "publish/Acme.Mcp.Server.dll"
    commands = [
        ["dotnet", "restore", project, "--locked-mode"],
        ["dotnet", "build", project, "--configuration", "Release", "--no-restore"],
        ["dotnet", "run", "--project", project, "--configuration", "Release", "--no-build", "--", server_dll],
        ["dotnet", "run", "--project", project, "--configuration", "Release", "--no-build", "--", server_dll, "--http"],
        ["dotnet", "publish", "src/Acme.Mcp.Server/Acme.Mcp.Server.csproj", "--configuration", "Release", "--no-build", "--output", "publish"],
        ["dotnet", smoke_dll, published],
        ["dotnet", smoke_dll, published, "--http"],
    ]
    env = os.environ.copy()
    env["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=target,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert completed.returncode == 0, (
            f"command failed: {' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )

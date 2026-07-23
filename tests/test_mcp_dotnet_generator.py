"""Executable contract for the .NET MCP project generator."""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
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
        Path("src/Acme.Mcp.Server/Program.cs"),
        Path("src/Acme.Mcp.Server/Tools.cs"),
        Path("src/Acme.Mcp.Server/InvocationKernel.cs"),
        Path("src/Acme.Mcp.Server/CapabilityManifest.cs"),
        Path("src/Acme.Mcp.Server/ApprovalRegistry.cs"),
        Path("src/Acme.Mcp.Server/ServerSettings.cs"),
        Path("tests/Acme.Mcp.Smoke/Acme.Mcp.Smoke.csproj"),
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

    packages = (target / "Directory.Packages.props").read_text(encoding="utf-8")
    assert 'ModelContextProtocol" Version="1.4.1"' in packages
    assert 'ModelContextProtocol.AspNetCore" Version="1.4.1"' in packages

    smoke = (target / "tests/Acme.Mcp.Smoke/Program.cs").read_text(encoding="utf-8")
    assert "InheritEnvironmentVariables = false" in smoke
    assert "HttpTransportMode.StreamableHttp" in smoke
    assert "StructuredContent is null" in smoke
    assert "rejected.IsError != true" in smoke

    workflow = (target / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for line in workflow.splitlines():
        if "uses:" not in line:
            continue
        revision = line.rsplit("@", 1)[1].split()[0]
        assert FULL_SHA.fullmatch(revision)
    assert "persist-credentials: false" in workflow
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
        ["dotnet", "restore", project],
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

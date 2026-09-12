"""Exact-artifact acceptance contract for the generated .NET Steward seed."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "skills/mcp-steward-architect/tools/generate_steward.py"
REQUIRED_DOTNET_SDK = "10.0.302"


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("dotnet_steward_project_generator", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _has_required_dotnet_sdk() -> bool:
    if shutil.which("dotnet") is None:
        return False
    try:
        completed = subprocess.run(
            ["dotnet", "--list-sdks"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0 and any(
        line.split()[0] == REQUIRED_DOTNET_SDK
        for line in completed.stdout.splitlines()
        if line.split()
    )


@pytest.mark.skipif(
    not _has_required_dotnet_sdk(),
    reason=f"generated .NET Steward artifact requires SDK {REQUIRED_DOTNET_SDK}",
)
def test_generated_dotnet_steward_builds_publishes_and_passes_official_client_smoke(
    tmp_path: Path,
) -> None:
    generator = _load_generator()
    target = tmp_path / "steward"
    generator.generate_project(
        target,
        language="dotnet",
        identity="StewardAcceptance",
        server_name="Steward Acceptance",
        steward_id="acceptance",
        profile="verification",
    )

    project = "tests/StewardAcceptance.Mcp.Smoke/StewardAcceptance.Mcp.Smoke.csproj"
    server_project = "src/StewardAcceptance.Mcp.Server/StewardAcceptance.Mcp.Server.csproj"
    server_dll = "src/StewardAcceptance.Mcp.Server/bin/Release/net10.0/StewardAcceptance.Mcp.Server.dll"
    smoke_dll = "tests/StewardAcceptance.Mcp.Smoke/bin/Release/net10.0/StewardAcceptance.Mcp.Smoke.dll"
    published = "publish/StewardAcceptance.Mcp.Server.dll"
    commands = [
        ["dotnet", "restore", project, "--locked-mode"],
        ["dotnet", "build", project, "--configuration", "Release", "--no-restore"],
        [
            "dotnet",
            "run",
            "--project",
            project,
            "--configuration",
            "Release",
            "--no-build",
            "--",
            server_dll,
        ],
        [
            "dotnet",
            "run",
            "--project",
            project,
            "--configuration",
            "Release",
            "--no-build",
            "--",
            server_dll,
            "--http",
        ],
        [
            "dotnet",
            "publish",
            server_project,
            "--configuration",
            "Release",
            "--no-build",
            "--output",
            "publish",
        ],
        ["dotnet", smoke_dll, published],
        ["dotnet", smoke_dll, published, "--http"],
    ]

    environment = os.environ.copy()
    environment["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=target,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=240,
        )
        assert completed.returncode == 0, (
            f"command failed: {' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )

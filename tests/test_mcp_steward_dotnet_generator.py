"""Exact-artifact acceptance contract for the generated .NET Steward seed."""

from __future__ import annotations

import importlib.util
import json
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
        line.split()[0] == REQUIRED_DOTNET_SDK for line in completed.stdout.splitlines() if line.split()
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
    handoff_export = "handoff-export.json"
    job_export = "job-export.json"
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
            "--export-handoff",
            handoff_export,
            "--export-job",
            job_export,
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
            f"command failed: {' '.join(command)}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )

    # The exported document is validated outside the .NET runtime on purpose:
    # the digest must match the language-neutral canonical rule, not a private copy.
    exported = json.loads((target / handoff_export).read_text(encoding="utf-8"))
    spec = importlib.util.spec_from_file_location(
        "steward_validator_dotnet_acceptance", ROOT / "skills/mcp-steward-architect/tools/validate_steward.py"
    )
    assert spec is not None and spec.loader is not None
    validator = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = validator
    spec.loader.exec_module(validator)
    assert validator.validate_document("handoff", exported) == [], validator.validate_document("handoff", exported)
    assert validator.compute_handoff_digest(exported) == exported["digest"]

    # Validated outside the .NET runtime: the terms must survive a full store restart.
    exported_job = json.loads((target / job_export).read_text(encoding="utf-8"))
    assert validator.validate_document("job", exported_job) == [], validator.validate_document("job", exported_job)
    parent_projection = exported_job["parentContract"]
    assert parent_projection["policy"]["revisionOrDigest"] == "policy-7"
    assert parent_projection["completion"]["obligationsRef"] == "obligations:9"
    assert parent_projection["completion"]["terminalBoundary"] == "supervisor-job"
    assert parent_projection["completion"]["handoffContract"] == "execution-evidence-v9"
    assert parent_projection["budget"]["retryOrResourceBudgetRef"].startswith("budget:")

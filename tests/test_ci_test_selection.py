from __future__ import annotations

import ast
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _run_command(job: str, step_name: str) -> str:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"][job]["steps"]
    step = next(step for step in steps if step.get("name") == step_name)
    return step["run"]


def test_dedicated_wheel_gate_keeps_required_wheel_test_selected() -> None:
    command = _run_command("python", "Validate exact generated Python wheel")
    source = ast.parse((ROOT / "tests/test_mcp_generator.py").read_text(encoding="utf-8"))
    test_names = {node.name for node in ast.walk(source) if isinstance(node, ast.FunctionDef)}

    assert "tests/test_mcp_generator.py" in command
    assert "test_generated_project_builds_installs_and_smokes_exact_wheel" in test_names


def test_container_gate_keeps_required_container_test_selected() -> None:
    command = _run_command(
        "python-container-artifact",
        "Build non-root generated image and invoke through official MCP client",
    )

    assert "tests/test_mcp_generator.py" in command
    assert "-m container" in command
    source = ast.parse((ROOT / "tests/test_mcp_generator.py").read_text(encoding="utf-8"))
    assert any(
        isinstance(node, ast.AsyncFunctionDef)
        and node.name == "test_generated_container_is_non_root_and_passes_official_stdio_smoke"
        for node in ast.walk(source)
    )


def test_repository_coverage_lane_excludes_dedicated_generator_suite() -> None:
    repository_command = _run_command("python", "Run repository tests with branch coverage")
    assert "--ignore=tests/test_mcp_generator.py" in repository_command

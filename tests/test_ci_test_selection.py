from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _run_command(job: str, step_name: str) -> str:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"][job]["steps"]
    step = next(step for step in steps if step.get("name") == step_name)
    return step["run"]


def _collect_selected_tests(job: str, step_name: str) -> str:
    """Run the pytest selector embedded in one CI step in collection-only mode."""
    arguments = shlex.split(_run_command(job, step_name))
    if "--" in arguments:
        arguments = arguments[arguments.index("--") + 1 :]
    if arguments and arguments[0] == "python":
        arguments[0] = sys.executable
    arguments = [argument for argument in arguments if not argument.startswith("--junitxml=")]
    completed = subprocess.run(
        [*arguments, "--collect-only", "-vv"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return completed.stdout


def test_dedicated_wheel_gate_keeps_required_wheel_test_selected() -> None:
    command = _run_command("python", "Validate exact generated Python wheel")

    assert "tests/test_mcp_generator.py" in command
    selected_tests = _collect_selected_tests("python", "Validate exact generated Python wheel")
    assert "test_generated_project_builds_installs_and_smokes_exact_wheel" in selected_tests
    assert "test_generated_container_is_non_root_and_passes_official_stdio_smoke" not in selected_tests


def test_container_gate_keeps_required_container_test_selected() -> None:
    command = _run_command(
        "python-container-artifact",
        "Build non-root generated image and invoke through official MCP client",
    )

    assert "tests/test_mcp_generator.py" in command
    assert "-m container" in command
    selected_tests = _collect_selected_tests(
        "python-container-artifact",
        "Build non-root generated image and invoke through official MCP client",
    )
    assert "test_generated_container_is_non_root_and_passes_official_stdio_smoke" in selected_tests


def test_repository_coverage_lane_excludes_dedicated_generator_suite() -> None:
    repository_command = _run_command("python", "Run repository tests with branch coverage")
    assert "--ignore=tests/test_mcp_generator.py" in repository_command

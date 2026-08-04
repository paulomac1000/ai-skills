"""Regressions for the latest AGENTS.md evidence review."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills/agents-md-architect/tools"
sys.path.insert(0, str(TOOLS))

import agents_md_shell_evidence as shell_evidence  # noqa: E402
import audit_agents_md as audit_module  # noqa: E402


def _codes(findings: list[Any]) -> set[str]:
    return {item.code for item in findings}


def _agents(full_gate: str) -> str:
    return f"""# AGENTS.md

## Scope

These instructions apply to the repository.

## Commands and verification

- Full gate: `{full_gate}`

## Safety boundaries

Secrets must not be committed. Destructive writes require explicit authorization and rollback.

## Definition of done

Report the exact revision, skipped checks, and residual risk.
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_gitlab_variable_named_script_cannot_establish_gate_evidence(tmp_path: Path) -> None:
    _write(
        tmp_path / ".gitlab-ci.yml",
        """variables:
  script: python scripts/ghost.py

real_job:
  script: echo real gate
""",
    )
    _write(tmp_path / "AGENTS.md", _agents("python scripts/ghost.py"))

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")

    assert "commands.unlocated-full-gate" in _codes(findings)


@pytest.mark.parametrize(
    "configuration",
    (
        """workflow:
  rules:
    - if: '$CI_COMMIT_BRANCH'
      script: python scripts/ghost.py
real_job:
  script: echo real
""",
        """real_job:
  script: echo real
  artifacts:
    script: python scripts/ghost.py
""",
        """real_job:
  rules:
    - if: '$CI_COMMIT_BRANCH'
      script: python scripts/ghost.py
  script: echo real
""",
    ),
)
def test_gitlab_nested_non_command_objects_cannot_establish_evidence(
    tmp_path: Path,
    configuration: str,
) -> None:
    _write(tmp_path / ".gitlab-ci.yml", configuration)
    _write(tmp_path / "AGENTS.md", _agents("python scripts/ghost.py"))

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")

    assert "commands.unlocated-full-gate" in _codes(findings)


@pytest.mark.parametrize(
    ("configuration", "command"),
    (
        ("real_job:\n  script: python scripts/ci.py\n", "python scripts/ci.py"),
        ("real_job:\n  before_script:\n    - python scripts/setup.py\n", "python scripts/setup.py"),
        ("real_job:\n  after_script: python scripts/cleanup.py\n", "python scripts/cleanup.py"),
        ("before_script:\n  - python scripts/global_setup.py\n", "python scripts/global_setup.py"),
        ("after_script: python scripts/global_cleanup.py\n", "python scripts/global_cleanup.py"),
        ("default:\n  before_script:\n    - python scripts/default_setup.py\n", "python scripts/default_setup.py"),
        ("default:\n  after_script: python scripts/default_cleanup.py\n", "python scripts/default_cleanup.py"),
        ("pages:\n  script:\n    - python scripts/publish_pages.py\n", "python scripts/publish_pages.py"),
    ),
)
def test_gitlab_supported_executable_scopes_establish_evidence(
    tmp_path: Path,
    configuration: str,
    command: str,
) -> None:
    _write(tmp_path / ".gitlab-ci.yml", configuration)
    _write(tmp_path / "AGENTS.md", _agents(command))

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")

    assert "commands.unlocated-full-gate" not in _codes(findings)


def test_class_body_import_is_not_visible_inside_method(tmp_path: Path) -> None:
    _write(
        tmp_path / "scripts/ci.py",
        """class Runner:
    import subprocess

    def run(self) -> None:
        subprocess.run(["python", "scripts/ghost.py"], check=True)
""",
    )
    _write(tmp_path / "AGENTS.md", _agents("python scripts/ghost.py"))

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")

    assert "commands.unlocated-full-gate" in _codes(findings)


def test_global_import_remains_visible_inside_method(tmp_path: Path) -> None:
    _write(
        tmp_path / "scripts/ci.py",
        """import subprocess

class Runner:
    def run(self) -> None:
        subprocess.run(["python", "scripts/ci.py"], check=True)
""",
    )
    _write(tmp_path / "AGENTS.md", _agents("python scripts/ci.py"))

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")

    assert "commands.unlocated-full-gate" not in _codes(findings)


def test_class_body_direct_call_remains_executable_evidence() -> None:
    commands = audit_module._extract_python_invocations(
        """class Runner:
    import subprocess as process
    result = process.run(["python", "scripts/ci.py"], check=True)
"""
    )

    assert "python scripts/ci.py" in commands


def test_class_alias_is_not_visible_to_method_or_lambda() -> None:
    commands = audit_module._extract_python_invocations(
        """class Runner:
    import subprocess as process

    def run(self) -> None:
        process.run(["python", "scripts/method_ghost.py"], check=True)

    callback = lambda: process.run(["python", "scripts/lambda_ghost.py"], check=True)
"""
    )

    assert "python scripts/method_ghost.py" not in commands
    assert "python scripts/lambda_ghost.py" not in commands


def test_global_alias_remains_visible_when_class_shadows_same_name() -> None:
    commands = audit_module._extract_python_invocations(
        """import subprocess as process

class Runner:
    process = object()

    def run(self) -> None:
        process.run(["python", "scripts/ci.py"], check=True)
"""
    )

    assert "python scripts/ci.py" in commands


def test_class_comprehension_body_does_not_close_over_class_namespace() -> None:
    commands = audit_module._extract_python_invocations(
        """class Runner:
    import subprocess
    results = [subprocess.run(["python", "scripts/ghost.py"], check=True) for _ in [1]]
"""
    )

    assert "python scripts/ghost.py" not in commands


def test_class_comprehension_outer_iterable_runs_in_class_scope() -> None:
    commands = audit_module._extract_python_invocations(
        """class Runner:
    import subprocess
    results = [item for item in subprocess.run(["python", "scripts/ci.py"], check=True)]
"""
    )

    assert "python scripts/ci.py" in commands


def test_function_parameter_and_assignment_shadow_process_bindings() -> None:
    commands = audit_module._extract_python_invocations(
        """import subprocess

def parameter(subprocess: object) -> None:
    subprocess.run(["python", "scripts/parameter_ghost.py"])

def assignment() -> None:
    subprocess.run(["python", "scripts/assignment_ghost.py"])
    subprocess = object()
"""
    )

    assert "python scripts/parameter_ghost.py" not in commands
    assert "python scripts/assignment_ghost.py" not in commands


def test_shell_inline_comment_cannot_fabricate_command() -> None:
    commands = shell_evidence._extract_shell_invocations("echo ok # ; python scripts/ghost.py")

    assert "python scripts/ghost.py" not in commands
    assert "echo ok" in commands


def test_shell_hashes_inside_quotes_or_escaping_remain_data() -> None:
    commands = shell_evidence._extract_shell_invocations("echo '# ; not a comment' && echo \\# && python scripts/ci.py")

    assert "python scripts/ci.py" in commands
    assert all("not a comment" not in command or command.startswith("echo") for command in commands)


def test_yaml_literal_shell_comment_cannot_fabricate_command() -> None:
    commands = shell_evidence._extract_yaml_invocations(
        ".github/workflows/ci.yml",
        """jobs:
  test:
    steps:
      - run: |
          echo ok # ; python scripts/ghost.py
""",
    )

    assert "python scripts/ghost.py" not in commands
    assert "echo ok" in commands


def test_azure_powershell_comments_are_not_shell_evidence() -> None:
    commands = shell_evidence._extract_yaml_invocations(
        "azure-pipelines.yml",
        """steps:
  - pwsh: |
      Write-Host ok # ; python scripts/ghost.py
      Write-Host '# still text'; python scripts/ci.py
""",
    )

    assert "python scripts/ghost.py" not in commands
    assert "python scripts/ci.py" in commands


def test_powershell_inline_and_block_comments_cannot_fabricate_commands() -> None:
    commands = shell_evidence._extract_powershell_invocations(
        """Write-Host ok # ; python scripts/inline_ghost.py
<# python scripts/block_ghost.py #>
Write-Host '# not a comment'; python scripts/ci.py
"""
    )

    assert "python scripts/inline_ghost.py" not in commands
    assert "python scripts/block_ghost.py" not in commands
    assert "python scripts/ci.py" in commands


@pytest.mark.parametrize(
    ("name", "text"),
    (
        ("Makefile", "all:\n\techo ok # ; python scripts/ghost.py\n"),
        ("Justfile", "all:\n    echo ok # ; python scripts/ghost.py\n"),
    ),
)
def test_recipe_comments_cannot_fabricate_commands(name: str, text: str) -> None:
    commands = shell_evidence._extract_gate_invocations(name, text)

    assert "python scripts/ghost.py" not in commands
    assert "echo ok" in commands


def test_jenkins_comments_cannot_fabricate_steps() -> None:
    commands = shell_evidence._extract_jenkins_invocations(
        """// sh 'python scripts/line_ghost.py'
/*
powershell 'python scripts/block_ghost.py'
*/
sh 'python scripts/ci.py'
"""
    )

    assert "python scripts/line_ghost.py" not in commands
    assert "python scripts/block_ghost.py" not in commands
    assert "python scripts/ci.py" in commands


def test_completion_fence_nested_in_list_is_audited(tmp_path: Path) -> None:
    _write(
        tmp_path / "AGENTS.md",
        """# AGENTS.md

## Scope

These instructions apply to the repository.

## Commands and verification

- Full gate:

    ```bash
    python scripts/missing_gate.py
    ```

## Safety boundaries

Secrets must not be committed. Destructive writes require explicit authorization and rollback.

## Definition of done

Report the exact revision, skipped checks, and residual risk.
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")

    assert "commands.unlocated-full-gate" in _codes(findings)

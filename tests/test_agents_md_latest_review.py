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
    runs-on: ubuntu-latest
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


@pytest.mark.parametrize(
    "workflow",
    (
        """jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/web
    steps:
      - run: npm run test
""",
        """defaults:
  run:
    working-directory: apps/web
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: npm run test
""",
        """jobs:
  test:
    steps:
      - run: npm run test
        working-directory: apps/web
""",
    ),
)
def test_github_working_directory_cannot_validate_root_gate(tmp_path: Path, workflow: str) -> None:
    _write(tmp_path / ".github/workflows/ci.yml", workflow)
    _write(tmp_path / "AGENTS.md", _agents("npm run test"))

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")

    assert "commands.unlocated-full-gate" in _codes(findings)


def test_github_working_directory_validates_matching_nested_gate(tmp_path: Path) -> None:
    _write(
        tmp_path / ".github/workflows/ci.yml",
        """jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/web
    steps:
      - run: npm run test
""",
    )
    _write(tmp_path / "AGENTS.md", _agents("python scripts/root.py"))
    _write(tmp_path / "scripts/root.py", "print('ok')\n")
    _write(tmp_path / "apps/web/AGENTS.md", _agents("npm run test"))

    _, findings = audit_module.audit(tmp_path, "application", "monorepo", "en")

    nested_gate_findings = {
        item.code for item in findings if item.path == "apps/web/AGENTS.md" and item.code.startswith("commands.")
    }
    assert "commands.unlocated-full-gate" not in nested_gate_findings


def test_github_step_working_directory_overrides_job_default(tmp_path: Path) -> None:
    _write(
        tmp_path / ".github/workflows/ci.yml",
        """jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/api
    steps:
      - run: npm run test
        working-directory: apps/web
""",
    )
    _write(tmp_path / "AGENTS.md", _agents("npm run test"))
    _write(tmp_path / "apps/web/AGENTS.md", _agents("npm run test"))

    _, findings = audit_module.audit(tmp_path, "application", "monorepo", "en")

    assert any(item.path == "AGENTS.md" and item.code == "commands.unlocated-full-gate" for item in findings)
    assert not any(
        item.path == "apps/web/AGENTS.md" and item.code == "commands.unlocated-full-gate" for item in findings
    )


@pytest.mark.parametrize("working_directory", ("${{ matrix.directory }}", "../outside", "/tmp/project", "C:/outside"))
def test_dynamic_or_external_github_working_directory_cannot_establish_evidence(
    tmp_path: Path,
    working_directory: str,
) -> None:
    _write(
        tmp_path / ".github/workflows/ci.yml",
        f"""jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: npm run test
        working-directory: {working_directory}
""",
    )
    _write(tmp_path / "AGENTS.md", _agents("npm run test"))

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")

    assert "commands.unlocated-full-gate" in _codes(findings)


def test_github_explicit_powershell_does_not_treat_comment_as_command() -> None:
    evidence = shell_evidence._extract_yaml_command_evidence(
        ".github/workflows/ci.yml",
        """jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        shell: pwsh
    steps:
      - run: |
          Write-Host ok # ; python scripts/ghost.py
          python scripts/ci.py
""",
    )

    commands = {command for _directory, command in evidence}
    assert "python scripts/ghost.py" not in commands
    assert "python scripts/ci.py" in commands


def test_windows_runner_uses_powershell_default_shell() -> None:
    evidence = shell_evidence._extract_yaml_command_evidence(
        ".github/workflows/ci.yml",
        """jobs:
  test:
    runs-on: windows-latest
    steps:
      - run: |
          $example = @"
          python scripts/ghost.py
          "@
          python scripts/ci.py
""",
    )

    commands = {command for _directory, command in evidence}
    assert "python scripts/ghost.py" not in commands
    assert "python scripts/ci.py" in commands


@pytest.mark.parametrize("shell", ("python", "cmd", "${{ matrix.shell }}"))
def test_unsupported_or_dynamic_github_shell_cannot_establish_evidence(tmp_path: Path, shell: str) -> None:
    _write(
        tmp_path / ".github/workflows/ci.yml",
        f"""jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: npm run test
        shell: {shell}
""",
    )
    _write(tmp_path / "AGENTS.md", _agents("npm run test"))

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")

    assert "commands.unlocated-full-gate" in _codes(findings)


def test_duplicate_yaml_keys_are_invalid_and_cannot_establish_evidence(tmp_path: Path) -> None:
    _write(
        tmp_path / ".github/workflows/ci.yml",
        """jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: npm run test
        run: echo shadowed
""",
    )
    _write(tmp_path / "AGENTS.md", _agents("npm run test"))

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")

    assert "evidence.invalid-yaml" in _codes(findings)
    assert "commands.unlocated-full-gate" in _codes(findings)


def test_github_job_without_runs_on_cannot_establish_evidence(tmp_path: Path) -> None:
    _write(
        tmp_path / ".github/workflows/ci.yml",
        """jobs:
  test:
    defaults:
      run:
        shell: bash
    steps:
      - run: npm run test
""",
    )
    _write(tmp_path / "AGENTS.md", _agents("npm run test"))

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")

    assert "commands.unlocated-full-gate" in _codes(findings)


def test_self_hosted_runner_without_os_or_shell_cannot_establish_evidence(tmp_path: Path) -> None:
    _write(
        tmp_path / ".github/workflows/ci.yml",
        """jobs:
  test:
    runs-on: self-hosted
    steps:
      - run: npm run test
""",
    )
    _write(tmp_path / "AGENTS.md", _agents("npm run test"))

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")

    assert "commands.unlocated-full-gate" in _codes(findings)


def test_self_hosted_runner_with_explicit_shell_can_establish_evidence(tmp_path: Path) -> None:
    _write(
        tmp_path / ".github/workflows/ci.yml",
        """jobs:
  test:
    runs-on: self-hosted
    defaults:
      run:
        shell: bash
    steps:
      - run: npm run test
""",
    )
    _write(tmp_path / "AGENTS.md", _agents("npm run test"))

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")

    assert "commands.unlocated-full-gate" not in _codes(findings)


@pytest.mark.parametrize("condition", ("false", "${{ false }}"))
def test_statically_disabled_github_step_cannot_establish_evidence(
    tmp_path: Path,
    condition: str,
) -> None:
    _write(
        tmp_path / ".github/workflows/ci.yml",
        f"""jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - if: {condition}
        run: npm run test
""",
    )
    _write(tmp_path / "AGENTS.md", _agents("npm run test"))

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")

    assert "commands.unlocated-full-gate" in _codes(findings)


@pytest.mark.parametrize("condition", ("false", "${{ false }}"))
def test_statically_disabled_github_job_cannot_establish_evidence(
    tmp_path: Path,
    condition: str,
) -> None:
    _write(
        tmp_path / ".github/workflows/ci.yml",
        f"""jobs:
  test:
    if: {condition}
    runs-on: ubuntu-latest
    steps:
      - run: npm run test
""",
    )
    _write(tmp_path / "AGENTS.md", _agents("npm run test"))

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")

    assert "commands.unlocated-full-gate" in _codes(findings)


def test_dynamic_github_condition_remains_potentially_executable(tmp_path: Path) -> None:
    _write(
        tmp_path / ".github/workflows/ci.yml",
        """jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - if: ${{ matrix.enabled }}
        run: npm run test
""",
    )
    _write(tmp_path / "AGENTS.md", _agents("npm run test"))

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")

    assert "commands.unlocated-full-gate" not in _codes(findings)


def test_dead_python_suite_does_not_discard_later_real_command() -> None:
    commands = audit_module._extract_python_invocations(
        """def dead() -> None:
    if False:
        print('never')

def real() -> None:
    import subprocess
    subprocess.run(['python', 'scripts/ci.py'], check=True)
"""
    )

    assert "python scripts/ci.py" in commands


def test_just_recipe_with_dependencies_establishes_command_evidence() -> None:
    commands = audit_module._extract_gate_invocations(
        "justfile",
        """build:
    python scripts/build.py

test: build
    pytest -q
""",
    )

    assert "pytest -q" in commands


def test_just_assignment_does_not_start_recipe() -> None:
    commands = audit_module._extract_gate_invocations(
        "justfile",
        """value := 'test'
    python scripts/ghost.py
""",
    )

    assert "python scripts/ghost.py" not in commands


def test_jenkins_triple_quoted_commands_are_extracted() -> None:
    commands = audit_module._extract_gate_invocations(
        "Jenkinsfile",
        """pipeline {
  stages {
    stage('test') {
      steps {
        sh '''
          python -m pytest
          python scripts/ci.py
        '''
        sh \"\"\"
          python scripts/other.py
        \"\"\"
      }
    }
  }
}
""",
    )

    assert "python -m pytest" in commands
    assert "python scripts/ci.py" in commands
    assert "python scripts/other.py" in commands


def test_just_quiet_recipe_with_dependencies_establishes_command_evidence(tmp_path: Path) -> None:
    _write(tmp_path / "justfile", "@test: build\n    pytest -q\n")
    _write(tmp_path / "AGENTS.md", _agents("pytest -q"))

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")

    assert "commands.unlocated-full-gate" not in _codes(findings)


def test_jenkins_single_line_powershell_uses_powershell_parser() -> None:
    commands = shell_evidence._extract_gate_invocations(
        "Jenkinsfile",
        "powershell 'Write-Host ok # ; python scripts/ghost.py'\n",
    )

    assert "python scripts/ghost.py" not in commands

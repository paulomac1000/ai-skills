#!/usr/bin/env python3
"""Apply final fail-closed GitHub Actions evidence corrections after the reviewed patch."""

from __future__ import annotations

from pathlib import Path


def replace_exact(path: Path, old: str, new: str, expected: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    actual = text.count(old)
    if actual != expected:
        raise SystemExit(f"{path}: expected {expected} occurrences, found {actual}")
    path.write_text(text.replace(old, new), encoding="utf-8")


shell_path = Path("skills/agents-md-architect/tools/agents_md_shell_evidence_impl.py")
replace_exact(
    shell_path,
    '''def _github_runner_default_shell(job: Node) -> str | None:
    runs_on = _mapping_value(job, "runs-on")
    if runs_on is None:
        return ""
    values: list[str] = []
    if isinstance(runs_on, ScalarNode):
        values.append(runs_on.value)
    elif isinstance(runs_on, SequenceNode):
        for item in runs_on.value:
            if not isinstance(item, ScalarNode):
                return None
            values.append(item.value)
    else:
        return None
    if any("${{" in value for value in values):
        return None
    return "pwsh" if any("windows" in value.casefold() for value in values) else ""
''',
    '''def _github_runner_default_shell(job: Node) -> tuple[bool, str | None]:
    runs_on = _mapping_value(job, "runs-on")
    if runs_on is None:
        return False, None
    values: list[str] = []
    if isinstance(runs_on, ScalarNode):
        values.append(runs_on.value)
    elif isinstance(runs_on, SequenceNode):
        for item in runs_on.value:
            if not isinstance(item, ScalarNode):
                return False, None
            values.append(item.value)
    else:
        return False, None
    if not values or any(not value.strip() for value in values):
        return False, None
    if any("${{" in value for value in values):
        return True, None
    labels = tuple(value.casefold() for value in values)
    if any("windows" in value for value in labels):
        return True, "pwsh"
    if any(any(marker in value for marker in ("ubuntu", "linux", "macos")) for value in labels):
        return True, ""
    return True, None
''',
)
replace_exact(
    shell_path,
    '''        job_cwd_node, job_shell_node = _github_run_defaults(job)
        job_cwd = _working_directory_override(job_cwd_node, workflow_cwd)
        workflow_shell = _shell_override(workflow_shell_node, _github_runner_default_shell(job))
        job_shell = _shell_override(job_shell_node, workflow_shell)
''',
    '''        has_runner, runner_shell = _github_runner_default_shell(job)
        if not has_runner:
            continue
        job_cwd_node, job_shell_node = _github_run_defaults(job)
        job_cwd = _working_directory_override(job_cwd_node, workflow_cwd)
        workflow_shell = _shell_override(workflow_shell_node, runner_shell)
        job_shell = _shell_override(job_shell_node, workflow_shell)
''',
)

tests_path = Path("tests/test_agents_md_latest_review.py")
replace_exact(
    tests_path,
    '''"""jobs:
  test:
    defaults:
      run:
        working-directory: apps/web
    steps:
''',
    '''"""jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/web
    steps:
''',
    expected=2,
)
replace_exact(
    tests_path,
    '''"""defaults:
  run:
    working-directory: apps/web
jobs:
  test:
    steps:
''',
    '''"""defaults:
  run:
    working-directory: apps/web
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
''',
)
replace_exact(
    tests_path,
    '''"""jobs:
  test:
    defaults:
      run:
        working-directory: apps/api
    steps:
''',
    '''"""jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/api
    steps:
''',
)
replace_exact(
    tests_path,
    '''f"""jobs:
  test:
    steps:
      - run: npm run test
        working-directory: {working_directory}
''',
    '''f"""jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: npm run test
        working-directory: {working_directory}
''',
)
replace_exact(
    tests_path,
    '''"""jobs:
  test:
    defaults:
      run:
        shell: pwsh
''',
    '''"""jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        shell: pwsh
''',
)

with tests_path.open("a", encoding="utf-8") as stream:
    stream.write(
        '''\n\ndef test_github_job_without_runs_on_cannot_establish_evidence(tmp_path: Path) -> None:
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
'''
    )

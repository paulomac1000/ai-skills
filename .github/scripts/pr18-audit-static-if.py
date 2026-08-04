#!/usr/bin/env python3
"""Exclude statically disabled GitHub Actions jobs and steps from command evidence."""

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
    '''def _github_run_defaults(node: Node | None) -> tuple[Node | None, Node | None]:
    run = _mapping_value(_mapping_value(node, "defaults"), "run")
    return _mapping_value(run, "working-directory"), _mapping_value(run, "shell")
''',
    '''def _github_condition_is_statically_false(node: Node | None) -> bool:
    value = _scalar_value(_mapping_value(node, "if"))
    if value is None:
        return False
    normalized = "".join(value.split()).casefold()
    return normalized in {"false", "${{false}}"}


def _github_run_defaults(node: Node | None) -> tuple[Node | None, Node | None]:
    run = _mapping_value(_mapping_value(node, "defaults"), "run")
    return _mapping_value(run, "working-directory"), _mapping_value(run, "shell")
''',
)
replace_exact(
    shell_path,
    '''    for _job_key, job in jobs.value:
        if not isinstance(job, MappingNode):
            continue
        has_runner, runner_shell = _github_runner_default_shell(job)
''',
    '''    for _job_key, job in jobs.value:
        if not isinstance(job, MappingNode) or _github_condition_is_statically_false(job):
            continue
        has_runner, runner_shell = _github_runner_default_shell(job)
''',
)
replace_exact(
    shell_path,
    '''        for step in steps.value:
            if not isinstance(step, MappingNode):
                continue
            run = _scalar_value(_mapping_value(step, "run"))
''',
    '''        for step in steps.value:
            if not isinstance(step, MappingNode) or _github_condition_is_statically_false(step):
                continue
            run = _scalar_value(_mapping_value(step, "run"))
''',
)

tests_path = Path("tests/test_agents_md_latest_review.py")
with tests_path.open("a", encoding="utf-8") as stream:
    stream.write(
        '''\n\n@pytest.mark.parametrize("condition", ("false", "${{ false }}"))
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
'''
    )

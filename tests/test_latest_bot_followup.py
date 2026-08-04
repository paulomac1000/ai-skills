"""Regressions for the final exact-head bot follow-up."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AGENTS_TOOLS = ROOT / "skills/agents-md-architect/tools"
CI_TOOLS = ROOT / "skills/ci-cd-architect/tools"
sys.path.insert(0, str(AGENTS_TOOLS))
sys.path.insert(0, str(CI_TOOLS))

import agents_md_python_evidence as python_evidence  # noqa: E402
import agents_md_shell_evidence as shell_evidence  # noqa: E402
import check_github_actions_policy as workflow_policy  # noqa: E402


@pytest.mark.parametrize(
    "source",
    (
        """import subprocess
if False:
    subprocess.run(["python", "scripts/ghost.py"], check=True)
""",
        """import subprocess
while 0:
    subprocess.run(["python", "scripts/ghost.py"], check=True)
""",
        """import subprocess
result = (
    subprocess.run(["python", "scripts/ghost.py"], check=True)
    if ()
    else None
)
""",
    ),
)
def test_literal_dead_python_branch_cannot_establish_evidence(source: str) -> None:
    commands = python_evidence._extract_python_invocations(source)

    assert "python scripts/ghost.py" not in commands


def test_literal_live_python_branch_remains_evidence() -> None:
    commands = python_evidence._extract_python_invocations(
        """import subprocess
if True:
    subprocess.run(["python", "scripts/ci.py"], check=True)
else:
    subprocess.run(["python", "scripts/ghost.py"], check=True)
"""
    )

    assert "python scripts/ci.py" in commands
    assert "python scripts/ghost.py" not in commands


def test_make_recipe_continuation_establishes_complete_gate() -> None:
    commands = shell_evidence._extract_gate_invocations(
        "Makefile",
        """quality:
	python scripts/ci.py \\
	  --strict \\
	  --profile safety-critical
""",
    )

    assert "python scripts/ci.py --strict --profile safety-critical" in commands
    assert "python scripts/ci.py" not in commands


def test_workflow_reader_rejects_intermediate_symlink(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    outside = tmp_path / "outside"
    workflows = outside / "workflows"
    workflows.mkdir(parents=True)
    workflow = workflows / "ci.yml"
    workflow.write_text("name: outside\n", encoding="utf-8")
    try:
        (repository / ".github").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")

    text, error = workflow_policy._read_workflow(
        repository / ".github" / "workflows" / "ci.yml",
        repository,
    )

    assert text is None
    assert error is not None
    assert "cannot read workflow safely" in error


def test_workflow_enumeration_charges_non_yaml_entries_to_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    workflow_dir = repository / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    for index in range(5):
        (workflow_dir / f"noise-{index}.txt").write_text("noise", encoding="utf-8")
    monkeypatch.setattr(workflow_policy, "MAX_DISCOVERY_ENTRIES", 3)

    paths, findings = workflow_policy.workflow_paths(repository)

    assert paths == []
    assert any("entry count exceeds 3" in finding.message for finding in findings)

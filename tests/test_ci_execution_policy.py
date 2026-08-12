"""Regression tests for cost-aware GitHub Actions execution policy."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills/ci-cd-architect/tools"
TEMPLATE = ROOT / "skills/ci-cd-architect/templates/on-demand-ci.yaml.template"
sys.path.insert(0, str(TOOLS))
import check_ci_execution_policy as policy  # noqa: E402
import check_github_actions_policy_impl as trust_policy  # noqa: E402


def _audit(text: str, branches: tuple[str, ...] = ("main", "master")) -> list[str]:
    findings = policy.audit_text(
        Path(".github/workflows/ci.yml"),
        text,
        integration_branches=branches,
    )
    return [finding.message for finding in findings]


def _workflow(events: str) -> str:
    return f"""# ai-skills-execution-policy: on-demand
name: CI
on:
{events}
permissions:
  contents: read
concurrency:
  group: ci-${{{{ github.ref }}}}
  cancel-in-progress: true
jobs:
  validate:
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    steps:
      - run: echo ok
"""


def _render_template() -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    replacements = {
        "<DEFAULT_BRANCH>": "main",
        "<FAST_TIMEOUT_MINUTES>": "10",
        "<FULL_TIMEOUT_MINUTES>": "45",
        "<PYTHON_VERSION>": "3.13",
        "<DEPENDENCY_FILE>": "requirements-dev.lock",
        "<INSTALL_COMMAND>": "python -m pip install -r requirements-dev.lock",
        "<FAST_CHECK_COMMAND>": "python -m compileall -q src tests",
        "<FULL_CHECK_COMMAND>": "python -m pytest",
        "<ARTIFACT_CHECK_COMMAND>": "docker build .",
        "<TEST_ARTIFACT_PATH>": "test-results",
    }
    for token, value in replacements.items():
        text = text.replace(token, value)
    return text


def test_accepts_manual_plus_integration_push() -> None:
    assert _audit(_workflow("  push:\n    branches: [main]\n  workflow_dispatch:\n")) == []


def test_accepts_manual_only_expensive_workflow() -> None:
    assert _audit(_workflow("  workflow_dispatch:\n")) == []


def test_rejects_pull_request_and_unrestricted_push() -> None:
    findings = _audit(_workflow("  push:\n  pull_request:\n  workflow_dispatch:\n"))
    assert any("pull_request" in finding for finding in findings)
    assert any("push trigger must be a mapping" in finding for finding in findings)


def test_rejects_feature_branch_and_tag_push() -> None:
    findings = _audit(_workflow('  push:\n    branches: [main, feature]\n    tags: ["*"]\n  workflow_dispatch:\n'))
    assert any("feature" in finding for finding in findings)
    assert any("tags" in finding for finding in findings)


def test_requires_manual_dispatch() -> None:
    findings = _audit(_workflow("  push:\n    branches: [main]\n"))
    assert any("workflow_dispatch" in finding for finding in findings)


def test_requires_cancel_in_progress() -> None:
    text = _workflow("  workflow_dispatch:\n").replace("cancel-in-progress: true", "cancel-in-progress: false")
    assert any("cancel-in-progress" in finding for finding in _audit(text))


def test_full_input_is_boolean_and_defaults_false() -> None:
    good = _workflow("  workflow_dispatch:\n    inputs:\n      full:\n        type: boolean\n        default: false\n")
    assert _audit(good) == []
    bad = good.replace("type: boolean", "type: string").replace("default: false", "default: true")
    findings = _audit(bad)
    assert any("type: boolean" in finding for finding in findings)
    assert any("default to false" in finding for finding in findings)


def test_custom_integration_branch_is_explicit() -> None:
    text = _workflow("  push:\n    branches: [trunk]\n  workflow_dispatch:\n")
    assert _audit(text, ("trunk",)) == []


def test_template_is_manual_on_branches_and_full_on_integration_push(tmp_path: Path) -> None:
    rendered = _render_template()
    workflow = tmp_path / "ci.yml"
    workflow.write_text(rendered, encoding="utf-8")
    assert (
        policy.audit_text(
            Path(".github/workflows/ci.yml"),
            rendered,
            integration_branches=("main",),
        )
        == []
    )

    def reader(path: Path, _root: Path) -> tuple[str | None, str | None]:
        return path.read_text(encoding="utf-8"), None

    assert trust_policy.audit_workflow(workflow, tmp_path, reader=reader) == []
    document = yaml.safe_load(rendered)
    events = document.get("on", document.get(True))
    assert set(events) == {"push", "workflow_dispatch"}
    assert events["push"]["branches"] == ["main"]
    assert "pull_request" not in events
    full = document["jobs"]["full"]
    assert full["needs"] == "validate"
    assert full["if"] == "github.event_name == 'push' || inputs.full == true"


def test_repository_scan_only_enforces_marked_workflows(tmp_path: Path) -> None:
    workflows = tmp_path / ".github/workflows"
    workflows.mkdir(parents=True)
    (workflows / "cost-aware.yml").write_text(_workflow("  workflow_dispatch:\n"), encoding="utf-8")
    (workflows / "labeler.yml").write_text("name: Labeler\non: pull_request_target\n", encoding="utf-8")
    assert policy.audit_repository(tmp_path) == []

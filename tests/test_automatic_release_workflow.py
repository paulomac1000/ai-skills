from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / ".github" / "workflows" / "release.yml"
CI = ROOT / ".github" / "workflows" / "ci.yml"


def _load(path: Path) -> dict[str, object]:
    value = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert isinstance(value, dict)
    return value


def test_release_waits_for_successful_main_push_ci() -> None:
    workflow = _load(RELEASE)
    trigger = workflow["on"]
    assert isinstance(trigger, dict)
    workflow_run = trigger["workflow_run"]
    assert isinstance(workflow_run, dict)
    assert workflow_run["workflows"] == ["CI"]
    assert workflow_run["types"] == ["completed"]
    assert workflow_run["branches"] == ["main"]

    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    prepare = jobs["prepare"]
    assert isinstance(prepare, dict)
    condition = str(prepare["if"])
    assert "workflow_run.conclusion == 'success'" in condition
    assert "workflow_run.event == 'push'" in condition
    assert "workflow_run.head_branch == 'main'" in condition


def test_release_publisher_is_separate_and_does_not_checkout_or_build_candidate() -> None:
    workflow = _load(RELEASE)
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    publish = jobs["publish"]
    assert isinstance(publish, dict)
    assert publish["needs"] == "prepare"
    assert publish["environment"] == "release"
    permissions = publish["permissions"]
    assert isinstance(permissions, dict)
    assert permissions == {"contents": "write"}

    steps = publish["steps"]
    assert isinstance(steps, list)
    rendered = "\n".join(str(step) for step in steps)
    assert "actions/checkout" not in rendered
    assert "git archive" not in rendered
    assert "python -m build" not in rendered
    assert "gh release create" in rendered
    assert "sha256sum -c SHA256SUMS" in rendered


def test_main_ci_runs_are_not_cancelled_by_later_main_pushes() -> None:
    workflow = _load(CI)
    concurrency = workflow["concurrency"]
    assert isinstance(concurrency, dict)
    group = str(concurrency["group"])
    assert "github.event_name == 'push'" in group
    assert "github.sha" in group
    assert "github.ref" in group
    assert concurrency["cancel-in-progress"] == "true"


def test_repository_release_policy_defaults_to_automatic_finalization() -> None:
    skill = (ROOT / "skills/changelog-release-architect/SKILL.md").read_text(encoding="utf-8")
    standard = (ROOT / "skills/changelog-release-architect/STANDARD.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "Never publish, tag, deploy, or create a provider release unless explicitly requested." not in skill
    assert "automatic-after-integration" in skill
    assert "do not ask for an additional publication confirmation" in skill
    assert "## Publication finalization" in standard
    assert "automatic-after-integration" in standard
    assert ".github/workflows/release.yml" in agents

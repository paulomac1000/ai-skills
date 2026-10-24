"""Workflow execution-contract regressions for the integration audit path.

String-presence assertions cannot distinguish a step that executes from a
step that is conditioned away, reordered, or removed. These tests pin the
executable contract of the exact-head audit job and the release admission
step: the mandatory steps must be present, unconditional, and ordered, and
the step scripts embedded in the workflows must behave correctly when they
are actually executed against synthetic event and provider state. Each
validator is falsified by injecting the exact mutations a reviewer would
look for, so the suite rejects them instead of merely describing the
current text.
"""

from __future__ import annotations

import copy
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


def _bash_works() -> bool:
    """Whether this environment can execute the workflow steps' bash scripts."""
    try:
        probe = subprocess.run(
            ["bash", "-c", "echo ok"],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0 and b"ok" in probe.stdout


BASH_AVAILABLE = _bash_works()

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github/workflows/ci.yml"
RELEASE = ROOT / ".github/workflows/release.yml"

AUDIT_JOB = "exact-head"
RESOLVE_STEP = "Resolve the integration base for the event"
FETCH_STEP = "Fetch the integration base from the provider"
HEAD_STEP = "Verify exact branch head"
VERSION_STEP = "Verify stable release versions changed with shipped contracts"
AUTHORSHIP_STEP = "Verify commit authorship of the integration range"
GATE_STEP = "Execute complete local gate on exact head"
MANDATORY_AUDIT_STEPS = (RESOLVE_STEP, FETCH_STEP, HEAD_STEP, VERSION_STEP, AUTHORSHIP_STEP, GATE_STEP)

ADMISSION_STEP = "Verify the mandatory integration audit executed on this revision"
UPLOAD_STEP = "Upload prepared release payload"


def _load(path: Path) -> dict[str, object]:
    value = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert isinstance(value, dict)
    return value


def _steps(workflow: dict[str, object], job: str) -> list[dict[str, object]]:
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    target = jobs[job]
    assert isinstance(target, dict)
    steps = target["steps"]
    assert isinstance(steps, list)
    return [step for step in steps if isinstance(step, dict)]


def _step(steps: list[dict[str, object]], name: str) -> dict[str, object]:
    for step in steps:
        if step.get("name") == name:
            return step
    raise AssertionError(f"step {name!r} is missing")


def _failure_masking_enabled(step: dict[str, object]) -> bool:
    """Whether the step tolerates its own failure under any spelling.

    Fail closed: any present continue-on-error value that is not an explicit
    false is treated as failure masking, because GitHub Actions expressions
    such as ${{ true }} or ${{ always() }} evaluate truthy at runtime while
    carrying no literal the validator could trust.
    """
    value = step.get("continue-on-error", False)
    return value is not False and str(value).casefold() != "false"


def _exact_head_violations(workflow: dict[str, object]) -> list[str]:
    """Return every way the audit job could execute less than it declares."""
    violations: list[str] = []
    steps = _steps(workflow, AUDIT_JOB)
    names = [str(step.get("name")) for step in steps]
    for step in steps:
        label = str(step.get("name") or step.get("uses") or step.get("run"))[:60]
        if step.get("if") is not None:
            violations.append(f"conditional audit step can be skipped: {label}")
        if _failure_masking_enabled(step):
            violations.append(f"failure-masking audit step can fail without failing the job: {label}")
    positions: list[int] = []
    for required in MANDATORY_AUDIT_STEPS:
        if required not in names:
            violations.append(f"mandatory audit step missing: {required}")
        else:
            positions.append(names.index(required))
    if len(positions) == len(MANDATORY_AUDIT_STEPS) and positions != sorted(positions):
        violations.append("mandatory audit steps are out of order")
    if GATE_STEP in names and names.index(GATE_STEP) != len(names) - 1:
        violations.append("the complete local gate is not the final audit step")
    authorship = next((step for step in steps if step.get("name") == AUTHORSHIP_STEP), None)
    if authorship is not None:
        run = str(authorship.get("run"))
        if "$BASE_SHA" not in run or "$HEAD_SHA" not in run:
            violations.append("authorship step does not audit the resolved base and event head")
        if "check_commit_authorship.py" not in run:
            violations.append("authorship step does not invoke the authorship checker")
    resolve = next((step for step in steps if step.get("name") == RESOLVE_STEP), None)
    if resolve is not None:
        run = str(resolve.get("run"))
        if "resolve_integration_base.py" not in run:
            violations.append("base resolution does not pass through the fail-closed resolver")
    return violations


def _release_admission_violations(workflow: dict[str, object]) -> list[str]:
    """Return every way publication could proceed without admission proof."""
    violations: list[str] = []
    steps = _steps(workflow, "prepare")
    names = [str(step.get("name")) for step in steps]
    if ADMISSION_STEP not in names:
        return [f"mandatory admission step missing: {ADMISSION_STEP}"]
    admission = _step(steps, ADMISSION_STEP)
    if admission.get("if") is not None:
        violations.append("the admission step is conditional and can be skipped")
    if _failure_masking_enabled(admission):
        violations.append("the admission step can fail without failing preparation")
    if UPLOAD_STEP in names and names.index(ADMISSION_STEP) > names.index(UPLOAD_STEP):
        violations.append("the admission step does not gate release preparation")
    run = str(admission.get("run"))
    if "verify_release_admission.py" not in run:
        violations.append("the admission step does not invoke the admission verifier")
    if "github.event.workflow_run.id" not in str(admission.get("env")):
        violations.append("the admission step is not bound to the triggering run id")
    return violations


def test_the_real_audit_job_satisfies_the_execution_contract() -> None:
    assert _exact_head_violations(_load(CI)) == []


def test_the_real_release_admission_satisfies_the_execution_contract() -> None:
    assert _release_admission_violations(_load(RELEASE)) == []


def test_conditioning_the_authorship_step_away_is_rejected() -> None:
    """F1 negative: `if: false` on the authorship step must fail the contract."""
    workflow = _load(CI)
    mutated = copy.deepcopy(workflow)
    steps = _steps(mutated, AUDIT_JOB)
    _step(steps, AUTHORSHIP_STEP)["if"] = "false"
    violations = _exact_head_violations(mutated)
    assert any("conditional audit step" in violation for violation in violations)


def test_failure_masking_the_authorship_step_is_rejected() -> None:
    """A failed mandatory step must not be allowed to leave the job green."""
    workflow = _load(CI)
    mutated = copy.deepcopy(workflow)
    steps = _steps(mutated, AUDIT_JOB)
    _step(steps, AUTHORSHIP_STEP)["continue-on-error"] = "true"
    violations = _exact_head_violations(mutated)
    assert any("failure-masking audit step" in violation for violation in violations)


def test_expression_failure_masking_is_rejected() -> None:
    """R4-F1: an expression that evaluates truthy at runtime is masking."""
    for spelling in ("${{ true }}", "${{ always() }}", "${{ !cancelled() }}"):
        workflow = _load(CI)
        mutated = copy.deepcopy(workflow)
        steps = _steps(mutated, AUDIT_JOB)
        _step(steps, AUTHORSHIP_STEP)["continue-on-error"] = spelling
        violations = _exact_head_violations(mutated)
        assert any("failure-masking audit step" in violation for violation in violations), spelling


def test_an_explicit_false_continue_on_error_is_not_masking() -> None:
    """The negative control: an explicit false is the only tolerated spelling."""
    workflow = _load(CI)
    mutated = copy.deepcopy(workflow)
    steps = _steps(mutated, AUDIT_JOB)
    _step(steps, AUTHORSHIP_STEP)["continue-on-error"] = "false"
    assert _exact_head_violations(mutated) == []


def test_failure_masking_the_admission_step_is_rejected() -> None:
    """A failed admission step must not be allowed to continue preparation."""
    workflow = _load(RELEASE)
    mutated = copy.deepcopy(workflow)
    steps = _steps(mutated, "prepare")
    _step(steps, ADMISSION_STEP)["continue-on-error"] = "${{ true }}"
    violations = _release_admission_violations(mutated)
    assert any("admission step can fail" in violation for violation in violations)


def test_removing_the_authorship_step_is_rejected() -> None:
    workflow = _load(CI)
    mutated = copy.deepcopy(workflow)
    steps = _steps(mutated, AUDIT_JOB)
    mutated_steps = [step for step in steps if step.get("name") != AUTHORSHIP_STEP]
    jobs = mutated["jobs"]
    assert isinstance(jobs, dict)
    job = jobs[AUDIT_JOB]
    assert isinstance(job, dict)
    job["steps"] = mutated_steps
    violations = _exact_head_violations(mutated)
    assert any("mandatory audit step missing" in violation for violation in violations)


def test_reordering_the_gate_before_the_audit_is_rejected() -> None:
    workflow = _load(CI)
    mutated = copy.deepcopy(workflow)
    jobs = mutated["jobs"]
    assert isinstance(jobs, dict)
    job = jobs[AUDIT_JOB]
    assert isinstance(job, dict)
    job_steps = job["steps"]
    assert isinstance(job_steps, list)
    gate = _step([step for step in job_steps if isinstance(step, dict)], GATE_STEP)
    job_steps.remove(gate)
    job_steps.insert(0, gate)
    violations = _exact_head_violations(mutated)
    assert any("out of order" in violation for violation in violations)
    assert any("not the final audit step" in violation for violation in violations)


def test_conditioning_the_admission_step_away_is_rejected() -> None:
    """F2 negative: `if: false` on the admission step must fail the contract."""
    workflow = _load(RELEASE)
    mutated = copy.deepcopy(workflow)
    steps = _steps(mutated, "prepare")
    _step(steps, ADMISSION_STEP)["if"] = "false"
    violations = _release_admission_violations(mutated)
    assert any("admission step is conditional" in violation for violation in violations)


def test_removing_the_admission_step_is_rejected() -> None:
    workflow = _load(RELEASE)
    mutated = copy.deepcopy(workflow)
    steps = _steps(mutated, "prepare")
    kept = [step for step in steps if step.get("name") != ADMISSION_STEP]
    jobs = mutated["jobs"]
    assert isinstance(jobs, dict)
    job = jobs["prepare"]
    assert isinstance(job, dict)
    job["steps"] = kept
    violations = _release_admission_violations(mutated)
    assert any("admission step missing" in violation for violation in violations)


def _run_workflow_step(step: dict[str, object], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Execute one workflow step's run script the way a runner would."""
    script = str(step["run"])
    shell = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", script],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    return shell


def _venv_env(extra: dict[str, str]) -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = f"{ROOT / '.venv' / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    env.update(extra)
    return env


@pytest.mark.skipif(sys.platform == "win32" or not BASH_AVAILABLE, reason="workflow steps execute through a POSIX bash")
def test_the_embedded_base_resolution_step_selects_each_event_base(tmp_path: Path) -> None:
    """The step script embedded in the real workflow resolves both event shapes."""
    workflow = _load(CI)
    step = _step(_steps(workflow, AUDIT_JOB), RESOLVE_STEP)
    github_env = tmp_path / "github_env"

    for event_base, expected in (
        ("c" * 40, "c" * 40),
        ("d" * 40, "d" * 40),
    ):
        github_env.write_text("", encoding="utf-8")
        result = _run_workflow_step(
            step,
            _venv_env({"EVENT_BASE": event_base, "GITHUB_ENV": str(github_env)}),
            ROOT,
        )
        assert result.returncode == 0, result.stderr
        assert f"BASE_SHA={expected}" in github_env.read_text(encoding="utf-8")

    for rejected in ("0" * 40, "abc123", ""):
        github_env.write_text("", encoding="utf-8")
        result = _run_workflow_step(
            step,
            _venv_env({"EVENT_BASE": rejected, "GITHUB_ENV": str(github_env)}),
            ROOT,
        )
        assert result.returncode != 0, rejected
        assert github_env.read_text(encoding="utf-8") == ""


def _gh_shim(directory: Path, fixtures: dict[str, Path]) -> Path:
    """A gh replacement that serves synthetic provider records by URL."""
    shim = directory / "gh"
    routes = "\n".join(
        f'  case "$2" in *"{fragment}"*) cat "{path}"; exit 0;; esac' for fragment, path in fixtures.items()
    )
    shim.write_text(
        f'#!/usr/bin/env bash\nurl="$2"\n{routes}\necho "shim: no fixture for $2" >&2\nexit 1\n',
        encoding="utf-8",
    )
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    return directory


def _isolated_step_workspace(tmp_path: Path) -> Path:
    """A workspace where the step's relative script path resolves but its
    redirects stay out of the repository checkout."""
    workspace = tmp_path / "step-workspace"
    workspace.mkdir(exist_ok=True)
    link = workspace / "scripts"
    if not link.exists():
        link.symlink_to(ROOT / "scripts")
    return workspace


@pytest.mark.skipif(sys.platform == "win32" or not BASH_AVAILABLE, reason="workflow steps execute through a POSIX bash")
def test_the_embedded_admission_step_blocks_publication_without_a_real_audit(tmp_path: Path) -> None:
    """F2 behavioral: the workflow's own admission step, executed against
    synthetic provider records, refuses skipped, failed, absent, and
    mismatched audits and accepts only a proven one."""
    workflow = _load(RELEASE)
    step = _step(_steps(workflow, "prepare"), ADMISSION_STEP)
    release_sha = "a" * 40

    def _write_fixtures(workspace: Path, jobs: dict[str, object], head_sha: str) -> None:
        run = {
            "id": 1234,
            "name": "CI",
            "event": "push",
            "head_sha": head_sha,
            "head_branch": "main",
            "conclusion": "success",
        }
        (workspace / "run.json").write_text(json.dumps(run), encoding="utf-8")
        (workspace / "jobs.json").write_text(json.dumps(jobs), encoding="utf-8")

    def _jobs_page(*jobs: tuple[str, str]) -> dict[str, object]:
        return {
            "total_count": len(jobs),
            "jobs": [{"name": name, "conclusion": conclusion} for name, conclusion in jobs],
        }

    cases: tuple[tuple[str, dict[str, object], str, int], ...] = (
        ("proven", _jobs_page(("python", "success"), (AUDIT_JOB, "success")), release_sha, 0),
        ("skipped", _jobs_page(("python", "success"), (AUDIT_JOB, "skipped")), release_sha, 1),
        (
            "failed",
            _jobs_page(
                (AUDIT_JOB, "failure"),
            ),
            release_sha,
            1,
        ),
        (
            "absent",
            _jobs_page(
                ("python", "success"),
            ),
            release_sha,
            1,
        ),
        (
            "mismatched-sha",
            _jobs_page(
                (AUDIT_JOB, "success"),
            ),
            "b" * 40,
            1,
        ),
    )
    for label, jobs_page, head_sha, expected in cases:
        workspace = tmp_path / label
        workspace.mkdir()
        _write_fixtures(workspace, jobs_page, head_sha)
        shim_dir = workspace / "bin"
        shim_dir.mkdir()
        _gh_shim(
            shim_dir, {"/actions/runs/1234/jobs": workspace / "jobs.json", "/actions/runs/1234": workspace / "run.json"}
        )
        env = _venv_env(
            {
                "PATH": os.pathsep.join((str(shim_dir), str(ROOT / ".venv" / "bin"), os.environ.get("PATH", ""))),
                "GITHUB_REPOSITORY": "paulomac1000/ai-skills",
                "RUN_ID": "1234",
                "RELEASE_SHA": release_sha,
                "GH_TOKEN": "shim-token",
                "GH_REPO": "paulomac1000/ai-skills",
            }
        )
        result = _run_workflow_step(step, env, _isolated_step_workspace(tmp_path))
        assert result.returncode == expected, (label, result.stdout, result.stderr)
        if expected == 0:
            assert "release admission: PASS" in result.stdout
        else:
            assert "ERROR: RELEASE_ADMISSION" in result.stdout


@pytest.mark.skipif(sys.platform == "win32" or not BASH_AVAILABLE, reason="workflow steps execute through a POSIX bash")
def test_the_embedded_admission_step_rejects_an_absent_audit(tmp_path: Path) -> None:
    workflow = _load(RELEASE)
    step = _step(_steps(workflow, "prepare"), ADMISSION_STEP)
    release_sha = "a" * 40
    workspace = tmp_path / "absent"
    workspace.mkdir()
    run = {
        "id": 1234,
        "name": "CI",
        "event": "push",
        "head_sha": release_sha,
        "head_branch": "main",
        "conclusion": "success",
    }
    jobs = {"total_count": 1, "jobs": [{"name": "python", "conclusion": "success"}]}
    run_file = workspace / "run.json"
    jobs_file = workspace / "jobs.json"
    run_file.write_text(json.dumps(run), encoding="utf-8")
    jobs_file.write_text(json.dumps(jobs), encoding="utf-8")
    shim_dir = workspace / "bin"
    shim_dir.mkdir()
    _gh_shim(shim_dir, {"/actions/runs/1234/jobs": jobs_file, "/actions/runs/1234": run_file})
    env = _venv_env(
        {
            "PATH": os.pathsep.join((str(shim_dir), str(ROOT / ".venv" / "bin"), os.environ.get("PATH", ""))),
            "GITHUB_REPOSITORY": "paulomac1000/ai-skills",
            "RUN_ID": "1234",
            "RELEASE_SHA": release_sha,
            "GH_TOKEN": "shim-token",
            "GH_REPO": "paulomac1000/ai-skills",
        }
    )
    result = _run_workflow_step(step, env, _isolated_step_workspace(tmp_path))
    assert result.returncode == 1
    assert "RELEASE_ADMISSION_AUDIT_ABSENT" in result.stdout

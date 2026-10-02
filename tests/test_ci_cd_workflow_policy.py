import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills/ci-cd-architect/tools"
sys.path.insert(0, str(TOOLS))

import check_github_actions_policy_impl as policy_impl  # noqa: E402
from check_github_actions_policy import audit_repository, audit_workflow  # noqa: E402


def _workflow(body: str) -> str:
    return (
        """
name: test
on: pull_request
permissions:
  contents: read
concurrency:
  group: test
  cancel-in-progress: true
jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          persist-credentials: false
"""
        + body
    ).lstrip()


def _messages(path: Path) -> list[str]:
    return [finding.message for finding in audit_workflow(path, path.parent)]


def test_safe_workflow_passes(tmp_path: Path) -> None:
    workflow = tmp_path / "safe.yml"
    workflow.write_text(_workflow(""), encoding="utf-8")
    assert _messages(workflow) == []


@pytest.mark.parametrize("permissions", ("read-all", "write-all", "none"))
def test_permission_shorthands_are_rejected(tmp_path: Path, permissions: str) -> None:
    workflow = tmp_path / "permissions.yml"
    workflow.write_text(
        _workflow("").replace("permissions:\n  contents: read", f"permissions: {permissions}"),
        encoding="utf-8",
    )
    assert any("explicit mapping" in message for message in _messages(workflow))


def test_additional_pr_read_scope_is_rejected_at_workflow_and_job_level(
    tmp_path: Path,
) -> None:
    workflow = tmp_path / "permissions.yml"
    workflow.write_text(
        _workflow(
            """
    permissions:
      contents: read
      packages: read
"""
        ).replace("permissions:\n  contents: read", "permissions:\n  actions: read"),
        encoding="utf-8",
    )
    messages = _messages(workflow)
    assert any("workflow grants actions: read" in message for message in messages)
    assert any("job 'test' grants packages: read" in message for message in messages)


@pytest.mark.parametrize(
    "reference",
    (
        "${{ secrets.TOKEN }}",
        "${{ secrets['TOKEN'] }}",
        '${{ secrets["TOKEN"] }}',
        "${{ toJSON(secrets) }}",
    ),
)
def test_pr_secret_context_is_rejected(tmp_path: Path, reference: str) -> None:
    workflow = tmp_path / "secret.yml"
    workflow.write_text(
        _workflow(
            f"""
    env:
      TOKEN: {reference}
"""
        ),
        encoding="utf-8",
    )
    assert any("must not reference repository secrets" in message for message in _messages(workflow))


@pytest.mark.parametrize(
    ("uses", "expected"),
    (
        ("actions/checkout@v7", "full 40-character SHA"),
        (
            "https://example.invalid/action@3d3c42e5aac5ba805825da76410c181273ba90b1",
            "invalid owner/repository",
        ),
        ("docker://alpine@sha256:not-a-digest", "exact sha256 digest"),
        ("docker://alpine:3.20", "exact sha256 digest"),
    ),
)
def test_mutable_or_malformed_actions_are_rejected(
    tmp_path: Path,
    uses: str,
    expected: str,
) -> None:
    workflow = tmp_path / "action.yml"
    workflow.write_text(
        _workflow("").replace(
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
            uses,
        ),
        encoding="utf-8",
    )
    assert any(expected in message for message in _messages(workflow))


def test_exact_docker_digest_is_accepted(tmp_path: Path) -> None:
    digest = "a" * 64
    workflow = tmp_path / "docker.yml"
    workflow.write_text(
        _workflow(
            f"""
      - uses: docker://alpine@sha256:{digest}
"""
        ),
        encoding="utf-8",
    )
    assert _messages(workflow) == []


@pytest.mark.parametrize(
    "runs_on",
    ("ubuntu-latest", " Ubuntu-Latest ", "${{ matrix.os }}", "[ubuntu-24.04]"),
)
def test_runner_must_be_concrete_literal(tmp_path: Path, runs_on: str) -> None:
    workflow = tmp_path / "runner.yml"
    workflow.write_text(
        _workflow("").replace("runs-on: ubuntu-24.04", f"runs-on: {runs_on}"),
        encoding="utf-8",
    )
    messages = _messages(workflow)
    assert any("runner" in message or "runs-on" in message for message in messages)


@pytest.mark.parametrize("events", ("{}", "[]"))
def test_empty_events_are_rejected(tmp_path: Path, events: str) -> None:
    workflow = tmp_path / "events.yml"
    workflow.write_text(
        _workflow("").replace("on: pull_request", f"on: {events}"),
        encoding="utf-8",
    )
    assert any("must declare events" in message for message in _messages(workflow))


def test_duplicate_keys_are_rejected(tmp_path: Path) -> None:
    workflow = tmp_path / "duplicate.yml"
    workflow.write_text(
        _workflow("") + "\npermissions:\n  contents: read\n",
        encoding="utf-8",
    )
    assert any("duplicate key" in message for message in _messages(workflow))


def test_repository_discovery_rejects_symlink_workflow(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    target = tmp_path / "outside.yml"
    target.write_text(_workflow(""), encoding="utf-8")
    try:
        (workflow_dir / "ci.yml").symlink_to(target)
    except OSError as error:
        pytest.skip(f"symlink creation is unavailable: {error}")

    assert any("non-symlink" in finding.message for finding in audit_repository(tmp_path))


def test_audit_rejects_dotdot_escape_outside_repository(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    workflow_dir = repository / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    outside = tmp_path / "outside.yml"
    outside.write_text(_workflow(""), encoding="utf-8")
    escaped = workflow_dir / ".." / ".." / ".." / outside.name

    messages = [finding.message for finding in audit_workflow(escaped, repository)]

    assert any("cannot read workflow safely" in message for message in messages)


def test_impl_requires_explicit_hardened_dependencies() -> None:
    workflow_parameters = inspect.signature(policy_impl.audit_workflow).parameters
    repository_parameters = inspect.signature(policy_impl.audit_repository).parameters

    assert workflow_parameters["reader"].default is inspect.Parameter.empty
    assert repository_parameters["reader"].default is inspect.Parameter.empty
    assert repository_parameters["enumerator"].default is inspect.Parameter.empty
    assert not hasattr(policy_impl, "main")


def _protected_release_workflow(publish_steps: str, *, validation_steps: str = "") -> str:
    return f"""
# ai-skills-policy-profile: protected-release
name: publish
on:
  workflow_dispatch:
permissions:
  contents: read
concurrency:
  group: publish
  cancel-in-progress: false
jobs:
  validate:
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    steps:
{validation_steps or "      - run: echo validated"}
  publish:
    needs: validate
    environment: production
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    permissions:
      contents: read
      packages: write
    steps:
{publish_steps}
""".lstrip()


def test_protected_release_allows_candidate_load_only_in_unprivileged_validation(tmp_path: Path) -> None:
    workflow = tmp_path / "publish.yml"
    workflow.write_text(
        _protected_release_workflow(
            "      - run: docker buildx imagetools create --tag ghcr.io/acme/app:release ghcr.io/acme/app@sha256:" + "a" * 64,
            validation_steps="      - run: docker load --input bundle/release/image.tar",
        ),
        encoding="utf-8",
    )
    assert _messages(workflow) == []


@pytest.mark.parametrize(
    ("run", "expected"),
    (
        ("docker load --input bundle/release/image.tar", "load a candidate image"),
        ("docker image load --input bundle/release/image.tar", "load a candidate image"),
        ("docker build -t candidate .", "build a candidate image"),
        ("docker buildx build --load -t candidate .", "build a candidate image"),
        ("docker run --rm candidate:tested", "execute a candidate image"),
        ("python -m build", "build a candidate package"),
        ("npm pack", "build a candidate package"),
        ("dotnet pack -c Release", "build or execute candidate code"),
        ("git clone https://example.invalid/repo.git src", "check out or materialize repository source"),
    ),
)
def test_protected_release_rejects_candidate_materialization_build_or_execution(
    tmp_path: Path,
    run: str,
    expected: str,
) -> None:
    workflow = tmp_path / "publish.yml"
    workflow.write_text(
        _protected_release_workflow(f"      - run: {run}"),
        encoding="utf-8",
    )
    messages = _messages(workflow)
    assert any(expected in message and "protected publisher" in message for message in messages)


def test_protected_release_allows_registry_native_exact_digest_promotion(tmp_path: Path) -> None:
    workflow = tmp_path / "publish.yml"
    workflow.write_text(
        _protected_release_workflow(
            """      - name: promote exact digest
        run: |
          set -euo pipefail
          source_ref="ghcr.io/acme/quarantine@sha256:${DIGEST}"
          docker buildx imagetools create --tag ghcr.io/acme/app:release "$source_ref"
          docker buildx imagetools inspect ghcr.io/acme/app:release
"""
        ),
        encoding="utf-8",
    )
    assert _messages(workflow) == []


def test_protected_release_rejects_checkout_action_in_write_job(tmp_path: Path) -> None:
    workflow = tmp_path / "publish.yml"
    workflow.write_text(
        _protected_release_workflow(
            """      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          persist-credentials: false
"""
        ),
        encoding="utf-8",
    )
    assert any("must not execute repository source" in message for message in _messages(workflow))

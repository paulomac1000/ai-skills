"""Fail-closed regressions for provider control and GitHub run classification."""

from __future__ import annotations

import importlib.util
import sys
import urllib.error
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
CI_TOOLS = ROOT / "skills/ci-cd-architect/tools"
CONTRACTS = ROOT / "contracts"


def _load(path: Path, name: str) -> ModuleType:
    for candidate in (path.parent, CONTRACTS):
        if str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PROVIDER = _load(CI_TOOLS / "check_github_provider_controls.py", "provider_control_edge_cases")
CLASSIFIER = _load(CI_TOOLS / "classify_github_run_evidence.py", "github_run_classifier_edge_cases")


class FakeClient:
    def __init__(self, responses: dict[str, tuple[int, object | None, str]]) -> None:
        self.responses = responses

    def get(self, path: str) -> tuple[int, object | None, str]:
        return self.responses.get(path, (404, None, "not found"))


def _repository(root: Path, *, release_environment: str | None = None) -> None:
    workflows = root / ".github/workflows"
    workflows.mkdir(parents=True)
    if release_environment is None:
        policy = "schema_version: 1\nworkflows: {}\n"
    else:
        policy = "schema_version: 1\nworkflows:\n  .github/workflows/release.yml: protected-release\n"
        (workflows / "release.yml").write_text(
            "# ai-skills-policy-profile: protected-release\n"
            "name: release\n"
            "on: workflow_dispatch\n"
            "jobs:\n"
            "  publish:\n"
            f"    environment: {release_environment}\n"
            "    runs-on: ubuntu-24.04\n"
            "    steps: []\n",
            encoding="utf-8",
        )
    (root / ".github/workflow-policy.yaml").write_text(policy, encoding="utf-8")


def _base_provider_responses() -> dict[str, tuple[int, object | None, str]]:
    return {
        "/repos/acme/project": (200, {"default_branch": "main"}, ""),
        "/repos/acme/project/branches/main": (200, {"protected": True}, ""),
    }


def test_provider_http_client_rejects_redirects(monkeypatch) -> None:
    captured_handlers: list[object] = []

    class RedirectingOpener:
        def open(self, request, *, timeout):
            del timeout
            raise urllib.error.HTTPError(
                request.full_url,
                301,
                "Moved Permanently",
                {"Location": "https://api.github.com/repos/acme/successor"},
                None,
            )

    def build_opener(*handlers):
        captured_handlers.extend(handlers)
        return RedirectingOpener()

    monkeypatch.setattr(PROVIDER.urllib.request, "build_opener", build_opener)
    client = PROVIDER.GitHubClient("secret")
    status, document, detail = client.get("/repos/acme/project")

    assert any(isinstance(handler, PROVIDER._RejectRedirects) for handler in captured_handlers)
    assert status == 301
    assert document is None
    assert "redirect is not accepted" in detail
    assert "acme/successor" in detail


def test_provider_rejects_invalid_repository_identity(tmp_path: Path) -> None:
    _repository(tmp_path)
    findings = PROVIDER.check_provider_controls(tmp_path, "not-a-repository", FakeClient({}))
    assert [(item.state, item.message) for item in findings] == [
        ("misconfigured", "repository must use GitHub owner/name syntax")
    ]


def test_provider_preserves_repository_metadata_failure_as_unverifiable(tmp_path: Path) -> None:
    _repository(tmp_path)
    findings = PROVIDER.check_provider_controls(
        tmp_path,
        "acme/project",
        FakeClient({"/repos/acme/project": (500, None, "provider unavailable")}),
    )
    assert any(item.state == "unverifiable" and "repository metadata/default branch" in item.message for item in findings)


def test_provider_requires_observable_default_branch(tmp_path: Path) -> None:
    _repository(tmp_path)
    findings = PROVIDER.check_provider_controls(
        tmp_path,
        "acme/project",
        FakeClient({"/repos/acme/project": (200, {"default_branch": ""}, "")}),
    )
    assert any(item.state == "unverifiable" and "did not expose a default branch" in item.message for item in findings)


def test_provider_accepts_protected_branch_without_release_environment(tmp_path: Path) -> None:
    _repository(tmp_path)
    findings = PROVIDER.check_provider_controls(tmp_path, "acme/project", FakeClient(_base_provider_responses()))
    assert findings == []


def test_provider_checks_authority_selected_required_status_check(tmp_path: Path) -> None:
    _repository(tmp_path)
    base = _base_provider_responses()
    missing = PROVIDER.check_provider_controls(
        tmp_path,
        "acme/project",
        FakeClient(
            {
                **base,
                "/repos/acme/project/branches/main/protection": (
                    200,
                    {"required_status_checks": {"contexts": ["lint"], "checks": []}},
                    "",
                ),
            }
        ),
        required_checks=("acceptance",),
    )
    assert any(item.state == "misconfigured" and "acceptance" in item.message for item in missing)

    passed = PROVIDER.check_provider_controls(
        tmp_path,
        "acme/project",
        FakeClient(
            {
                **base,
                "/repos/acme/project/branches/main/protection": (
                    200,
                    {"required_status_checks": {"contexts": [], "checks": [{"context": "acceptance"}]}},
                    "",
                ),
            }
        ),
        required_checks=("acceptance",),
    )
    assert passed == []


def test_provider_preserves_malformed_environment_listing_as_unverifiable(tmp_path: Path) -> None:
    _repository(tmp_path, release_environment="release")
    findings = PROVIDER.check_provider_controls(
        tmp_path,
        "acme/project",
        FakeClient(
            {
                **_base_provider_responses(),
                "/repos/acme/project/environments?per_page=100": (200, {"environments": "bad"}, ""),
            }
        ),
    )
    assert any(item.state == "unverifiable" and "no environments list" in item.message for item in findings)


def test_provider_rejects_invalid_environment_total_count(tmp_path: Path) -> None:
    _repository(tmp_path, release_environment="release")
    findings = PROVIDER.check_provider_controls(
        tmp_path,
        "acme/project",
        FakeClient(
            {
                **_base_provider_responses(),
                "/repos/acme/project/environments?per_page=100": (
                    200,
                    {"total_count": True, "environments": []},
                    "",
                ),
            }
        ),
    )
    assert any(item.state == "unverifiable" and "invalid total_count" in item.message for item in findings)


def test_provider_finds_release_environment_on_second_page(tmp_path: Path) -> None:
    _repository(tmp_path, release_environment="release")
    first_page = [{"name": f"environment-{index}"} for index in range(100)]
    findings = PROVIDER.check_provider_controls(
        tmp_path,
        "acme/project",
        FakeClient(
            {
                **_base_provider_responses(),
                "/repos/acme/project/environments?per_page=100": (
                    200,
                    {"total_count": 101, "environments": first_page},
                    "",
                ),
                "/repos/acme/project/environments?per_page=100&page=2": (
                    200,
                    {"total_count": 101, "environments": [{"name": "release"}]},
                    "",
                ),
                "/repos/acme/project/environments/release": (
                    200,
                    {"protection_rules": [{"type": "required_reviewers"}], "deployment_branch_policy": None},
                    "",
                ),
            }
        ),
    )
    assert findings == []


def test_provider_marks_incomplete_environment_pagination_unverifiable(tmp_path: Path) -> None:
    _repository(tmp_path, release_environment="release")
    first_page = [{"name": f"environment-{index}"} for index in range(100)]
    findings = PROVIDER.check_provider_controls(
        tmp_path,
        "acme/project",
        FakeClient(
            {
                **_base_provider_responses(),
                "/repos/acme/project/environments?per_page=100": (
                    200,
                    {"total_count": 101, "environments": first_page},
                    "",
                ),
                "/repos/acme/project/environments?per_page=100&page=2": (403, None, "forbidden"),
            }
        ),
    )
    assert any(item.state == "unverifiable" and "environments page 2" in item.message for item in findings)
    assert not any(item.state == "misconfigured" and "does not exist" in item.message for item in findings)


def test_provider_preserves_environment_permission_failure_as_unverifiable(tmp_path: Path) -> None:
    _repository(tmp_path, release_environment="release")
    findings = PROVIDER.check_provider_controls(
        tmp_path,
        "acme/project",
        FakeClient(
            {
                **_base_provider_responses(),
                "/repos/acme/project/environments?per_page=100": (200, {"environments": [{"name": "release"}]}, ""),
                "/repos/acme/project/environments/release": (403, None, "forbidden"),
            }
        ),
    )
    assert any(item.state == "unverifiable" and "release environment 'release'" in item.message for item in findings)


def test_provider_rejects_unprotected_release_environment(tmp_path: Path) -> None:
    _repository(tmp_path, release_environment="release")
    findings = PROVIDER.check_provider_controls(
        tmp_path,
        "acme/project",
        FakeClient(
            {
                **_base_provider_responses(),
                "/repos/acme/project/environments?per_page=100": (200, {"environments": [{"name": "release"}]}, ""),
                "/repos/acme/project/environments/release": (
                    200,
                    {"protection_rules": [], "deployment_branch_policy": None},
                    "",
                ),
            }
        ),
    )
    assert any(item.state == "misconfigured" and "has no protection rule" in item.message for item in findings)


def test_provider_verifies_custom_deployment_branch_policy(tmp_path: Path) -> None:
    _repository(tmp_path, release_environment="release")
    common = {
        **_base_provider_responses(),
        "/repos/acme/project/environments?per_page=100": (200, {"environments": [{"name": "release"}]}, ""),
        "/repos/acme/project/environments/release": (
            200,
            {
                "protection_rules": [],
                "deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True},
            },
            "",
        ),
    }
    invalid = PROVIDER.check_provider_controls(
        tmp_path,
        "acme/project",
        FakeClient(
            {
                **common,
                "/repos/acme/project/environments/release/deployment-branch-policies?per_page=100": (
                    200,
                    {"total_count": "1"},
                    "",
                ),
            }
        ),
    )
    assert any(item.state == "unverifiable" and "integer total_count" in item.message for item in invalid)

    passed = PROVIDER.check_provider_controls(
        tmp_path,
        "acme/project",
        FakeClient(
            {
                **common,
                "/repos/acme/project/environments/release/deployment-branch-policies?per_page=100": (
                    200,
                    {"total_count": 1},
                    "",
                ),
            }
        ),
    )
    assert passed == []


def test_run_classifier_covers_pending_cancelled_and_executed_success() -> None:
    assert CLASSIFIER.classify_run({"status": "waiting"}, {"jobs": []}) == "queued"
    assert CLASSIFIER.classify_run({"status": "completed", "conclusion": "stale"}, {"jobs": []}) == "cancelled"
    assert (
        CLASSIFIER.classify_run(
            {"status": "completed", "conclusion": "success"},
            [{"runner_id": 7, "steps": []}],
        )
        == "executed-pass"
    )


def test_run_classifier_requires_execution_evidence_for_success_and_failure() -> None:
    success_without_execution = {"workflow_jobs": [{"runner_id": 0, "steps": []}]}
    assert (
        CLASSIFIER.classify_run({"status": "completed", "conclusion": "success"}, success_without_execution)
        == "missing-evidence"
    )
    assert (
        CLASSIFIER.classify_run(
            {"status": "completed", "conclusion": "startup_failure"},
            {"jobs": [{"runner_id": 0, "steps": []}]},
        )
        == "provider-no-runner"
    )
    assert (
        CLASSIFIER.classify_run(
            {"status": "completed", "conclusion": "timed_out"},
            {"jobs": [{"runner_id": 0, "steps": [{"name": "start"}]}]},
        )
        == "executed-fail"
    )
    assert CLASSIFIER.classify_run({"status": "completed", "conclusion": "failure"}, {}) == "missing-evidence"

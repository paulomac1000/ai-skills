"""Provider-backed diagnostic evidence is fail-closed and byte-bound."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Mapping
from typing import Any

from contracts.evidence import GitHubEvidenceVerifier

SHA = "a" * 40
REPORT_PATH = "evidence/report.json"
RESULT_PATH = "results.xml"
ARGV = ["python", "-m", "pytest"]
COMMAND_DIGEST = (
    "sha256:"
    + hashlib.sha256(
        json.dumps(
            {"argv": ARGV, "working_directory": "."},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
)
IDENTITY = "tests.test_policy::test_auth_before_io"
JUNIT = (
    b'<testsuite tests="1" failures="0" errors="0" skipped="0">'
    b'<testcase classname="tests.test_policy" name="test_auth_before_io" />'
    b"</testsuite>"
)
RESULT_DIGEST = "sha256:" + hashlib.sha256(JUNIT).hexdigest()
CLAIM = {
    "kind": "rule",
    "subject": "server.auth.before-io",
    "result": "passed",
    "execution_id": "tests",
    "command_digest": COMMAND_DIGEST,
}


def binding(path: str = RESULT_PATH, digest: str = RESULT_DIGEST, identity: str = IDENTITY) -> dict[str, Any]:
    return {
        "result_path": path,
        "result_digest": digest,
        "test_cases": [{"identity": identity, "status": "passed"}],
    }


def make_report(**overrides: Any) -> bytes:
    payload: dict[str, Any] = {
        "format": "ai-skills-evidence-report",
        "evidence_role": "diagnostic",
        "repository": "owner/repository",
        "revision": SHA,
        "source_head_sha": SHA,
        "tested_checkout_sha": SHA,
        "merge_sha": None,
        "provider_run_head_sha": SHA,
        "run_id": 100,
        "job_id": 200,
        "check_run_id": 2200,
        "workflow_id": 300,
        "workflow_path": ".github/workflows/ci.yml",
        "workflow_name": "CI",
        "event": "pull_request",
        "job_name": "python-quality",
        "lane": "repository-gate",
        "producer": {"provider": "github", "login": "producer", "id": 700},
        "executions": [
            {
                "execution_id": "tests",
                "argv": ARGV,
                "working_directory": ".",
                "command_digest": COMMAND_DIGEST,
                "exit_status": 0,
                "result_digests": [RESULT_DIGEST],
            }
        ],
        "results": [
            {
                "path": RESULT_PATH,
                "format": "junit",
                "digest": RESULT_DIGEST,
                "summary": {"tests": 1, "passed": 1, "skipped": 0, "failures": 0, "errors": 0},
            }
        ],
        "claims": [{**CLAIM, "result_bindings": [binding()], "exit_status": 0}],
    }
    payload.update(overrides)
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def make_zip(
    report: bytes | None,
    *,
    results: Mapping[str, bytes] | None = None,
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        if report is not None:
            archive.writestr(REPORT_PATH, report)
        for path, payload in (results or {RESULT_PATH: JUNIT}).items():
            archive.writestr(path, payload)
    return output.getvalue()


class StubVerifier(GitHubEvidenceVerifier):
    """Return fixed provider objects and archive bytes."""

    def __init__(self, responses: Mapping[str, object], archive: bytes) -> None:
        super().__init__("test-token")
        self.responses = dict(responses)
        self.archive = archive

    def _get_json(self, path: str) -> object:
        return self.responses[path]

    def _download_artifact_bytes(self, repository: str, artifact_id: int) -> bytes:
        return self.archive


def fixture(
    report: bytes | None = None, results: Mapping[str, bytes] | None = None
) -> tuple[dict[str, Any], dict[str, object], bytes]:
    report = report or make_report()
    archive = make_zip(report, results=results)
    provider_digest = "sha256:" + hashlib.sha256(archive).hexdigest()
    reference = {
        "provider": "github-actions",
        "repository": "owner/repository",
        "run_id": 100,
        "job_id": 200,
        "check_run_id": 2200,
        "revision": SHA,
        "workflow_id": 300,
        "workflow_path": ".github/workflows/ci.yml",
        "workflow_name": "CI",
        "event": "pull_request",
        "job_name": "python-quality",
        "lane": "repository-gate",
        "artifact_id": 400,
        "artifact_name": "evidence-python-quality",
        "provider_digest": provider_digest,
        "report_path": REPORT_PATH,
        "report_digest": "sha256:" + hashlib.sha256(report).hexdigest(),
        "_expected_claim": CLAIM,
    }
    responses: dict[str, object] = {
        "/repos/owner/repository/actions/runs/100": {
            "head_sha": SHA,
            "status": "completed",
            "conclusion": "success",
            "workflow_id": 300,
            "path": ".github/workflows/ci.yml",
            "name": "CI",
            "event": "pull_request",
            "actor": {"id": 700, "login": "producer"},
        },
        "/repos/owner/repository/actions/jobs/200": {
            "run_id": 100,
            "status": "completed",
            "conclusion": "success",
            "name": "python-quality",
            "check_run_url": "https://api.github.com/repos/owner/repository/check-runs/2200",
        },
        "/repos/owner/repository/actions/artifacts/400": {
            "name": "evidence-python-quality",
            "expired": False,
            "digest": provider_digest,
            "workflow_run": {"id": 100, "head_sha": SHA},
        },
        "/repos/owner/repository/pulls/12/reviews/500": {
            "state": "APPROVED",
            "commit_id": SHA,
            "user": {"id": 600, "login": "reviewer"},
        },
        "/repos/owner/repository/pulls/12": {
            "head": {"sha": SHA},
            "user": {"id": 800, "login": "author"},
            "commits": 1,
        },
        "/repos/owner/repository/pulls/12/commits?per_page=100&page=1": [
            {
                "author": {"id": 800, "login": "author"},
                "committer": {"id": 801, "login": "committer"},
            }
        ],
    }
    return reference, responses, archive


def with_report(
    report: bytes, results: Mapping[str, bytes] | None = None
) -> tuple[dict[str, Any], dict[str, object], bytes]:
    reference, responses, archive = fixture(report, results)
    return reference, responses, archive


def test_exact_report_execution_result_and_claim_pass() -> None:
    reference, responses, archive = fixture()
    assert StubVerifier(responses, archive).verify_action(reference, SHA) == []


def test_unrelated_passing_result_cannot_support_claim() -> None:
    unrelated_path = "unrelated.xml"
    unrelated = (
        b'<testsuite tests="1" failures="0" errors="0" skipped="0">'
        b'<testcase classname="tests.test_other" name="test_other" />'
        b"</testsuite>"
    )
    unrelated_digest = "sha256:" + hashlib.sha256(unrelated).hexdigest()
    document = json.loads(make_report())
    document["results"].append(
        {
            "path": unrelated_path,
            "format": "junit",
            "digest": unrelated_digest,
            "summary": {"tests": 1, "passed": 1, "skipped": 0, "failures": 0, "errors": 0},
        }
    )
    document["claims"][0]["result_bindings"] = [
        binding(unrelated_path, unrelated_digest, "tests.test_other::test_other")
    ]
    report = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
    reference, responses, archive = with_report(report, {RESULT_PATH: JUNIT, unrelated_path: unrelated})
    errors = StubVerifier(responses, archive).verify_action(reference, SHA)
    assert any("not bound to its execution result bytes" in error for error in errors)


def test_false_command_digest_with_real_junit_is_rejected() -> None:
    document = json.loads(make_report())
    document["claims"][0]["command_digest"] = "sha256:" + "b" * 64
    report = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
    reference, responses, archive = with_report(report)
    errors = StubVerifier(responses, archive).verify_action(reference, SHA)
    assert any("command does not match its execution" in error for error in errors)


def _duplicate_junit(first: str, second: str) -> bytes:
    def outcome(status: str) -> bytes:
        return b"<failure />" if status == "failure" else b""

    return (
        b'<testsuite tests="2" failures="1" errors="0" skipped="0">'
        b'<testcase classname="tests.test_policy" name="test_auth_before_io">' + outcome(first) + b"</testcase>"
        b'<testcase classname="tests.test_policy" name="test_auth_before_io">'
        + outcome(second)
        + b"</testcase></testsuite>"
    )


def test_duplicate_failure_then_passed_is_rejected() -> None:
    duplicate = _duplicate_junit("failure", "passed")
    digest = "sha256:" + hashlib.sha256(duplicate).hexdigest()
    document = json.loads(make_report())
    document["results"][0]["digest"] = digest
    document["executions"][0]["result_digests"] = [digest]
    document["claims"][0]["result_bindings"] = [binding(digest=digest)]
    report = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
    reference, responses, archive = with_report(report, {RESULT_PATH: duplicate})
    errors = StubVerifier(responses, archive).verify_action(reference, SHA)
    assert any("duplicate testcase identity" in error for error in errors)


def test_duplicate_passed_then_failure_is_rejected() -> None:
    duplicate = _duplicate_junit("passed", "failure")
    digest = "sha256:" + hashlib.sha256(duplicate).hexdigest()
    document = json.loads(make_report())
    document["results"][0]["digest"] = digest
    document["executions"][0]["result_digests"] = [digest]
    document["claims"][0]["result_bindings"] = [binding(digest=digest)]
    report = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
    reference, responses, archive = with_report(report, {RESULT_PATH: duplicate})
    errors = StubVerifier(responses, archive).verify_action(reference, SHA)
    assert any("duplicate testcase identity" in error for error in errors)


def test_digest_mismatch_is_rejected_before_junit_interpretation() -> None:
    failed = JUNIT.replace(b" />", b"><failure /></testcase>")
    reference, responses, archive = fixture(results={RESULT_PATH: failed})
    errors = StubVerifier(responses, archive).verify_action(reference, SHA)
    assert any("digest does not match" in error for error in errors)


def test_failed_junit_with_matching_digest_is_rejected() -> None:
    failed = (
        b'<testsuite tests="1" failures="1" errors="0" skipped="0">'
        b'<testcase classname="tests.test_policy" name="test_auth_before_io"><failure /></testcase>'
        b"</testsuite>"
    )
    digest = "sha256:" + hashlib.sha256(failed).hexdigest()
    document = json.loads(make_report())
    document["results"][0]["digest"] = digest
    document["executions"][0]["result_digests"] = [digest]
    document["claims"][0]["result_bindings"] = [binding(digest=digest)]
    report = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
    reference, responses, archive = with_report(report, {RESULT_PATH: failed})
    errors = StubVerifier(responses, archive).verify_action(reference, SHA)
    assert any("failures or errors" in error for error in errors)


def _review_reference() -> dict[str, Any]:
    return {
        "provider": "github",
        "repository": "owner/repository",
        "pull_request": 12,
        "review_id": 500,
        "login": "reviewer",
        "id": 600,
        "revision": SHA,
        "state": "APPROVED",
    }


def test_unlinked_commit_author_fails_closed() -> None:
    _, responses, archive = fixture()
    commits = list(responses["/repos/owner/repository/pulls/12/commits?per_page=100&page=1"])  # type: ignore[arg-type]
    commits[0] = {"author": None, "committer": {"id": 801, "login": "committer"}}
    responses["/repos/owner/repository/pulls/12/commits?per_page=100&page=1"] = commits
    errors = StubVerifier(responses, archive).verify_review(_review_reference(), SHA)
    assert any("commit author has no canonical identity" in error for error in errors)


def test_unlinked_commit_committer_fails_closed() -> None:
    _, responses, archive = fixture()
    commits = list(responses["/repos/owner/repository/pulls/12/commits?per_page=100&page=1"])  # type: ignore[arg-type]
    commits[0] = {"author": {"id": 800, "login": "author"}, "committer": None}
    responses["/repos/owner/repository/pulls/12/commits?per_page=100&page=1"] = commits
    errors = StubVerifier(responses, archive).verify_review(_review_reference(), SHA)
    assert any("commit committer has no canonical identity" in error for error in errors)


def test_independent_review_is_bound_to_exact_revision() -> None:
    _, responses, archive = fixture()
    assert StubVerifier(responses, archive).verify_review(_review_reference(), SHA) == []
    changed = dict(responses)
    changed["/repos/owner/repository/pulls/12/reviews/500"] = {
        "state": "APPROVED",
        "commit_id": "b" * 40,
        "user": {"id": 600, "login": "reviewer"},
    }
    errors = StubVerifier(changed, archive).verify_review(_review_reference(), SHA)
    assert "review approval is not bound to the assessed revision" in errors


successful_fixture = fixture

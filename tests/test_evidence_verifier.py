"""Provider-backed evidence verification contract without live network access."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Mapping
from typing import Any

import pytest

from contracts.evidence import GitHubEvidenceVerifier

SHA = "a" * 40
REPORT_PATH = "evidence/report.json"
RESULT_PATH = "results.xml"
COMMAND_DIGEST = "sha256:" + hashlib.sha256(b"python -m pytest").hexdigest()
CLAIM = {
    "kind": "rule",
    "subject": "server.auth.before-io",
    "result": "passed",
    "command_digest": COMMAND_DIGEST,
}
JUNIT = (
    b'<testsuite tests="1" failures="0" errors="0" skipped="0">'
    b'<testcase classname="tests.test_policy" name="test_auth_before_io" />'
    b"</testsuite>"
)
RESULT_DIGEST = "sha256:" + hashlib.sha256(JUNIT).hexdigest()


def make_report(**overrides: Any) -> bytes:
    payload = {
        "schema_version": 2,
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
        "results": [
            {
                "path": RESULT_PATH,
                "format": "junit",
                "digest": RESULT_DIGEST,
                "summary": {
                    "tests": 1,
                    "passed": 1,
                    "skipped": 0,
                    "failures": 0,
                    "errors": 0,
                },
            }
        ],
        "claims": [
            {
                **CLAIM,
                "result_digests": [RESULT_DIGEST],
                "test_cases": ["tests.test_policy::test_auth_before_io"],
                "exit_status": 0,
            }
        ],
    }
    payload.update(overrides)
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def make_zip(
    report: bytes | None = None,
    *,
    result: bytes = JUNIT,
    unsafe_name: str | None = None,
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        if unsafe_name is not None:
            archive.writestr(unsafe_name, b"x")
        if report is not None:
            archive.writestr(REPORT_PATH, report)
            archive.writestr(RESULT_PATH, result)
    return output.getvalue()


class StubVerifier(GitHubEvidenceVerifier):
    """Return fixed provider objects and archive bytes."""

    def __init__(self, responses: Mapping[str, object], archive: bytes) -> None:
        super().__init__("test-token")
        self.responses = dict(responses)
        self.archive = archive
        self.requested: list[str] = []

    def _get_json(self, path: str) -> object:
        self.requested.append(path)
        return self.responses[path]

    def _download_artifact_bytes(self, repository: str, artifact_id: int) -> bytes:
        return self.archive


def successful_fixture() -> tuple[dict[str, Any], dict[str, object], bytes]:
    report = make_report()
    archive = make_zip(report)
    provider_digest = "sha256:" + hashlib.sha256(archive).hexdigest()
    report_digest = "sha256:" + hashlib.sha256(report).hexdigest()
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
        "report_digest": report_digest,
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


def test_action_requires_exact_workflow_job_machine_result_and_claim() -> None:
    reference, responses, archive = successful_fixture()
    assert StubVerifier(responses, archive).verify_action(reference, SHA) == []

    wrong_report = make_report(tested_checkout_sha="b" * 40)
    wrong_archive = make_zip(wrong_report)
    digest = "sha256:" + hashlib.sha256(wrong_archive).hexdigest()
    altered = dict(
        reference, provider_digest=digest, report_digest="sha256:" + hashlib.sha256(wrong_report).hexdigest()
    )
    provider = dict(responses)
    provider["/repos/owner/repository/actions/artifacts/400"] = {
        **provider["/repos/owner/repository/actions/artifacts/400"],  # type: ignore[arg-type]
        "digest": digest,
    }
    errors = StubVerifier(provider, wrong_archive).verify_action(altered, SHA)
    assert "evidence report tested_checkout_sha does not match the referenced execution" in errors


def test_green_self_described_claim_without_matching_junit_is_rejected() -> None:
    reference, responses, _ = successful_fixture()
    wrong_report = make_report(
        claims=[
            {
                **CLAIM,
                "result_digests": [RESULT_DIGEST],
                "test_cases": ["tests.test_policy::not_executed"],
                "exit_status": 0,
            }
        ]
    )
    archive = make_zip(wrong_report)
    provider_digest = "sha256:" + hashlib.sha256(archive).hexdigest()
    reference = dict(
        reference,
        provider_digest=provider_digest,
        report_digest="sha256:" + hashlib.sha256(wrong_report).hexdigest(),
    )
    responses = dict(responses)
    responses["/repos/owner/repository/actions/artifacts/400"] = {
        **responses["/repos/owner/repository/actions/artifacts/400"],  # type: ignore[arg-type]
        "digest": provider_digest,
    }
    errors = StubVerifier(responses, archive).verify_action(reference, SHA)
    assert any("not bound to passed test cases" in error for error in errors)


def test_claim_test_cases_must_come_from_the_claimed_result_digest() -> None:
    reference, responses, _ = successful_fixture()
    second_path = "second-results.xml"
    second_junit = (
        b'<testsuite tests="1" failures="0" errors="0" skipped="0">'
        b'<testcase classname="tests.test_other" name="test_other" />'
        b"</testsuite>"
    )
    second_digest = "sha256:" + hashlib.sha256(second_junit).hexdigest()
    document = json.loads(make_report())
    document["results"].append(
        {
            "path": second_path,
            "format": "junit",
            "digest": second_digest,
            "summary": {"tests": 1, "passed": 1, "skipped": 0, "failures": 0, "errors": 0},
        }
    )
    document["claims"][0]["result_digests"] = [RESULT_DIGEST]
    document["claims"][0]["test_cases"] = ["tests.test_other::test_other"]
    report = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(REPORT_PATH, report)
        archive.writestr(RESULT_PATH, JUNIT)
        archive.writestr(second_path, second_junit)
    archive_bytes = output.getvalue()
    provider_digest = "sha256:" + hashlib.sha256(archive_bytes).hexdigest()
    reference = dict(
        reference,
        provider_digest=provider_digest,
        report_digest="sha256:" + hashlib.sha256(report).hexdigest(),
    )
    responses = dict(responses)
    responses["/repos/owner/repository/actions/artifacts/400"] = {
        **responses["/repos/owner/repository/actions/artifacts/400"],  # type: ignore[arg-type]
        "digest": provider_digest,
    }
    errors = StubVerifier(responses, archive_bytes).verify_action(reference, SHA)
    assert any("not bound to passed test cases in its result bytes" in error for error in errors)


def test_non_null_unverified_merge_sha_is_rejected() -> None:
    reference, responses, _ = successful_fixture()
    report = make_report(merge_sha="b" * 40)
    archive = make_zip(report)
    provider_digest = "sha256:" + hashlib.sha256(archive).hexdigest()
    reference = dict(
        reference,
        provider_digest=provider_digest,
        report_digest="sha256:" + hashlib.sha256(report).hexdigest(),
    )
    responses = dict(responses)
    responses["/repos/owner/repository/actions/artifacts/400"] = {
        **responses["/repos/owner/repository/actions/artifacts/400"],  # type: ignore[arg-type]
        "digest": provider_digest,
    }
    errors = StubVerifier(responses, archive).verify_action(reference, SHA)
    assert "evidence report merge_sha does not match the referenced execution" in errors


def test_result_digest_and_failed_junit_are_rejected() -> None:
    reference, responses, _ = successful_fixture()
    failed = (
        b'<testsuite tests="1" failures="1" errors="0" skipped="0">'
        b'<testcase classname="tests.test_policy" name="test_auth_before_io"><failure /></testcase>'
        b"</testsuite>"
    )
    archive = make_zip(make_report(), result=failed)
    provider_digest = "sha256:" + hashlib.sha256(archive).hexdigest()
    reference = dict(reference, provider_digest=provider_digest)
    responses = dict(responses)
    responses["/repos/owner/repository/actions/artifacts/400"] = {
        **responses["/repos/owner/repository/actions/artifacts/400"],  # type: ignore[arg-type]
        "digest": provider_digest,
    }
    errors = StubVerifier(responses, archive).verify_action(reference, SHA)
    assert any("digest does not match" in error for error in errors)


def test_review_independence_is_derived_from_pr_commits_and_evidence_actor() -> None:
    reference, responses, archive = successful_fixture()
    verifier = StubVerifier(responses, archive)
    action_reference = dict(reference)
    assert verifier.verify_action(action_reference, SHA) == []

    review_reference = {
        "provider": "github",
        "repository": "owner/repository",
        "pull_request": 12,
        "review_id": 500,
        "login": "reviewer",
        "id": 600,
        "revision": SHA,
        "state": "APPROVED",
    }
    assert verifier.verify_review(review_reference, SHA) == []

    for identity in (
        {"id": 800, "login": "author"},
        {"id": 801, "login": "committer"},
        {"id": 700, "login": "producer"},
    ):
        changed = dict(responses)
        changed["/repos/owner/repository/pulls/12/reviews/500"] = {
            "state": "APPROVED",
            "commit_id": SHA,
            "user": identity,
        }
        candidate = StubVerifier(changed, archive)
        assert candidate.verify_action(action_reference, SHA) == []
        ref = dict(review_reference, id=identity["id"], login=identity["login"])
        errors = candidate.verify_review(ref, SHA)
        assert "reviewer is not independent from PR, commit, or evidence provenance" in errors


def test_review_fails_closed_when_provider_cannot_enumerate_every_pr_commit() -> None:
    reference, responses, archive = successful_fixture()
    responses = dict(responses)
    responses["/repos/owner/repository/pulls/12"] = {
        "head": {"sha": SHA},
        "user": {"id": 800, "login": "author"},
        "commits": 251,
    }
    review_reference = {
        "provider": "github",
        "repository": "owner/repository",
        "pull_request": 12,
        "review_id": 500,
        "login": "reviewer",
        "id": 600,
        "revision": SHA,
        "state": "APPROVED",
    }
    errors = StubVerifier(responses, archive).verify_review(review_reference, SHA)
    assert any("more than 250 commits" in error for error in errors)


def test_artifact_path_and_github_com_scope_fail_closed() -> None:
    reference, responses, _ = successful_fixture()
    archive = make_zip(make_report(), unsafe_name="../escape")
    provider_digest = "sha256:" + hashlib.sha256(archive).hexdigest()
    reference = dict(reference, provider_digest=provider_digest)
    responses = dict(responses)
    responses["/repos/owner/repository/actions/artifacts/400"] = {
        **responses["/repos/owner/repository/actions/artifacts/400"],  # type: ignore[arg-type]
        "digest": provider_digest,
    }
    errors = StubVerifier(responses, archive).verify_action(reference, SHA)
    assert any("unsafe path" in error for error in errors)
    with pytest.raises(ValueError, match="GitHub.com"):
        GitHubEvidenceVerifier("token", api_base="https://github.example.com/api/v3")

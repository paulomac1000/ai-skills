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
CLAIM = {
    "kind": "rule",
    "subject": "server.auth.before-io",
    "result": "passed",
    "command_digest": "sha256:" + "d" * 64,
}
REPORT_PATH = "evidence/report.json"


def make_report(**overrides: Any) -> bytes:
    payload = {
        "schema_version": 1,
        "repository": "owner/repository",
        "revision": SHA,
        "run_id": 100,
        "job_id": 200,
        "check_run_id": 2200,
        "workflow_id": 300,
        "workflow_path": ".github/workflows/ci.yml",
        "workflow_name": "CI",
        "event": "pull_request",
        "job_name": "python-quality",
        "lane": "repository-gate",
        "claims": [CLAIM],
    }
    payload.update(overrides)
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def make_zip(report: bytes | None = None, *, unsafe_name: str | None = None) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        if unsafe_name is not None:
            archive.writestr(unsafe_name, b"x")
        if report is not None:
            archive.writestr(REPORT_PATH, report)
    return output.getvalue()


class StubVerifier(GitHubEvidenceVerifier):
    """Return fixed provider objects and archive bytes."""

    def __init__(self, responses: Mapping[str, Mapping[str, Any]], archive: bytes) -> None:
        super().__init__("test-token")
        self.responses = dict(responses)
        self.archive = archive
        self.requested: list[str] = []

    def _get(self, path: str) -> Mapping[str, Any]:
        self.requested.append(path)
        return self.responses[path]

    def _download_artifact_bytes(self, repository: str, artifact_id: int) -> bytes:
        return self.archive


def successful_fixture() -> tuple[dict[str, Any], dict[str, Mapping[str, Any]], bytes]:
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
    responses: dict[str, Mapping[str, Any]] = {
        "/repos/owner/repository/actions/runs/100": {
            "head_sha": SHA,
            "status": "completed",
            "conclusion": "success",
            "workflow_id": 300,
            "path": ".github/workflows/ci.yml",
            "name": "CI",
            "event": "pull_request",
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
    }
    return reference, responses, archive


def test_action_requires_exact_workflow_job_and_claim_report() -> None:
    reference, responses, archive = successful_fixture()
    assert StubVerifier(responses, archive).verify_action(reference, SHA) == []

    responses = dict(responses)
    responses["/repos/owner/repository/actions/jobs/200"] = {
        **responses["/repos/owner/repository/actions/jobs/200"],
        "name": "docs-only",
    }
    errors = StubVerifier(responses, archive).verify_action(reference, SHA)
    assert "workflow job name does not match evidence.job_name" in errors


def test_green_wrong_claim_is_rejected() -> None:
    reference, responses, _ = successful_fixture()
    wrong_report = make_report(
        claims=[
            {
                "kind": "rule",
                "subject": "another.rule",
                "result": "passed",
                "command_digest": "sha256:" + "d" * 64,
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
        **responses["/repos/owner/repository/actions/artifacts/400"],
        "digest": provider_digest,
    }
    errors = StubVerifier(responses, archive).verify_action(reference, SHA)
    assert "evidence report does not contain the exact assessed claim" in errors


def test_artifact_is_bound_to_exact_run_name_and_bytes() -> None:
    reference, responses, archive = successful_fixture()
    bad = dict(responses)
    bad["/repos/owner/repository/actions/artifacts/400"] = {
        **bad["/repos/owner/repository/actions/artifacts/400"],
        "name": "other",
        "workflow_run": {"id": 999, "head_sha": SHA},
    }
    errors = StubVerifier(bad, archive).verify_artifact(reference, SHA, reference["provider_digest"])
    assert "artifact name does not match evidence.artifact_name" in errors
    assert "artifact is not part of the referenced run" in errors


def test_unsafe_archive_paths_are_rejected() -> None:
    reference, responses, _ = successful_fixture()
    archive = make_zip(make_report(), unsafe_name="../escape")
    provider_digest = "sha256:" + hashlib.sha256(archive).hexdigest()
    reference = dict(reference, provider_digest=provider_digest)
    responses = dict(responses)
    responses["/repos/owner/repository/actions/artifacts/400"] = {
        **responses["/repos/owner/repository/actions/artifacts/400"],
        "digest": provider_digest,
    }
    errors = StubVerifier(responses, archive).verify_action(reference, SHA)
    assert any("unsafe path" in error for error in errors)


def test_review_malformed_provider_id_fails_closed_without_exception() -> None:
    reference = {
        "provider": "github",
        "repository": "owner/repository",
        "pull_request": 12,
        "review_id": 500,
        "login": "reviewer",
        "id": 600,
        "revision": SHA,
        "state": "APPROVED",
    }
    _, responses, archive = successful_fixture()
    responses = dict(responses)
    responses["/repos/owner/repository/pulls/12/reviews/500"] = {
        **responses["/repos/owner/repository/pulls/12/reviews/500"],
        "user": {"id": "invalid", "login": "reviewer"},
    }
    assert StubVerifier(responses, archive).verify_review(reference, SHA) == [
        "review author has an invalid numeric identity"
    ]


def test_verifier_rejects_untrusted_api_origin_and_invalid_repository() -> None:
    with pytest.raises(ValueError, match="canonical GitHub API"):
        GitHubEvidenceVerifier("token", api_base="https://example.invalid")
    reference, responses, archive = successful_fixture()
    reference = dict(reference, repository="invalid")
    assert StubVerifier(responses, archive).verify_action(reference, SHA) == [
        "GitHub evidence verification failed: evidence repository must use owner/name"
    ]

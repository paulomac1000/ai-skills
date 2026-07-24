"""Provider-backed evidence verification contract without live network access."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from contracts.evidence import GitHubEvidenceVerifier

SHA = "a" * 40
DIGEST = "sha256:" + "b" * 64
PROVIDER_DIGEST = "sha256:" + "c" * 64


class StubVerifier(GitHubEvidenceVerifier):
    """Return fixed GitHub API objects for deterministic contract tests."""

    def __init__(self, responses: Mapping[str, Mapping[str, Any]]) -> None:
        super().__init__("test-token")
        self.responses = dict(responses)
        self.requested: list[str] = []

    def _get(self, path: str) -> Mapping[str, Any]:
        self.requested.append(path)
        return self.responses[path]


def action_reference() -> dict[str, Any]:
    return {
        "provider": "github-actions",
        "repository": "owner/repository",
        "run_id": 100,
        "job_id": 200,
        "revision": SHA,
    }


def successful_responses() -> dict[str, Mapping[str, Any]]:
    return {
        "/repos/owner/repository/actions/runs/100": {
            "head_sha": SHA,
            "status": "completed",
            "conclusion": "success",
        },
        "/repos/owner/repository/actions/jobs/200": {
            "run_id": 100,
            "status": "completed",
            "conclusion": "success",
        },
        "/repos/owner/repository/actions/artifacts/300": {
            "expired": False,
            "digest": PROVIDER_DIGEST,
            "workflow_run": {"head_sha": SHA},
        },
        "/repos/owner/repository/pulls/12/reviews/400": {
            "state": "APPROVED",
            "commit_id": SHA,
            "user": {"id": 500, "login": "reviewer"},
        },
    }


def test_action_evidence_requires_exact_successful_run_and_job() -> None:
    verifier = StubVerifier(successful_responses())
    assert verifier.verify_action(action_reference(), SHA) == []

    responses = successful_responses()
    responses["/repos/owner/repository/actions/runs/100"] = {
        "head_sha": "c" * 40,
        "status": "completed",
        "conclusion": "failure",
    }
    responses["/repos/owner/repository/actions/jobs/200"] = {
        "run_id": 999,
        "status": "completed",
        "conclusion": "failure",
    }
    errors = StubVerifier(responses).verify_action(action_reference(), SHA)
    assert errors == [
        "workflow run head_sha does not match the assessed revision",
        "workflow run is not completed successfully",
        "workflow job is not part of the referenced run",
        "workflow job is not completed successfully",
    ]


def test_artifact_evidence_binds_provider_digest_and_revision() -> None:
    reference = action_reference() | {"artifact_id": 300, "provider_digest": PROVIDER_DIGEST}
    verifier = StubVerifier(successful_responses())
    assert verifier.verify_artifact(reference, SHA, PROVIDER_DIGEST) == []

    responses = successful_responses()
    responses["/repos/owner/repository/actions/artifacts/300"] = {
        "expired": True,
        "digest": "sha256:" + "d" * 64,
        "workflow_run": {"head_sha": "e" * 40},
    }
    errors = StubVerifier(responses).verify_artifact(reference, SHA, PROVIDER_DIGEST)
    assert errors == [
        "artifact workflow revision does not match the assessed revision",
        "artifact is expired",
        "artifact provider digest does not match evidence.provider_digest",
    ]


def test_review_evidence_uses_canonical_identity_and_exact_revision() -> None:
    reference = {
        "provider": "github",
        "repository": "owner/repository",
        "pull_request": 12,
        "review_id": 400,
        "login": "Reviewer",
        "id": 500,
        "revision": SHA,
        "state": "APPROVED",
    }
    assert StubVerifier(successful_responses()).verify_review(reference, SHA) == []

    responses = successful_responses()
    responses["/repos/owner/repository/pulls/12/reviews/400"] = {
        "state": "CHANGES_REQUESTED",
        "commit_id": "f" * 40,
        "user": {"id": 501, "login": "someone-else"},
    }
    errors = StubVerifier(responses).verify_review(reference, SHA)
    assert errors == [
        "reviewer numeric identity does not match the review author",
        "reviewer login does not match the review author",
        "review state is not APPROVED",
        "review approval is not bound to the assessed revision",
    ]


def test_verifier_rejects_untrusted_api_origin_and_invalid_repository() -> None:
    with pytest.raises(ValueError, match="canonical GitHub API"):
        GitHubEvidenceVerifier("token", api_base="https://example.invalid")
    verifier = StubVerifier({})
    errors = verifier.verify_action(action_reference() | {"repository": "not-a-repository"}, SHA)
    assert errors == ["GitHub evidence verification failed: evidence repository must use owner/name"]

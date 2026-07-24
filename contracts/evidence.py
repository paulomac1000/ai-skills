"""Provider-backed evidence verification for adoption assessments.

The semantic validator owns policy. This module only proves that immutable
GitHub Actions and pull-request review records exist and match the assessment
revision. Network verification is opt-in for structural checks and mandatory for
an approving acceptance gate.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class EvidenceVerifier(Protocol):
    """Verify provider records referenced by one assessment."""

    def verify_action(self, reference: Mapping[str, Any], expected_revision: str) -> Sequence[str]:
        """Return violations for one GitHub Actions run/job reference."""

    def verify_artifact(
        self,
        reference: Mapping[str, Any],
        expected_revision: str,
        expected_provider_digest: str,
    ) -> Sequence[str]:
        """Return violations for one immutable workflow artifact."""

    def verify_review(self, reference: Mapping[str, Any], expected_revision: str) -> Sequence[str]:
        """Return violations for one pull-request review approval."""


class GitHubEvidenceVerifier:
    """Verify GitHub Actions and review evidence through GitHub's REST API."""

    def __init__(self, token: str, *, api_base: str = "https://api.github.com", timeout_seconds: int = 20) -> None:
        if not token.strip():
            raise ValueError("GitHub evidence verification requires a non-empty token")
        if api_base != "https://api.github.com":
            raise ValueError("only the canonical GitHub API endpoint is supported")
        self._token = token.strip()
        self._api_base = api_base
        self._timeout_seconds = timeout_seconds
        self._cache: dict[str, Mapping[str, Any]] = {}

    def _get(self, path: str) -> Mapping[str, Any]:
        cached = self._cache.get(path)
        if cached is not None:
            return cached
        request = Request(  # noqa: S310 - fixed HTTPS GitHub API origin.
            f"{self._api_base}{path}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "ai-skills-adoption-verifier",
            },
        )
        with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310 - fixed origin above.
            payload = json.load(response)
        if not isinstance(payload, Mapping):
            raise ValueError(f"GitHub API returned a non-object for {path}")
        self._cache[path] = payload
        return payload

    @staticmethod
    def _repository_path(reference: Mapping[str, Any]) -> str:
        repository = str(reference.get("repository") or "")
        owner, separator, name = repository.partition("/")
        if not separator or not owner or not name or "/" in name:
            raise ValueError("evidence repository must use owner/name")
        return f"{quote(owner, safe='')}/{quote(name, safe='')}"

    @staticmethod
    def _api_error(exc: Exception) -> str:
        if isinstance(exc, HTTPError):
            return f"GitHub API returned HTTP {exc.code}"
        if isinstance(exc, URLError):
            return f"GitHub API request failed: {exc.reason}"
        return f"GitHub evidence verification failed: {exc}"

    def verify_action(self, reference: Mapping[str, Any], expected_revision: str) -> Sequence[str]:
        errors: list[str] = []
        try:
            repository = self._repository_path(reference)
            run_id = int(reference["run_id"])
            job_id = int(reference["job_id"])
            run = self._get(f"/repos/{repository}/actions/runs/{run_id}")
            job = self._get(f"/repos/{repository}/actions/jobs/{job_id}")
        except (KeyError, TypeError, ValueError, HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            return [self._api_error(exc)]

        if str(run.get("head_sha") or "") != expected_revision:
            errors.append("workflow run head_sha does not match the assessed revision")
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            errors.append("workflow run is not completed successfully")
        if job.get("run_id") != run_id:
            errors.append("workflow job is not part of the referenced run")
        if job.get("status") != "completed" or job.get("conclusion") != "success":
            errors.append("workflow job is not completed successfully")
        return errors

    def verify_artifact(
        self,
        reference: Mapping[str, Any],
        expected_revision: str,
        expected_provider_digest: str,
    ) -> Sequence[str]:
        errors = list(self.verify_action(reference, expected_revision))
        try:
            repository = self._repository_path(reference)
            artifact_id = int(reference["artifact_id"])
            artifact = self._get(f"/repos/{repository}/actions/artifacts/{artifact_id}")
        except (KeyError, TypeError, ValueError, HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            errors.append(self._api_error(exc))
            return errors

        workflow_run = artifact.get("workflow_run")
        if not isinstance(workflow_run, Mapping) or str(workflow_run.get("head_sha") or "") != expected_revision:
            errors.append("artifact workflow revision does not match the assessed revision")
        if artifact.get("expired") is True:
            errors.append("artifact is expired")
        if str(artifact.get("digest") or "") != expected_provider_digest:
            errors.append("artifact provider digest does not match evidence.provider_digest")
        return errors

    def verify_review(self, reference: Mapping[str, Any], expected_revision: str) -> Sequence[str]:
        errors: list[str] = []
        try:
            repository = self._repository_path(reference)
            pull_request = int(reference["pull_request"])
            review_id = int(reference["review_id"])
            review = self._get(f"/repos/{repository}/pulls/{pull_request}/reviews/{review_id}")
        except (KeyError, TypeError, ValueError, HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            return [self._api_error(exc)]

        user = review.get("user")
        if not isinstance(user, Mapping):
            errors.append("review has no canonical GitHub user")
        else:
            if int(user.get("id") or 0) != int(reference.get("id") or 0):
                errors.append("reviewer numeric identity does not match the review author")
            if str(user.get("login") or "").casefold() != str(reference.get("login") or "").casefold():
                errors.append("reviewer login does not match the review author")
        if str(review.get("state") or "").upper() != "APPROVED":
            errors.append("review state is not APPROVED")
        if str(review.get("commit_id") or "") != expected_revision:
            errors.append("review approval is not bound to the assessed revision")
        return errors

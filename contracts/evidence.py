"""Provider-backed evidence verification for adoption assessments.

The semantic validator owns policy and injects the exact expected claim into a
copy of each evidence reference. This module proves that the referenced GitHub
Actions workflow, job, artifact, and machine-readable report all describe that
same claim on the assessed immutable revision.
"""

from __future__ import annotations

import hashlib
import io
import json
import stat
import zipfile
from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 1_000
_ALLOWED_DOWNLOAD_HOST_SUFFIXES = (
    ".actions.githubusercontent.com",
    ".githubusercontent.com",
    ".blob.core.windows.net",
)


class EvidenceVerifier(Protocol):
    """Verify provider records referenced by one assessment."""

    def verify_action(self, reference: Mapping[str, Any], expected_revision: str) -> Sequence[str]:
        """Return violations for one GitHub Actions claim report."""

    def verify_artifact(
        self,
        reference: Mapping[str, Any],
        expected_revision: str,
        expected_provider_digest: str,
    ) -> Sequence[str]:
        """Return violations for one exact artifact claim report."""

    def verify_review(self, reference: Mapping[str, Any], expected_revision: str) -> Sequence[str]:
        """Return violations for one pull-request review approval."""


class _NoRedirect(HTTPRedirectHandler):
    """Expose the signed artifact URL instead of forwarding API credentials."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


class GitHubEvidenceVerifier:
    """Verify GitHub Actions, artifact reports, and review evidence."""

    def __init__(
        self,
        token: str,
        *,
        api_base: str = "https://api.github.com",
        timeout_seconds: int = 20,
    ) -> None:
        if not token.strip():
            raise ValueError("GitHub evidence verification requires a non-empty token")
        if api_base != "https://api.github.com":
            raise ValueError("only the canonical GitHub API endpoint is supported")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._token = token.strip()
        self._api_base = api_base
        self._timeout_seconds = timeout_seconds
        self._cache: dict[str, Mapping[str, Any]] = {}
        self._artifact_cache: dict[tuple[str, int], bytes] = {}

    def _api_request(self, path: str) -> Request:
        return Request(  # noqa: S310 - fixed HTTPS GitHub API origin.
            f"{self._api_base}{path}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "ai-skills-adoption-verifier",
            },
        )

    def _get(self, path: str) -> Mapping[str, Any]:
        cached = self._cache.get(path)
        if cached is not None:
            return cached
        with urlopen(self._api_request(path), timeout=self._timeout_seconds) as response:  # noqa: S310
            payload = json.load(response)
        if not isinstance(payload, Mapping):
            raise ValueError(f"GitHub API returned a non-object for {path}")
        self._cache[path] = payload
        return payload

    @staticmethod
    def _repository_path(reference: Mapping[str, Any]) -> str:
        repository = reference.get("repository")
        if not isinstance(repository, str):
            raise ValueError("evidence repository must use owner/name")
        owner, separator, name = repository.partition("/")
        if not separator or not owner or not name or "/" in name:
            raise ValueError("evidence repository must use owner/name")
        return f"{quote(owner, safe='')}/{quote(name, safe='')}"

    @staticmethod
    def _positive_int(reference: Mapping[str, Any], field: str) -> int:
        value = reference.get(field)
        if type(value) is not int or value <= 0:
            raise ValueError(f"evidence {field} must be a positive integer")
        return value

    @staticmethod
    def _required_text(reference: Mapping[str, Any], field: str) -> str:
        value = reference.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"evidence {field} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _api_error(exc: Exception) -> str:
        if isinstance(exc, HTTPError):
            return f"GitHub API returned HTTP {exc.code}"
        if isinstance(exc, URLError):
            return f"GitHub API request failed: {exc.reason}"
        return f"GitHub evidence verification failed: {exc}"

    @staticmethod
    def _safe_report_path(value: str) -> str:
        if not value or value.startswith(("/", "\\")) or "\\" in value:
            raise ValueError("evidence report_path must be a relative POSIX path")
        parts = value.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("evidence report_path must be a relative POSIX path")
        return value

    @staticmethod
    def _validate_download_url(location: str) -> str:
        parsed = urlparse(location)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host or parsed.username or parsed.password:
            raise ValueError("GitHub artifact redirect is not a safe HTTPS URL")
        if not any(host.endswith(suffix) for suffix in _ALLOWED_DOWNLOAD_HOST_SUFFIXES):
            raise ValueError("GitHub artifact redirect host is not trusted")
        return location

    def _download_artifact_bytes(self, repository: str, artifact_id: int) -> bytes:
        cache_key = (repository, artifact_id)
        cached = self._artifact_cache.get(cache_key)
        if cached is not None:
            return cached

        path = f"/repos/{repository}/actions/artifacts/{artifact_id}/zip"
        opener = build_opener(_NoRedirect())
        try:
            opener.open(self._api_request(path), timeout=self._timeout_seconds)  # noqa: S310
        except HTTPError as exc:
            if exc.code not in {301, 302, 303, 307, 308}:
                raise
            location = exc.headers.get("Location", "")
        else:
            raise ValueError("GitHub artifact endpoint did not return a signed redirect")

        signed_url = self._validate_download_url(location)
        request = Request(
            signed_url,
            headers={"User-Agent": "ai-skills-adoption-verifier"},
        )  # noqa: S310
        with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
            data = response.read(MAX_ARCHIVE_BYTES + 1)
        if len(data) > MAX_ARCHIVE_BYTES:
            raise ValueError("GitHub artifact archive exceeds the verifier size limit")
        self._artifact_cache[cache_key] = data
        return data

    @staticmethod
    def _read_report(archive_bytes: bytes, report_path: str) -> bytes:
        try:
            archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
        except zipfile.BadZipFile as exc:
            raise ValueError("GitHub artifact is not a valid ZIP archive") from exc
        with archive:
            members = archive.infolist()
            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise ValueError("GitHub artifact contains too many entries")
            total = 0
            seen: set[str] = set()
            report: bytes | None = None
            for member in members:
                name = member.filename
                if name in seen:
                    raise ValueError("GitHub artifact contains duplicate paths")
                seen.add(name)
                if name.startswith(("/", "\\")) or "\\" in name:
                    raise ValueError("GitHub artifact contains a non-POSIX path")
                parts = name.rstrip("/").split("/") if name.rstrip("/") else []
                if any(part in {"", ".", ".."} for part in parts):
                    raise ValueError("GitHub artifact contains an unsafe path")
                mode = member.external_attr >> 16
                if stat.S_IFMT(mode) == stat.S_IFLNK:
                    raise ValueError("GitHub artifact contains a symlink")
                total += member.file_size
                if total > MAX_UNCOMPRESSED_BYTES:
                    raise ValueError("GitHub artifact exceeds the uncompressed size limit")
                if name == report_path:
                    report = archive.read(member)
            if report is None:
                raise ValueError("GitHub artifact does not contain evidence.report_path")
            return report

    @staticmethod
    def _claim_matches(report: Mapping[str, Any], expected_claim: object) -> bool:
        if not isinstance(expected_claim, Mapping):
            return False
        claims = report.get("claims")
        return isinstance(claims, list) and any(
            isinstance(claim, Mapping) and dict(claim) == dict(expected_claim)
            for claim in claims
        )

    def _verify_report(
        self,
        reference: Mapping[str, Any],
        expected_revision: str,
        repository: str,
        run_id: int,
        artifact: Mapping[str, Any],
    ) -> list[str]:
        errors: list[str] = []
        artifact_id = self._positive_int(reference, "artifact_id")
        artifact_name = self._required_text(reference, "artifact_name")
        provider_digest = self._required_text(reference, "provider_digest")
        report_path = self._safe_report_path(self._required_text(reference, "report_path"))
        report_digest = self._required_text(reference, "report_digest")

        if artifact.get("name") != artifact_name:
            errors.append("artifact name does not match evidence.artifact_name")
        workflow_run = artifact.get("workflow_run")
        if not isinstance(workflow_run, Mapping):
            errors.append("artifact has no workflow_run identity")
        else:
            if workflow_run.get("id") != run_id:
                errors.append("artifact is not part of the referenced run")
            if str(workflow_run.get("head_sha") or "") != expected_revision:
                errors.append("artifact workflow revision does not match the assessed revision")
        if artifact.get("expired") is True:
            errors.append("artifact is expired")
        if str(artifact.get("digest") or "") != provider_digest:
            errors.append("artifact provider digest does not match evidence.provider_digest")

        archive_bytes = self._download_artifact_bytes(repository, artifact_id)
        observed_provider_digest = f"sha256:{hashlib.sha256(archive_bytes).hexdigest()}"
        if observed_provider_digest != provider_digest:
            errors.append("downloaded artifact bytes do not match evidence.provider_digest")
        report_bytes = self._read_report(archive_bytes, report_path)
        observed_report_digest = f"sha256:{hashlib.sha256(report_bytes).hexdigest()}"
        if observed_report_digest != report_digest:
            errors.append("evidence report bytes do not match evidence.report_digest")
        try:
            report = json.loads(report_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("evidence report is not valid UTF-8 JSON") from exc
        if not isinstance(report, Mapping):
            raise ValueError("evidence report must contain a JSON object")

        expected_fields = {
            "schema_version": 1,
            "repository": str(reference.get("repository") or ""),
            "revision": expected_revision,
            "run_id": run_id,
            "check_run_id": self._positive_int(reference, "check_run_id"),
            "workflow_path": self._required_text(reference, "workflow_path"),
            "workflow_name": self._required_text(reference, "workflow_name"),
            "event": self._required_text(reference, "event"),
            "job_name": self._required_text(reference, "job_name"),
            "lane": self._required_text(reference, "lane"),
        }
        for field, expected in expected_fields.items():
            if report.get(field) != expected:
                errors.append(f"evidence report {field} does not match the referenced execution")
        if not self._claim_matches(report, reference.get("_expected_claim")):
            errors.append("evidence report does not contain the exact assessed claim")
        return errors

    def _verify_action_common(
        self,
        reference: Mapping[str, Any],
        expected_revision: str,
        expected_provider_digest: str | None,
    ) -> list[str]:
        errors: list[str] = []
        try:
            repository = self._repository_path(reference)
            run_id = self._positive_int(reference, "run_id")
            job_id = self._positive_int(reference, "job_id")
            raw_workflow_id = reference.get("workflow_id")
            workflow_id = None if raw_workflow_id is None else self._positive_int(reference, "workflow_id")
            workflow_path = self._required_text(reference, "workflow_path")
            workflow_name = self._required_text(reference, "workflow_name")
            event = self._required_text(reference, "event")
            job_name = self._required_text(reference, "job_name")
            self._required_text(reference, "lane")
            artifact_id = self._positive_int(reference, "artifact_id")
            run = self._get(f"/repos/{repository}/actions/runs/{run_id}")
            job = self._get(f"/repos/{repository}/actions/jobs/{job_id}")
            artifact = self._get(f"/repos/{repository}/actions/artifacts/{artifact_id}")
        except (
            KeyError,
            TypeError,
            ValueError,
            HTTPError,
            URLError,
            TimeoutError,
            json.JSONDecodeError,
        ) as exc:
            return [self._api_error(exc)]

        if str(run.get("head_sha") or "") != expected_revision:
            errors.append("workflow run head_sha does not match the assessed revision")
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            errors.append("workflow run is not completed successfully")
        if workflow_id is not None and run.get("workflow_id") != workflow_id:
            errors.append("workflow id does not match evidence.workflow_id")
        if str(run.get("path") or "") != workflow_path:
            errors.append("workflow path does not match evidence.workflow_path")
        if str(run.get("name") or "") != workflow_name:
            errors.append("workflow name does not match evidence.workflow_name")
        if str(run.get("event") or "") != event:
            errors.append("workflow event does not match evidence.event")
        if job.get("run_id") != run_id:
            errors.append("workflow job is not part of the referenced run")
        if job.get("status") != "completed" or job.get("conclusion") != "success":
            errors.append("workflow job is not completed successfully")
        if str(job.get("name") or "") != job_name:
            errors.append("workflow job name does not match evidence.job_name")
        check_run_id = self._positive_int(reference, "check_run_id")
        check_run_url = str(job.get("check_run_url") or "")
        if not check_run_url.endswith(f"/check-runs/{check_run_id}"):
            errors.append("workflow job check run does not match evidence.check_run_id")
        if (
            expected_provider_digest is not None
            and str(reference.get("provider_digest") or "") != expected_provider_digest
        ):
            errors.append("artifact provider digest does not match the expected digest")
        try:
            errors.extend(
                self._verify_report(
                    reference,
                    expected_revision,
                    repository,
                    run_id,
                    artifact,
                )
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            HTTPError,
            URLError,
            TimeoutError,
            json.JSONDecodeError,
        ) as exc:
            errors.append(self._api_error(exc))
        return errors

    def verify_action(self, reference: Mapping[str, Any], expected_revision: str) -> Sequence[str]:
        return self._verify_action_common(reference, expected_revision, None)

    def verify_artifact(
        self,
        reference: Mapping[str, Any],
        expected_revision: str,
        expected_provider_digest: str,
    ) -> Sequence[str]:
        return self._verify_action_common(reference, expected_revision, expected_provider_digest)

    def verify_review(self, reference: Mapping[str, Any], expected_revision: str) -> Sequence[str]:
        errors: list[str] = []
        try:
            repository = self._repository_path(reference)
            pull_request = self._positive_int(reference, "pull_request")
            review_id = self._positive_int(reference, "review_id")
            expected_id = self._positive_int(reference, "id")
            review = self._get(f"/repos/{repository}/pulls/{pull_request}/reviews/{review_id}")
        except (
            KeyError,
            TypeError,
            ValueError,
            HTTPError,
            URLError,
            TimeoutError,
            json.JSONDecodeError,
        ) as exc:
            return [self._api_error(exc)]

        user = review.get("user")
        if not isinstance(user, Mapping):
            errors.append("review has no canonical GitHub user")
        else:
            actual_id = user.get("id")
            if type(actual_id) is not int or actual_id <= 0:
                errors.append("review author has an invalid numeric identity")
            elif actual_id != expected_id:
                errors.append("reviewer numeric identity does not match the review author")
            if str(user.get("login") or "").casefold() != str(reference.get("login") or "").casefold():
                errors.append("reviewer login does not match the review author")
        if str(review.get("state") or "").upper() != "APPROVED":
            errors.append("review state is not APPROVED")
        if str(review.get("commit_id") or "") != expected_revision:
            errors.append("review approval is not bound to the assessed revision")
        return errors

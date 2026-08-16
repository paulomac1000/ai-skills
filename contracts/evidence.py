"""Provider-backed GitHub.com evidence verification for adoption assessments."""

from __future__ import annotations

import hashlib
import io
import json
import stat
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 1_000
READ_CHUNK_BYTES = 64 * 1024
_ALLOWED_DOWNLOAD_HOST_SUFFIXES = (
    ".actions.githubusercontent.com",
    ".githubusercontent.com",
    ".blob.core.windows.net",
)


class EvidenceVerifier(Protocol):
    """Verify provider records referenced by one assessment."""

    acceptance_authority: Mapping[str, str] | None

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

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


class GitHubEvidenceVerifier:
    """Verify candidate-produced GitHub evidence for diagnostics only."""

    acceptance_authority: Mapping[str, str] | None = None

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
            raise ValueError("only the canonical GitHub.com API endpoint is supported")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._token = token.strip()
        self._api_base = api_base
        self._timeout_seconds = timeout_seconds
        self._cache: dict[str, object] = {}
        self._artifact_cache: dict[tuple[str, int], bytes] = {}
        self._observed_producers: set[tuple[int, str]] = set()

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

    def _get_json(self, path: str) -> object:
        cached = self._cache.get(path)
        if cached is not None:
            return cached
        with urlopen(self._api_request(path), timeout=self._timeout_seconds) as response:  # noqa: S310
            payload = json.load(response)
        if not isinstance(payload, (Mapping, list)):
            raise ValueError(f"GitHub API returned an unsupported payload for {path}")
        self._cache[path] = payload
        return payload

    def _get(self, path: str) -> Mapping[str, Any]:
        payload = self._get_json(path)
        if not isinstance(payload, Mapping):
            raise ValueError(f"GitHub API returned a non-object for {path}")
        return payload

    def _get_list(self, path: str) -> list[Mapping[str, Any]]:
        payload = self._get_json(path)
        if not isinstance(payload, list):
            raise ValueError(f"GitHub API returned a non-array for {path}")
        return [item for item in payload if isinstance(item, Mapping)]

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
            response = opener.open(self._api_request(path), timeout=self._timeout_seconds)  # noqa: S310
        except HTTPError as exc:
            try:
                if exc.code not in {301, 302, 303, 307, 308}:
                    raise
                location = exc.headers.get("Location", "")
            finally:
                exc.close()
        else:
            response.close()
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
    def _read_member(archive_bytes: bytes, member_path: str) -> bytes:
        safe_path = GitHubEvidenceVerifier._safe_report_path(member_path)
        try:
            archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
        except zipfile.BadZipFile as exc:
            raise ValueError("GitHub artifact is not a valid ZIP archive") from exc
        with archive:
            members = archive.infolist()
            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise ValueError("GitHub artifact contains too many entries")
            declared_total = 0
            seen: set[str] = set()
            selected: bytes | None = None
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
                declared_total += member.file_size
                if declared_total > MAX_UNCOMPRESSED_BYTES:
                    raise ValueError("GitHub artifact exceeds the declared uncompressed size limit")
                if name != safe_path:
                    continue
                buffer = bytearray()
                try:
                    with archive.open(member, "r") as source:
                        while True:
                            remaining = MAX_UNCOMPRESSED_BYTES - len(buffer)
                            chunk = source.read(min(READ_CHUNK_BYTES, remaining + 1))
                            if not chunk:
                                break
                            buffer.extend(chunk)
                            if len(buffer) > MAX_UNCOMPRESSED_BYTES:
                                raise ValueError("GitHub artifact member exceeds the actual uncompressed size limit")
                except zipfile.BadZipFile as exc:
                    raise ValueError("GitHub artifact contains an invalid ZIP entry") from exc
                selected = bytes(buffer)
            if selected is None:
                raise ValueError(f"GitHub artifact does not contain {safe_path}")
            return selected

    @staticmethod
    def _read_report(archive_bytes: bytes, report_path: str) -> bytes:
        try:
            return GitHubEvidenceVerifier._read_member(archive_bytes, report_path)
        except ValueError as exc:
            if "does not contain" in str(exc):
                raise ValueError("GitHub artifact does not contain evidence.report_path") from exc
            raise

    @staticmethod
    def _junit_identity_for_test_case(value: object) -> str | None:
        """Translate one validated pytest node id into its default JUnit identity."""
        if not isinstance(value, str):
            return None
        path, separator, function_name = value.partition("::")
        if not separator or not path.startswith("tests/") or not path.endswith(".py"):
            return None
        if not function_name.startswith("test_") or "::" in function_name:
            return None
        parts = path[:-3].split("/")
        if any(not part or part in {".", ".."} for part in parts):
            return None
        return f"{'.'.join(parts)}::{function_name}"

    @staticmethod
    def _claim_binds_test_case(claim: Mapping[str, Any], test_case: object) -> bool:
        expected_identity = GitHubEvidenceVerifier._junit_identity_for_test_case(test_case)
        if expected_identity is None:
            return False
        bindings = claim.get("result_bindings")
        if not isinstance(bindings, list):
            return False
        for binding in bindings:
            if not isinstance(binding, Mapping):
                continue
            tests = binding.get("test_cases")
            if not isinstance(tests, list):
                continue
            if any(
                isinstance(test, Mapping)
                and test.get("identity") == expected_identity
                and test.get("status") == "passed"
                for test in tests
            ):
                return True
        return False

    @staticmethod
    def _claim_matches(report: Mapping[str, Any], expected_claim: object) -> bool:
        if not isinstance(expected_claim, Mapping):
            return False
        claims = report.get("claims")
        if not isinstance(claims, list):
            return False
        expected_test_case = expected_claim.get("test_case")
        expected_fields = {
            key: value for key, value in expected_claim.items() if key != "test_case"
        }
        for claim in claims:
            if not isinstance(claim, Mapping):
                continue
            if not all(claim.get(key) == value for key, value in expected_fields.items()):
                continue
            if expected_test_case is None or GitHubEvidenceVerifier._claim_binds_test_case(
                claim, expected_test_case
            ):
                return True
        return False

    @staticmethod
    def _junit_cases(payload: bytes) -> dict[str, str]:
        """Return unique JUnit identities and reject every failed execution."""
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            raise ValueError("evidence result is not valid JUnit XML") from exc
        cases: dict[str, str] = {}
        for element in root.iter():
            if _tag(element) != "testcase":
                continue
            classname = str(element.attrib.get("classname") or "").strip()
            name = str(element.attrib.get("name") or "").strip()
            if not name:
                raise ValueError("JUnit testcase has no name")
            identity = f"{classname}::{name}" if classname else name
            if identity in cases:
                raise ValueError(f"evidence JUnit result contains duplicate testcase identity: {identity}")
            status = "passed"
            for child in element:
                child_tag = _tag(child)
                if child_tag in {"failure", "error", "skipped"}:
                    status = child_tag
                    break
            cases[identity] = status
        if not cases:
            raise ValueError("evidence JUnit result contains no test cases")
        if any(status in {"failure", "error"} for status in cases.values()):
            raise ValueError("evidence JUnit result contains failures or errors")
        return cases

    @staticmethod
    def _producer_identity(value: object) -> tuple[int, str]:
        if not isinstance(value, Mapping):
            raise ValueError("evidence report producer must be an object")
        raw_id = value.get("id")
        login = value.get("login")
        if type(raw_id) is not int or raw_id <= 0 or not isinstance(login, str) or not login.strip():
            raise ValueError("evidence report producer has an invalid canonical identity")
        return raw_id, login.strip().casefold()

    def _verify_report(
        self,
        reference: Mapping[str, Any],
        expected_revision: str,
        repository: str,
        run_id: int,
        run: Mapping[str, Any],
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
            "format": "ai-skills-evidence-report",
            "evidence_role": "diagnostic",
            "repository": str(reference.get("repository") or ""),
            "revision": expected_revision,
            "source_head_sha": expected_revision,
            "tested_checkout_sha": expected_revision,
            "merge_sha": None,
            "provider_run_head_sha": str(run.get("head_sha") or ""),
            "run_id": run_id,
            "job_id": self._positive_int(reference, "job_id"),
            "check_run_id": self._positive_int(reference, "check_run_id"),
            "workflow_id": self._positive_int(reference, "workflow_id"),
            "workflow_path": self._required_text(reference, "workflow_path"),
            "workflow_name": self._required_text(reference, "workflow_name"),
            "event": self._required_text(reference, "event"),
            "job_name": self._required_text(reference, "job_name"),
            "lane": self._required_text(reference, "lane"),
        }
        for field, expected in expected_fields.items():
            if report.get(field) != expected:
                errors.append(f"evidence report {field} does not match the referenced execution")

        producer = self._producer_identity(report.get("producer"))
        run_actor = run.get("actor")
        if not isinstance(run_actor, Mapping):
            errors.append("workflow run has no canonical actor")
        else:
            actor_id = run_actor.get("id")
            actor_login = str(run_actor.get("login") or "").casefold()
            if producer != (actor_id, actor_login):
                errors.append("evidence report producer does not match the workflow run actor")
            else:
                self._observed_producers.add(producer)

        raw_results = report.get("results")
        result_cases: dict[str, dict[str, str]] = {}
        result_paths: dict[str, str] = {}
        if not isinstance(raw_results, list) or not raw_results:
            errors.append("evidence report has no machine result files")
        else:
            for index, raw in enumerate(raw_results):
                if not isinstance(raw, Mapping):
                    errors.append(f"evidence report results[{index}] is not an object")
                    continue
                path = self._safe_report_path(str(raw.get("path") or ""))
                if raw.get("format") != "junit":
                    errors.append(f"evidence report results[{index}] is not JUnit")
                    continue
                payload = self._read_member(archive_bytes, path)
                digest = f"sha256:{hashlib.sha256(payload).hexdigest()}"
                if raw.get("digest") != digest:
                    errors.append(f"evidence report results[{index}] digest does not match artifact bytes")
                    continue
                if digest in result_cases or path in result_paths:
                    errors.append(f"evidence report results[{index}] duplicates a result path or digest")
                    continue
                result_cases[digest] = self._junit_cases(payload)
                result_paths[path] = digest

        raw_executions = report.get("executions")
        executions: dict[str, Mapping[str, Any]] = {}
        if not isinstance(raw_executions, list) or not raw_executions:
            errors.append("evidence report has no execution records")
        else:
            for index, raw in enumerate(raw_executions):
                if not isinstance(raw, Mapping):
                    errors.append(f"evidence report executions[{index}] is not an object")
                    continue
                execution_id = str(raw.get("execution_id") or "")
                digests = raw.get("result_digests")
                if not execution_id or execution_id in executions:
                    errors.append(f"evidence report executions[{index}] has a missing or duplicate execution_id")
                    continue
                if raw.get("exit_status") != 0:
                    errors.append(f"evidence report executions[{index}] has a nonzero exit status")
                if (
                    not isinstance(digests, list)
                    or not digests
                    or any(not isinstance(digest, str) or digest not in result_cases for digest in digests)
                ):
                    errors.append(f"evidence report executions[{index}] is not bound to verified result bytes")
                command_digest = str(raw.get("command_digest") or "")
                if not command_digest.startswith("sha256:") or len(command_digest) != 71:
                    errors.append(f"evidence report executions[{index}] has an invalid command digest")
                executions[execution_id] = raw

        claims = report.get("claims")
        if not isinstance(claims, list) or not claims:
            errors.append("evidence report has no claims")
        else:
            for index, raw in enumerate(claims):
                if not isinstance(raw, Mapping):
                    errors.append(f"evidence report claims[{index}] is not an object")
                    continue
                execution_id = str(raw.get("execution_id") or "")
                execution = executions.get(execution_id)
                if execution is None:
                    errors.append(f"evidence report claims[{index}] is not bound to a verified execution")
                    continue
                if raw.get("command_digest") != execution.get("command_digest"):
                    errors.append(f"evidence report claims[{index}] command does not match its execution")
                if raw.get("exit_status") != 0 or execution.get("exit_status") != 0:
                    errors.append(f"evidence report claims[{index}] has a nonzero exit status")
                execution_digests = set(execution.get("result_digests") or [])
                bindings = raw.get("result_bindings")
                if not isinstance(bindings, list) or not bindings:
                    errors.append(f"evidence report claims[{index}] has no result bindings")
                    continue
                observed_cases: set[tuple[str, str]] = set()
                for binding_index, binding in enumerate(bindings):
                    if not isinstance(binding, Mapping):
                        errors.append(
                            f"evidence report claims[{index}].result_bindings[{binding_index}] is not an object"
                        )
                        continue
                    path = str(binding.get("result_path") or "")
                    digest = str(binding.get("result_digest") or "")
                    if result_paths.get(path) != digest or digest not in execution_digests:
                        errors.append(
                            f"evidence report claims[{index}].result_bindings[{binding_index}] "
                            "is not bound to its execution result bytes"
                        )
                        continue
                    tests = binding.get("test_cases")
                    if not isinstance(tests, list) or not tests:
                        errors.append(
                            f"evidence report claims[{index}].result_bindings[{binding_index}] has no test cases"
                        )
                        continue
                    for test_index, test in enumerate(tests):
                        if not isinstance(test, Mapping):
                            errors.append(
                                f"evidence report claims[{index}].result_bindings[{binding_index}]."
                                f"test_cases[{test_index}] is not an object"
                            )
                            continue
                        identity = str(test.get("identity") or "")
                        status = str(test.get("status") or "")
                        key = (digest, identity)
                        if key in observed_cases:
                            errors.append(f"evidence report claims[{index}] duplicates a testcase binding")
                            continue
                        observed_cases.add(key)
                        if status != "passed" or result_cases[digest].get(identity) != "passed":
                            errors.append(
                                f"evidence report claims[{index}] is not bound to a passed testcase in its result bytes"
                            )

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
            check_run_id = self._positive_int(reference, "check_run_id")
            workflow_id = self._positive_int(reference, "workflow_id")
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
        if run.get("workflow_id") != workflow_id:
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
                    run,
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

    @staticmethod
    def _canonical_user(value: object) -> tuple[int, str] | None:
        if not isinstance(value, Mapping):
            return None
        raw_id = value.get("id")
        login = value.get("login")
        if type(raw_id) is not int or raw_id <= 0 or not isinstance(login, str) or not login.strip():
            return None
        return raw_id, login.strip().casefold()

    def _pull_request_identities(self, repository: str, pull_request: int) -> tuple[str, set[tuple[int, str]]]:
        pull = self._get(f"/repos/{repository}/pulls/{pull_request}")
        head = pull.get("head")
        head_sha = str(head.get("sha") or "") if isinstance(head, Mapping) else ""
        identities: set[tuple[int, str]] = set()
        author = self._canonical_user(pull.get("user"))
        if author is None:
            raise ValueError(
                "cannot prove reviewer independence because the pull request author has no canonical identity"
            )
        identities.add(author)
        raw_commit_count = pull.get("commits")
        if type(raw_commit_count) is not int or raw_commit_count < 0:
            raise ValueError("pull request has no canonical commit count")
        if raw_commit_count > 250:
            raise ValueError("cannot prove reviewer independence for a pull request with more than 250 commits")
        page = 1
        observed_commits = 0
        while observed_commits < raw_commit_count:
            commits = self._get_list(f"/repos/{repository}/pulls/{pull_request}/commits?per_page=100&page={page}")
            if not commits:
                break
            observed_commits += len(commits)
            for commit in commits:
                for field in ("author", "committer"):
                    identity = self._canonical_user(commit.get(field))
                    if identity is None:
                        raise ValueError(
                            f"cannot prove reviewer independence because a commit {field} has no canonical identity"
                        )
                    identities.add(identity)
            page += 1
        if observed_commits != raw_commit_count:
            raise ValueError("cannot prove reviewer independence because provider commit enumeration is incomplete")
        identities.update(self._observed_producers)
        return head_sha, identities

    def verify_review(self, reference: Mapping[str, Any], expected_revision: str) -> Sequence[str]:
        errors: list[str] = []
        try:
            repository = self._repository_path(reference)
            pull_request = self._positive_int(reference, "pull_request")
            review_id = self._positive_int(reference, "review_id")
            expected_id = self._positive_int(reference, "id")
            review = self._get(f"/repos/{repository}/pulls/{pull_request}/reviews/{review_id}")
            head_sha, forbidden = self._pull_request_identities(repository, pull_request)
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
        actual = self._canonical_user(user)
        if actual is None:
            errors.append("review author has an invalid numeric identity")
        else:
            if actual[0] != expected_id:
                errors.append("reviewer numeric identity does not match the review author")
            if actual[1] != str(reference.get("login") or "").casefold():
                errors.append("reviewer login does not match the review author")
            if actual in forbidden:
                errors.append("reviewer is not independent from PR, commit, or evidence provenance")
        if head_sha != expected_revision:
            errors.append("pull request head does not match the assessed revision")
        if str(review.get("state") or "").upper() != "APPROVED":
            errors.append("review state is not APPROVED")
        if str(review.get("commit_id") or "") != expected_revision:
            errors.append("review approval is not bound to the assessed revision")
        return errors

#!/usr/bin/env python3
"""Verify GitHub provider controls that repository YAML cannot prove by itself."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

TOOLS = Path(__file__).resolve().parent
REPOSITORY_ROOT = TOOLS.parents[2]
CONTRACTS = REPOSITORY_ROOT / "contracts"
for candidate in (TOOLS, CONTRACTS):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import check_github_actions_policy as workflow_policy  # noqa: E402
import check_github_actions_policy_impl as workflow_impl  # noqa: E402
import validate_trusted_executable_sources as trusted_sources  # noqa: E402

API_VERSION = "2026-03-10"
GITHUB_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
ENVIRONMENT_PAGE_SIZE = 100
MAX_ENVIRONMENT_PAGES = 100


@dataclass(frozen=True)
class ProviderFinding:
    state: str
    message: str

    def render(self) -> str:
        return f"{self.state.upper()}: {self.message}"


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Fail closed on redirects so provider identity cannot silently change."""

    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


class GitHubClient:
    """Small read-only GitHub REST client with explicit response bounds."""

    def __init__(self, token: str, *, api_base: str = "https://api.github.com", timeout_seconds: int = 20) -> None:
        self._token = token
        self._api_base = api_base.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._opener = urllib.request.build_opener(_RejectRedirects())

    def get(self, path: str) -> tuple[int, object | None, str]:
        request = urllib.request.Request(
            f"{self._api_base}{path}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "ai-skills-provider-preflight",
            },
            method="GET",
        )
        try:
            with self._opener.open(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                status = int(response.status)
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            if 300 <= status < 400:
                location = exc.headers.get("Location", "") if exc.headers is not None else ""
                suffix = f" to {location}" if location else ""
                return status, None, f"provider redirect is not accepted{suffix}"
            raw = exc.read(MAX_RESPONSE_BYTES + 1)
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            return 0, None, str(exc)
        if len(raw) > MAX_RESPONSE_BYTES:
            return status, None, "response exceeds bounded provider-preflight limit"
        if not raw:
            return status, None, ""
        try:
            return status, json.loads(raw.decode("utf-8")), ""
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return status, None, f"invalid JSON response: {exc}"


def _provider_error(label: str, status: int, detail: str) -> ProviderFinding:
    if status in {401, 403, 404}:
        return ProviderFinding(
            "unverifiable",
            f"cannot verify {label}: GitHub returned HTTP {status}; check token permissions, plan support, and visibility",
        )
    suffix = f": {detail}" if detail else ""
    return ProviderFinding("unverifiable", f"cannot verify {label}: GitHub request failed with HTTP {status}{suffix}")


def _profiles_from_immutable_policy(text: str) -> tuple[dict[str, str], list[ProviderFinding]]:
    """Parse the workflow-profile declaration captured from one authenticated Git object."""
    try:
        document = yaml.load(text, Loader=workflow_impl._UniqueKeyLoader)
    except yaml.YAMLError as exc:
        return {}, [ProviderFinding("misconfigured", f"cannot parse workflow policy: {exc}")]
    if not isinstance(document, Mapping) or document.get("schema_version") != 1:
        return {}, [ProviderFinding("misconfigured", "workflow policy must be a schema_version 1 mapping")]
    if set(document) != {"schema_version", "workflows"}:
        return {}, [ProviderFinding("misconfigured", "workflow policy contains unsupported fields")]
    raw_workflows = document.get("workflows")
    if not isinstance(raw_workflows, Mapping):
        return {}, [ProviderFinding("misconfigured", "workflow policy workflows must be a mapping")]

    profiles: dict[str, str] = {}
    findings: list[ProviderFinding] = []
    for raw_path, raw_profile in raw_workflows.items():
        if not isinstance(raw_path, str) or not isinstance(raw_profile, str):
            findings.append(ProviderFinding("misconfigured", "workflow policy paths and profiles must be strings"))
            continue
        candidate = Path(raw_path)
        if (
            candidate.is_absolute()
            or "\\" in raw_path
            or ".." in candidate.parts
            or candidate.parts[:2] != (".github", "workflows")
            or candidate.suffix.casefold() not in workflow_impl._WORKFLOW_SUFFIXES
        ):
            findings.append(ProviderFinding("misconfigured", f"invalid governed workflow path: {raw_path}"))
            continue
        selected_profile = raw_profile.casefold()
        if selected_profile not in workflow_impl._PROFILES:
            findings.append(
                ProviderFinding("misconfigured", f"unknown profile for {raw_path}: {raw_profile}")
            )
            continue
        profiles[candidate.as_posix()] = selected_profile
    return profiles, findings


def _release_environments(
    repository_root: Path,
    repository_revision: str | None = None,
) -> tuple[set[str], list[ProviderFinding]]:
    root = repository_root.resolve(strict=True)
    if repository_revision is None:
        profiles, policy_findings = workflow_policy._repository_profiles(root)
        findings = [ProviderFinding("misconfigured", finding.render()) for finding in policy_findings]

        def read_workflow(relative: str) -> tuple[str | None, str | None]:
            return workflow_policy._read_workflow(root / relative, root)

    else:
        try:
            policy_text = trusted_sources._authority_text(
                root,
                repository_revision,
                workflow_policy.POLICY_PATH.as_posix(),
                max_bytes=workflow_policy.MAX_POLICY_BYTES,
            )
        except ValueError as exc:
            if "path is not tracked at the locked revision" in str(exc):
                profiles, findings = {}, []
            else:
                return set(), [ProviderFinding("unverifiable", f"cannot inspect immutable workflow policy: {exc}")]
        else:
            profiles, findings = _profiles_from_immutable_policy(policy_text)

        def read_workflow(relative: str) -> tuple[str | None, str | None]:
            try:
                text = trusted_sources._authority_text(
                    root,
                    repository_revision,
                    relative,
                    max_bytes=workflow_policy.MAX_WORKFLOW_BYTES,
                )
            except ValueError as exc:
                return None, str(exc)
            return text, None

    environments: set[str] = set()
    for relative, profile in sorted(profiles.items()):
        if profile != "protected-release":
            continue
        text, error = read_workflow(relative)
        if error or text is None:
            findings.append(ProviderFinding("misconfigured", f"cannot inspect protected release {relative}: {error}"))
            continue
        try:
            document = yaml.load(text, Loader=workflow_impl._UniqueKeyLoader)
        except yaml.YAMLError as exc:
            findings.append(ProviderFinding("misconfigured", f"cannot parse protected release {relative}: {exc}"))
            continue
        jobs = document.get("jobs") if isinstance(document, Mapping) else None
        if not isinstance(jobs, Mapping):
            continue
        for job_name, raw_job in jobs.items():
            if not isinstance(raw_job, Mapping):
                continue
            raw_environment = raw_job.get("environment")
            if raw_environment is None:
                continue
            if isinstance(raw_environment, str):
                name = raw_environment
            elif isinstance(raw_environment, Mapping) and isinstance(raw_environment.get("name"), str):
                name = str(raw_environment["name"])
            else:
                findings.append(
                    ProviderFinding(
                        "unverifiable",
                        f"protected release {relative} job {job_name} uses a non-literal environment identity",
                    )
                )
                continue
            if "${{" in name or not name.strip():
                findings.append(
                    ProviderFinding(
                        "unverifiable",
                        f"protected release {relative} job {job_name} environment must be a literal provider identity",
                    )
                )
                continue
            environments.add(name.strip())
    return environments, findings


def _status_check_names(protection: Mapping[str, Any]) -> set[str]:
    raw = protection.get("required_status_checks")
    if not isinstance(raw, Mapping):
        return set()
    names: set[str] = set()
    raw_contexts = raw.get("contexts")
    if isinstance(raw_contexts, list):
        names.update(str(item) for item in raw_contexts if isinstance(item, str))
    checks = raw.get("checks")
    if isinstance(checks, list):
        names.update(
            str(item["context"])
            for item in checks
            if isinstance(item, Mapping) and isinstance(item.get("context"), str)
        )
    return names


def _repository_environment_names(
    encoded_repository: str,
    client: GitHubClient,
) -> tuple[set[str] | None, list[ProviderFinding]]:
    """List every environment or fail unverifiable when pagination cannot be proven complete."""
    available: set[str] = set()
    observed_count = 0
    expected_total: int | None = None

    for page in range(1, MAX_ENVIRONMENT_PAGES + 1):
        query = f"?per_page={ENVIRONMENT_PAGE_SIZE}"
        if page > 1:
            query += f"&page={page}"
        status, document, detail = client.get(f"/repos/{encoded_repository}/environments{query}")
        if status != 200 or not isinstance(document, Mapping):
            return None, [_provider_error(f"repository environments page {page}", status, detail)]

        raw_environments = document.get("environments")
        if not isinstance(raw_environments, list):
            return None, [ProviderFinding("unverifiable", "GitHub environments response has no environments list")]

        if page == 1 and "total_count" in document:
            raw_total = document.get("total_count")
            if type(raw_total) is not int or raw_total < 0:
                return None, [
                    ProviderFinding("unverifiable", "GitHub environments response has an invalid total_count")
                ]
            expected_total = raw_total

        observed_count += len(raw_environments)
        available.update(
            str(item["name"])
            for item in raw_environments
            if isinstance(item, Mapping) and isinstance(item.get("name"), str)
        )

        if expected_total is not None:
            if observed_count > expected_total:
                return None, [
                    ProviderFinding(
                        "unverifiable",
                        "GitHub environments pagination returned more records than total_count",
                    )
                ]
            if observed_count == expected_total:
                return available, []
            if not raw_environments:
                return None, [
                    ProviderFinding(
                        "unverifiable",
                        "GitHub environments pagination ended before total_count was reached",
                    )
                ]
        elif len(raw_environments) < ENVIRONMENT_PAGE_SIZE:
            return available, []

    return None, [
        ProviderFinding(
            "unverifiable",
            f"GitHub environments pagination exceeds the bounded {MAX_ENVIRONMENT_PAGES}-page preflight limit",
        )
    ]


def check_provider_controls(
    repository_root: Path,
    repository: str,
    client: GitHubClient,
    *,
    default_branch: str | None = None,
    required_checks: Sequence[str] = (),
    repository_revision: str | None = None,
) -> list[ProviderFinding]:
    """Return provider-backed control findings, preserving unknown as unverifiable."""
    if GITHUB_REPOSITORY.fullmatch(repository) is None:
        return [ProviderFinding("misconfigured", "repository must use GitHub owner/name syntax")]
    findings: list[ProviderFinding] = []
    if repository_revision is not None:
        if trusted_sources.FULL_SHA.fullmatch(repository_revision) is None:
            return [
                ProviderFinding(
                    "misconfigured",
                    "repository revision must be a full lowercase 40-character commit SHA",
                )
            ]
        try:
            trusted_sources._verify_candidate_identity(repository_root, repository, repository_revision)
        except ValueError as exc:
            return [
                ProviderFinding(
                    "unverifiable",
                    f"cannot bind provider scope to immutable candidate revision: {exc}",
                )
            ]
    encoded_repository = "/".join(urllib.parse.quote(part, safe="") for part in repository.split("/", 1))

    branch = default_branch
    if branch is None:
        status, document, detail = client.get(f"/repos/{encoded_repository}")
        if status != 200 or not isinstance(document, Mapping):
            return [_provider_error("repository metadata/default branch", status, detail)]
        raw_branch = document.get("default_branch")
        if not isinstance(raw_branch, str) or not raw_branch:
            return [ProviderFinding("unverifiable", "repository metadata did not expose a default branch")]
        branch = raw_branch

    encoded_branch = urllib.parse.quote(branch, safe="")
    status, branch_document, detail = client.get(f"/repos/{encoded_repository}/branches/{encoded_branch}")
    if status != 200 or not isinstance(branch_document, Mapping):
        findings.append(_provider_error(f"default branch {branch!r}", status, detail))
    elif branch_document.get("protected") is not True:
        findings.append(
            ProviderFinding("misconfigured", f"default branch {branch!r} is not protected by provider policy")
        )

    required = {item for item in required_checks if item}
    if required:
        status, protection, detail = client.get(f"/repos/{encoded_repository}/branches/{encoded_branch}/protection")
        if status != 200 or not isinstance(protection, Mapping):
            findings.append(_provider_error(f"required checks on branch {branch!r}", status, detail))
        else:
            missing = sorted(required - _status_check_names(protection))
            if missing:
                findings.append(
                    ProviderFinding(
                        "misconfigured",
                        f"default branch {branch!r} is missing required provider checks: {', '.join(missing)}",
                    )
                )

    environments, discovery_findings = _release_environments(repository_root, repository_revision)
    findings.extend(discovery_findings)
    if environments:
        available, environment_findings = _repository_environment_names(encoded_repository, client)
        findings.extend(environment_findings)
        if available is None:
            return findings
        for name in sorted(environments):
            if name not in available:
                findings.append(
                    ProviderFinding("misconfigured", f"declared release environment {name!r} does not exist")
                )
                continue
            encoded_name = urllib.parse.quote(name, safe="")
            env_status, environment, env_detail = client.get(f"/repos/{encoded_repository}/environments/{encoded_name}")
            if env_status != 200 or not isinstance(environment, Mapping):
                findings.append(_provider_error(f"release environment {name!r}", env_status, env_detail))
                continue
            rules = environment.get("protection_rules")
            has_rules = isinstance(rules, list) and bool(rules)
            branch_policy = environment.get("deployment_branch_policy")
            protected_branches = isinstance(branch_policy, Mapping) and branch_policy.get("protected_branches") is True
            custom_policies = isinstance(branch_policy, Mapping) and branch_policy.get("custom_branch_policies") is True
            if custom_policies:
                policy_status, policies, policy_detail = client.get(
                    f"/repos/{encoded_repository}/environments/{encoded_name}/deployment-branch-policies?per_page=100"
                )
                if policy_status != 200 or not isinstance(policies, Mapping):
                    findings.append(
                        _provider_error(f"deployment branch policy for {name!r}", policy_status, policy_detail)
                    )
                    continue
                total_count = policies.get("total_count")
                if not isinstance(total_count, int) or isinstance(total_count, bool):
                    findings.append(
                        ProviderFinding(
                            "unverifiable",
                            f"deployment branch policy for {name!r} did not expose an integer total_count",
                        )
                    )
                    continue
                custom_policies = total_count > 0
            if not (has_rules or protected_branches or custom_policies):
                findings.append(
                    ProviderFinding(
                        "misconfigured",
                        f"release environment {name!r} has no protection rule or deployment-branch restriction",
                    )
                )
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository_root", nargs="?", type=Path, default=Path("."))
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--token-env", default="AI_SKILLS_PROVIDER_TOKEN")
    parser.add_argument("--default-branch")
    parser.add_argument("--required-check", action="append", default=[])
    parser.add_argument(
        "--revision",
        help="Externally supplied immutable candidate commit SHA used to scope workflow policy",
    )
    args = parser.parse_args(argv)
    if not args.repository:
        parser.error("--repository or GITHUB_REPOSITORY is required")
    token = os.environ.get(args.token_env, "")
    if not token:
        print(f"UNVERIFIABLE: provider token environment variable {args.token_env} is not set")
        return 2
    try:
        findings = check_provider_controls(
            args.repository_root,
            args.repository,
            GitHubClient(token),
            default_branch=args.default_branch,
            required_checks=args.required_check,
            repository_revision=args.revision,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"UNVERIFIABLE: provider preflight could not complete safely: {exc}")
        return 2
    for finding in findings:
        print(finding.render())
    if any(finding.state == "misconfigured" for finding in findings):
        return 1
    if findings:
        return 2
    print("provider controls: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

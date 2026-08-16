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


class GitHubClient:
    """Small read-only GitHub REST client with explicit response bounds."""

    def __init__(self, token: str, *, api_base: str = "https://api.github.com", timeout_seconds: int = 20) -> None:
        self._token = token
        self._api_base = api_base.rstrip("/")
        self._timeout_seconds = timeout_seconds

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
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                status = int(response.status)
        except urllib.error.HTTPError as exc:
            raw = exc.read(MAX_RESPONSE_BYTES + 1)
            status = int(exc.code)
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


def _release_environments(repository_root: Path) -> tuple[set[str], list[ProviderFinding]]:
    root = repository_root.resolve(strict=True)
    profiles, policy_findings = workflow_policy._repository_profiles(root)
    findings = [ProviderFinding("misconfigured", finding.render()) for finding in policy_findings]
    environments: set[str] = set()
    for relative, profile in sorted(profiles.items()):
        if profile != "protected-release":
            continue
        path = root / relative
        text, error = workflow_policy._read_workflow(path, root)
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
) -> list[ProviderFinding]:
    """Return provider-backed control findings, preserving unknown as unverifiable."""
    if GITHUB_REPOSITORY.fullmatch(repository) is None:
        return [ProviderFinding("misconfigured", "repository must use GitHub owner/name syntax")]
    findings: list[ProviderFinding] = []
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

    environments, discovery_findings = _release_environments(repository_root)
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

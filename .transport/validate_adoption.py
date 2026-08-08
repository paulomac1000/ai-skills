#!/usr/bin/env python3
"""Validate ai-skills adoption assessments against one shared applicability authority."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Mapping

import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = ROOT / "adoption-assessment.schema.json"
CATALOG_PATH = ROOT / "rule-catalog.yaml"
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
PLACEHOLDER_RE = re.compile(r"(?:REPLACE_WITH|TODO|TBD)", re.IGNORECASE)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from rule_applicability import RuleContext, expected_rules  # noqa: E402


def _load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot read YAML {path}: {exc}") from exc


def _schema_findings(document: Any) -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    findings: list[str] = []
    for error in sorted(validator.iter_errors(document), key=lambda item: tuple(str(part) for part in item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        findings.append(f"schema {location}: {error.message}")
    return findings


def _catalog() -> Mapping[str, Any]:
    value = _load_yaml(CATALOG_PATH)
    if not isinstance(value, Mapping):
        raise ValueError("rule catalog must be a mapping")
    return value


def _catalog_index(catalog: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    raw = catalog.get("rules", [])
    if not isinstance(raw, list):
        raise ValueError("rule catalog rules must be an array")
    result: dict[str, Mapping[str, Any]] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        rule_id = item.get("id") or item.get("rule_id")
        if isinstance(rule_id, str) and rule_id:
            result[rule_id] = item
    return result


def _expected_ids(catalog: Mapping[str, Any], skill: str, context: RuleContext) -> set[str]:
    selected = expected_rules(catalog, skill, context)
    if isinstance(selected, Mapping):
        return {str(key) for key in selected}
    result: set[str] = set()
    for item in selected:
        if isinstance(item, str):
            result.add(item)
        elif isinstance(item, Mapping):
            value = item.get("id") or item.get("rule_id")
            if isinstance(value, str):
                result.add(value)
        else:
            value = getattr(item, "rule_id", None) or getattr(item, "id", None)
            if isinstance(value, str):
                result.add(value)
    return result


def _rule_context(document: Mapping[str, Any], *, approval: bool) -> tuple[RuleContext | None, list[str]]:
    findings: list[str] = []
    raw = document.get("rule_context")
    if raw is None:
        if approval:
            findings.append("explicit rule_context is required before approval")
            return None, findings
        extension = document.get("extensions", {})
        mcp = extension.get("mcp", {}) if isinstance(extension, Mapping) else {}
        target = mcp.get("target_level", "L1") if isinstance(mcp, Mapping) else "L1"
        profiles = mcp.get("profiles", []) if isinstance(mcp, Mapping) else []
        raw = {"target_level": target, "profiles": profiles, "capabilities": []}
    if not isinstance(raw, Mapping):
        return None, ["rule_context must be an object"]
    target = raw.get("target_level", "L1")
    profiles = raw.get("profiles", [])
    capabilities = raw.get("capabilities", [])
    if not isinstance(target, str) or not isinstance(profiles, list) or not isinstance(capabilities, list):
        return None, ["rule_context target_level/profiles/capabilities are malformed"]
    try:
        context = RuleContext(
            target_level=target,
            profiles=frozenset(str(value) for value in profiles),
            capabilities=frozenset(str(value) for value in capabilities),
        )
    except (TypeError, ValueError) as exc:
        message = str(exc)
        if "profile" in message:
            findings.append(f"unknown deployment profiles: {message}")
        elif "capabil" in message:
            findings.append(f"unknown capability classes: {message}")
        else:
            findings.append(f"invalid rule_context: {message}")
        return None, findings
    return context, findings


def _parse_expiry(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _is_waivable(rule: Mapping[str, Any]) -> bool:
    value = rule.get("waivable")
    if isinstance(value, bool):
        return value
    policy = rule.get("waiver")
    return bool(policy.get("allowed")) if isinstance(policy, Mapping) else False


def _validate_applicability(document: Mapping[str, Any], catalog: Mapping[str, Any], context: RuleContext | None) -> list[str]:
    findings: list[str] = []
    index = _catalog_index(catalog)
    skill = document.get("skill", {})
    skill_name = skill.get("name") if isinstance(skill, Mapping) else None
    expected: set[str] = set()
    if context is not None and isinstance(skill_name, str):
        try:
            expected = _expected_ids(catalog, skill_name, context)
        except (TypeError, ValueError) as exc:
            findings.append(f"shared applicability engine rejected context: {exc}")

    raw_entries = document.get("applicability", [])
    entries = raw_entries if isinstance(raw_entries, list) else []
    by_id: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        rule_id = entry.get("rule_id")
        if not isinstance(rule_id, str):
            continue
        if rule_id in by_id:
            findings.append(f"duplicate applicability rule {rule_id}")
            continue
        by_id[rule_id] = entry
        if rule_id not in index:
            findings.append(f"unknown catalog rule {rule_id}")
            continue
        status = entry.get("status")
        if context is not None and rule_id in expected and status == "not-applicable":
            findings.append(f"rule {rule_id} is applicable under the shared rule context and cannot be marked not-applicable")
        if context is not None and rule_id not in expected and status in {"applicable", "deferred"}:
            findings.append(f"rule {rule_id} is not applicable under the shared rule context and cannot be marked {status}")
        if status == "applicable":
            if not entry.get("implementation"):
                findings.append(f"applicable rule {rule_id} has no implementation evidence")
            verification = entry.get("verification")
            if not isinstance(verification, list) or not verification:
                findings.append(f"applicable rule {rule_id} has no executable verification")
        if status == "deferred" and not _is_waivable(index[rule_id]):
            findings.append(f"rule {rule_id} is not waivable in the rule catalog")

    for rule_id in sorted(expected - set(by_id)):
        findings.append(f"missing applicable catalog rule {rule_id} for the shared rule context")

    waivers_raw = document.get("waivers", [])
    waivers = waivers_raw if isinstance(waivers_raw, list) else []
    waiver_by_id: dict[str, Mapping[str, Any]] = {}
    today = datetime.now(UTC).date()
    for waiver in waivers:
        if not isinstance(waiver, Mapping):
            continue
        waiver_id = waiver.get("id")
        rule_id = waiver.get("rule_id")
        if not isinstance(waiver_id, str) or not isinstance(rule_id, str):
            continue
        waiver_by_id[waiver_id] = waiver
        expiry = _parse_expiry(waiver.get("expires"))
        if expiry is None:
            findings.append(f"waiver {waiver_id} has invalid expiry")
        elif expiry < today:
            findings.append(f"waiver {waiver_id} expired on {expiry.isoformat()}")
        entry = by_id.get(rule_id)
        if entry is None or entry.get("status") != "deferred" or entry.get("waiver_id") != waiver_id:
            findings.append(f"waiver {waiver_id} does not map to a deferred rule")
        catalog_rule = index.get(rule_id)
        if catalog_rule is not None and not _is_waivable(catalog_rule):
            findings.append(f"waiver {waiver_id} targets rule {rule_id}, which is not waivable in the rule catalog")

    for rule_id, entry in by_id.items():
        if entry.get("status") != "deferred":
            continue
        waiver_id = entry.get("waiver_id")
        if not isinstance(waiver_id, str) or waiver_id not in waiver_by_id:
            findings.append(f"deferred rule {rule_id} requires a declared waiver")
    return findings


def _validate_revisions(document: Mapping[str, Any]) -> list[str]:
    findings: list[str] = []
    repository = document.get("repository", {})
    revision = repository.get("revision") if isinstance(repository, Mapping) else None
    if not isinstance(revision, str) or not REVISION_RE.fullmatch(revision):
        findings.append("repository.revision must be a full immutable 40-hex commit SHA")
        return findings
    artifact = document.get("artifact_verification", {})
    exact = artifact.get("exact_revision") if isinstance(artifact, Mapping) else None
    if exact != revision:
        findings.append("artifact_verification.exact_revision must equal repository.revision")
    for section_name in ("applicability", "compatibility_results"):
        section = document.get(section_name, [])
        if not isinstance(section, list):
            continue
        for entry in section:
            if not isinstance(entry, Mapping):
                continue
            verifications = entry.get("verification", []) if section_name == "applicability" else [entry]
            if not isinstance(verifications, list):
                continue
            for verification in verifications:
                if not isinstance(verification, Mapping):
                    continue
                evidence = verification.get("evidence")
                if isinstance(evidence, Mapping) and evidence.get("revision") != revision:
                    findings.append(f"{section_name} evidence revision must equal repository.revision")
    return findings


def _validate_transport_results(document: Mapping[str, Any]) -> list[str]:
    findings: list[str] = []
    extensions = document.get("extensions", {})
    mcp = extensions.get("mcp") if isinstance(extensions, Mapping) else None
    if not isinstance(mcp, Mapping):
        return findings
    advertised_raw = mcp.get("advertised_transports", [])
    advertised = set(advertised_raw) if isinstance(advertised_raw, list) else set()
    results = mcp.get("transport_results", {})
    if not isinstance(results, Mapping):
        return findings
    for transport in results:
        if transport not in advertised:
            findings.append(f"transport_results key {transport} is not advertised")
    return findings


def _github_json(url: str, token: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ai-skills-adoption-validator",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - fixed github.com API authority
            return json.loads(response.read())
    except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise ValueError(f"GitHub provider lookup failed: {exc}") from exc


def _iter_evidence(document: Mapping[str, Any]):  # type: ignore[no-untyped-def]
    applicability = document.get("applicability", [])
    if isinstance(applicability, list):
        for entry in applicability:
            if isinstance(entry, Mapping) and isinstance(entry.get("verification"), list):
                for verification in entry["verification"]:
                    if isinstance(verification, Mapping) and isinstance(verification.get("evidence"), Mapping):
                        yield verification["evidence"]
    compatibility = document.get("compatibility_results", [])
    if isinstance(compatibility, list):
        for entry in compatibility:
            if isinstance(entry, Mapping) and isinstance(entry.get("evidence"), Mapping):
                yield entry["evidence"]
    artifacts = document.get("artifact_verification", {})
    if isinstance(artifacts, Mapping) and isinstance(artifacts.get("artifacts"), list):
        for artifact in artifacts["artifacts"]:
            if isinstance(artifact, Mapping) and isinstance(artifact.get("evidence"), Mapping):
                yield artifact["evidence"]


def _validate_provider(document: Mapping[str, Any], token: str) -> list[str]:
    findings: list[str] = []
    repository = document.get("repository", {})
    repo_name = repository.get("name") if isinstance(repository, Mapping) else None
    revision = repository.get("revision") if isinstance(repository, Mapping) else None
    if not isinstance(repo_name, str) or not isinstance(revision, str):
        return ["provider-backed verification requires repository identity"]
    for evidence in _iter_evidence(document):
        if evidence.get("provider") != "github-actions":
            continue
        if evidence.get("repository") != repo_name or evidence.get("revision") != revision:
            findings.append("provider evidence must bind the assessed repository and exact revision")
            continue
        run_id = evidence.get("run_id")
        job_id = evidence.get("job_id")
        artifact_id = evidence.get("artifact_id")
        if isinstance(run_id, int):
            try:
                run = _github_json(f"https://api.github.com/repos/{repo_name}/actions/runs/{run_id}", token)
                if run.get("head_sha") != revision or run.get("conclusion") not in {"success", None}:
                    findings.append(f"GitHub Actions run {run_id} is not successful evidence for the assessed revision")
            except ValueError as exc:
                findings.append(str(exc))
        if isinstance(job_id, int):
            try:
                job = _github_json(f"https://api.github.com/repos/{repo_name}/actions/jobs/{job_id}", token)
                if job.get("conclusion") != "success":
                    findings.append(f"GitHub Actions job {job_id} is not successful")
            except ValueError as exc:
                findings.append(str(exc))
        if isinstance(artifact_id, int):
            try:
                artifact = _github_json(f"https://api.github.com/repos/{repo_name}/actions/artifacts/{artifact_id}", token)
                if artifact.get("expired") is True or artifact.get("name") != evidence.get("artifact_name"):
                    findings.append(f"GitHub Actions artifact {artifact_id} is expired or has the wrong identity")
            except ValueError as exc:
                findings.append(str(exc))
    return findings


def _validate_decision(document: Mapping[str, Any], *, require_approval: bool, token: str | None) -> list[str]:
    findings: list[str] = []
    decision = document.get("decision", {})
    if not isinstance(decision, Mapping):
        return ["decision must be an object"]
    status = decision.get("status")
    mode = document.get("verification_mode")
    approval = status == "approve"
    if require_approval and not approval:
        findings.append("approval is required but decision.status is not approve")
    if approval and mode != "provider-backed":
        findings.append("structural-attestation cannot approve an adoption assessment")
    reviewer = decision.get("reviewer")
    if approval:
        if not isinstance(reviewer, Mapping):
            findings.append("approved assessment requires reviewer evidence")
            return findings
        repository = document.get("repository", {})
        repo_name = repository.get("name") if isinstance(repository, Mapping) else None
        revision = repository.get("revision") if isinstance(repository, Mapping) else None
        if reviewer.get("repository") != repo_name or reviewer.get("revision") != revision:
            findings.append("reviewer evidence must bind the assessed repository and exact revision")
        if reviewer.get("state") != "APPROVED":
            findings.append("reviewer state must be APPROVED")
        prepared = document.get("prepared_by", [])
        prepared_ids = {
            (item.get("provider"), item.get("id"))
            for item in prepared
            if isinstance(item, Mapping)
        } if isinstance(prepared, list) else set()
        if (reviewer.get("provider"), reviewer.get("id")) in prepared_ids:
            findings.append("reviewer must be independent from prepared_by identities")
        if token and isinstance(repo_name, str) and isinstance(reviewer.get("pull_request"), int) and isinstance(reviewer.get("review_id"), int):
            try:
                review = _github_json(
                    f"https://api.github.com/repos/{repo_name}/pulls/{reviewer['pull_request']}/reviews/{reviewer['review_id']}",
                    token,
                )
                user = review.get("user", {})
                if review.get("state") != "APPROVED" or review.get("commit_id") != revision:
                    findings.append("provider review is not APPROVED for the exact assessed revision")
                if user.get("id") != reviewer.get("id") or user.get("login") != reviewer.get("login"):
                    findings.append("provider reviewer identity does not match decision.reviewer")
            except ValueError as exc:
                findings.append(str(exc))
    return findings


def _placeholder_findings(document: Any, *, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(document, str) and PLACEHOLDER_RE.search(document):
        findings.append(f"unresolved placeholder at {path}")
    elif isinstance(document, Mapping):
        for key, value in document.items():
            findings.extend(_placeholder_findings(value, path=f"{path}.{key}"))
    elif isinstance(document, list):
        for index, value in enumerate(document):
            findings.extend(_placeholder_findings(value, path=f"{path}[{index}]"))
    return findings


def validate_adoption(path: Path, *, require_approval: bool = False) -> list[str]:
    """Return fail-closed structural, applicability, evidence, and decision findings."""
    try:
        document = _load_yaml(path)
    except ValueError as exc:
        return [str(exc)]
    if not isinstance(document, Mapping):
        return ["assessment root must be a mapping"]
    findings = _schema_findings(document)
    if findings:
        return findings

    approval = require_approval or document.get("decision", {}).get("status") == "approve"
    context, context_findings = _rule_context(document, approval=approval)
    findings.extend(context_findings)
    try:
        catalog = _catalog()
        findings.extend(_validate_applicability(document, catalog, context))
    except ValueError as exc:
        findings.append(str(exc))
    findings.extend(_validate_revisions(document))
    findings.extend(_validate_transport_results(document))

    mode = document.get("verification_mode")
    token = os.environ.get("GITHUB_TOKEN")
    if mode == "provider-backed":
        if not token:
            findings.append("provider-backed verification requires GITHUB_TOKEN")
        else:
            findings.extend(_validate_provider(document, token))
    findings.extend(_validate_decision(document, require_approval=require_approval, token=token))

    decision = document.get("decision", {})
    if isinstance(decision, Mapping) and decision.get("status") == "approve":
        findings.extend(_placeholder_findings(document))
        risks = document.get("residual_risks", [])
        if isinstance(risks, list):
            for risk in risks:
                if isinstance(risk, Mapping) and risk.get("blocking") is True:
                    findings.append("approved assessment contains a blocking residual risk")
    return sorted(set(findings))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assessment", type=Path)
    parser.add_argument("--require-approval", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    findings = validate_adoption(args.assessment, require_approval=args.require_approval)
    if findings:
        for finding in findings:
            print(finding, file=sys.stderr)
        return 1
    print(f"validated adoption assessment: {args.assessment}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

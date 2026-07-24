#!/usr/bin/env python3
"""Validate one completed repository-wide skill adoption assessment."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.semver import is_semver
DEFAULT_CATALOG = Path(__file__).with_name("rule-catalog.yaml")
DEFAULT_SKILLS = ROOT / "skills"
FULL_SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
PLACEHOLDER = re.compile(
    r"(?:replace(?:-with|-me)?|full-immutable|yyyy-mm-dd|not-run|not-tested|todo|tbd|example\.invalid)",
    re.IGNORECASE,
)
ALLOWED_STATUSES = {"applicable", "not-applicable", "deferred"}
ALLOWED_DECISIONS = {"approve", "request-changes", "rejected"}
ALLOWED_RESULTS = {"passed", "failed", "not-run"}
MCP_TRANSPORTS = {"stdio", "streamable_http"}


@dataclass(frozen=True, slots=True)
class Finding:
    """One deterministic assessment validation finding."""

    location: str
    message: str

    def __str__(self) -> str:
        return f"{self.location}: {self.message}"


def _mapping(value: object, location: str, findings: list[Finding]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        findings.append(Finding(location, "must be an object"))
        return {}
    return value


def _sequence(value: object, location: str, findings: list[Finding]) -> Sequence[Any]:
    if not isinstance(value, list):
        findings.append(Finding(location, "must be a list"))
        return []
    return value


def _text(value: object, location: str, findings: list[Finding], *, allow_placeholder: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        findings.append(Finding(location, "must be a non-empty string"))
        return ""
    normalized = value.strip()
    if not allow_placeholder and PLACEHOLDER.search(normalized):
        findings.append(Finding(location, "must not contain a placeholder value"))
    return normalized


def _text_list(value: object, location: str, findings: list[Finding], *, nonempty: bool = False) -> list[str]:
    values = _sequence(value, location, findings)
    result: list[str] = []
    for index, item in enumerate(values):
        result.append(_text(item, f"{location}[{index}]", findings))
    if nonempty and not result:
        findings.append(Finding(location, "must contain at least one value"))
    return result


def _iso_datetime(value: object, location: str, findings: list[Finding]) -> datetime | None:
    text = _text(value, location, findings)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        findings.append(Finding(location, "must be an ISO-8601 date-time"))
        return None
    if parsed.tzinfo is None:
        findings.append(Finding(location, "must include a timezone"))
        return None
    return parsed.astimezone(UTC)


def _date(value: object, location: str, findings: list[Finding]) -> date | None:
    text = _text(value, location, findings)
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        findings.append(Finding(location, "must be an ISO-8601 date"))
        return None


def _load_yaml(path: Path) -> Mapping[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError(f"{path} must contain a YAML object")
    return document


def _catalog_rules(catalog: Mapping[str, Any], skill_name: str, findings: list[Finding]) -> set[str]:
    skills = _mapping(catalog.get("skills"), "catalog.skills", findings)
    skill = _mapping(skills.get(skill_name), f"catalog.skills.{skill_name}", findings)
    rules = _sequence(skill.get("rules"), f"catalog.skills.{skill_name}.rules", findings)
    result: set[str] = set()
    for index, raw in enumerate(rules):
        rule = _mapping(raw, f"catalog.skills.{skill_name}.rules[{index}]", findings)
        rule_id = _text(rule.get("id"), f"catalog.skills.{skill_name}.rules[{index}].id", findings)
        if rule_id in result:
            findings.append(Finding(f"catalog.skills.{skill_name}.rules[{index}].id", "duplicates a catalog rule"))
        result.add(rule_id)
    return result


def _manifest(skill_name: str, skills_root: Path, findings: list[Finding]) -> Mapping[str, Any]:
    path = skills_root / skill_name / "manifest.yaml"
    if not path.is_file():
        findings.append(Finding("skill.name", f"unknown skill: {skill_name}"))
        return {}
    try:
        return _load_yaml(path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        findings.append(Finding("skill.name", f"cannot load manifest: {exc}"))
        return {}


def _validate_compatibility(
    assessment: Mapping[str, Any], manifest: Mapping[str, Any], findings: list[Finding]
) -> None:
    claims = _mapping(assessment.get("compatibility_claims"), "compatibility_claims", findings)
    claimed_os = set(_text_list(claims.get("operating_systems"), "compatibility_claims.operating_systems", findings))
    manifest_compatibility = _mapping(manifest.get("compatibility"), "manifest.compatibility", findings)
    supported_os = set(
        _text_list(manifest_compatibility.get("operating_systems"), "manifest.compatibility.operating_systems", findings)
    )
    if not claimed_os:
        findings.append(Finding("compatibility_claims.operating_systems", "must claim at least one target OS"))
    unsupported_os = claimed_os - supported_os
    if unsupported_os:
        findings.append(Finding("compatibility_claims.operating_systems", f"unsupported values: {sorted(unsupported_os)}"))

    claimed_runtimes = _mapping(claims.get("runtimes"), "compatibility_claims.runtimes", findings)
    manifest_runtimes = _mapping(manifest_compatibility.get("runtimes", {}), "manifest.compatibility.runtimes", findings)
    for runtime, raw_versions in claimed_runtimes.items():
        if runtime not in manifest_runtimes:
            findings.append(Finding(f"compatibility_claims.runtimes.{runtime}", "runtime is not declared by the skill"))
        _text_list(raw_versions, f"compatibility_claims.runtimes.{runtime}", findings, nonempty=True)

    results = _sequence(assessment.get("compatibility_results"), "compatibility_results", findings)
    observed_os: set[str] = set()
    observed_runtimes: dict[str, set[str]] = {}
    for index, raw in enumerate(results):
        result = _mapping(raw, f"compatibility_results[{index}]", findings)
        os_name = _text(result.get("operating_system"), f"compatibility_results[{index}].operating_system", findings)
        command = _text(result.get("command"), f"compatibility_results[{index}].command", findings)
        evidence = _text(result.get("evidence"), f"compatibility_results[{index}].evidence", findings)
        outcome = result.get("result")
        if outcome not in ALLOWED_RESULTS:
            findings.append(Finding(f"compatibility_results[{index}].result", f"must be one of {sorted(ALLOWED_RESULTS)}"))
        runtime = result.get("runtime")
        version = result.get("version")
        runtime_text = ""
        version_text = ""
        if runtime is not None or version is not None:
            runtime_text = _text(runtime, f"compatibility_results[{index}].runtime", findings)
            version_text = _text(version, f"compatibility_results[{index}].version", findings)
        if os_name and command and evidence and outcome == "passed":
            observed_os.add(os_name)
            if runtime_text and version_text:
                observed_runtimes.setdefault(runtime_text, set()).add(version_text)

    missing_os = claimed_os - observed_os
    if missing_os:
        findings.append(Finding("compatibility_results", f"missing passed evidence for OS values: {sorted(missing_os)}"))
    for runtime, raw_versions in claimed_runtimes.items():
        expected = set(item for item in raw_versions if isinstance(item, str)) if isinstance(raw_versions, list) else set()
        missing = expected - observed_runtimes.get(str(runtime), set())
        if missing:
            findings.append(Finding("compatibility_results", f"missing passed {runtime} versions: {sorted(missing)}"))


def _validate_applicability(
    assessment: Mapping[str, Any], catalog_rules: set[str], findings: list[Finding], *, as_of: date
) -> None:
    raw_entries = _sequence(assessment.get("applicability"), "applicability", findings)
    entries: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(raw_entries):
        location = f"applicability[{index}]"
        entry = _mapping(raw, location, findings)
        rule_id = _text(entry.get("rule_id"), f"{location}.rule_id", findings)
        if rule_id in entries:
            findings.append(Finding(f"{location}.rule_id", "duplicates another applicability entry"))
        entries[rule_id] = entry
        if rule_id not in catalog_rules:
            findings.append(Finding(f"{location}.rule_id", "does not exist in the stable rule catalog"))
        status = entry.get("status")
        if status not in ALLOWED_STATUSES:
            findings.append(Finding(f"{location}.status", f"must be one of {sorted(ALLOWED_STATUSES)}"))
        _text(entry.get("rationale"), f"{location}.rationale", findings)
        waiver_id = entry.get("waiver_id")
        if status == "applicable":
            implementations = _sequence(entry.get("implementation"), f"{location}.implementation", findings)
            verifications = _sequence(entry.get("verification"), f"{location}.verification", findings)
            if not implementations:
                findings.append(Finding(f"{location}.implementation", "applicable rule needs implementation evidence"))
            if not verifications:
                findings.append(Finding(f"{location}.verification", "applicable rule needs executable verification"))
            for impl_index, raw_impl in enumerate(implementations):
                implementation = _mapping(raw_impl, f"{location}.implementation[{impl_index}]", findings)
                path = _text(implementation.get("path"), f"{location}.implementation[{impl_index}].path", findings)
                _text(implementation.get("symbol"), f"{location}.implementation[{impl_index}].symbol", findings)
                candidate = Path(path)
                if path and (candidate.is_absolute() or ".." in candidate.parts):
                    findings.append(Finding(f"{location}.implementation[{impl_index}].path", "must be repository-relative"))
            for verification_index, raw_verification in enumerate(verifications):
                verification = _mapping(
                    raw_verification, f"{location}.verification[{verification_index}]", findings
                )
                _text(
                    verification.get("command"),
                    f"{location}.verification[{verification_index}].command",
                    findings,
                )
                _text(
                    verification.get("evidence"),
                    f"{location}.verification[{verification_index}].evidence",
                    findings,
                )
                if verification.get("result") != "passed":
                    findings.append(
                        Finding(f"{location}.verification[{verification_index}].result", "must be passed")
                    )
            if waiver_id is not None:
                findings.append(Finding(f"{location}.waiver_id", "applicable rule must not use a waiver"))
        elif status == "not-applicable":
            if waiver_id is not None:
                findings.append(Finding(f"{location}.waiver_id", "not-applicable rule must not use a waiver"))
        elif status == "deferred":
            _text(waiver_id, f"{location}.waiver_id", findings)

    missing = catalog_rules - set(entries)
    if missing:
        findings.append(Finding("applicability", f"missing catalog rules: {sorted(missing)}"))

    waivers = _sequence(assessment.get("waivers"), "waivers", findings)
    by_id: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(waivers):
        location = f"waivers[{index}]"
        waiver = _mapping(raw, location, findings)
        waiver_id = _text(waiver.get("waiver_id"), f"{location}.waiver_id", findings)
        if waiver_id in by_id:
            findings.append(Finding(f"{location}.waiver_id", "duplicates another waiver"))
        by_id[waiver_id] = waiver
        rule_id = _text(waiver.get("rule_id"), f"{location}.rule_id", findings)
        _text(waiver.get("owner"), f"{location}.owner", findings)
        _text(waiver.get("rationale"), f"{location}.rationale", findings)
        _text_list(waiver.get("compensating_controls"), f"{location}.compensating_controls", findings, nonempty=True)
        expiry = _date(waiver.get("expires_at"), f"{location}.expires_at", findings)
        if expiry is not None and expiry < as_of:
            findings.append(Finding(f"{location}.expires_at", f"waiver expired before {as_of.isoformat()}"))
        if rule_id not in catalog_rules:
            findings.append(Finding(f"{location}.rule_id", "does not exist in the stable rule catalog"))

    for rule_id, entry in entries.items():
        if entry.get("status") != "deferred":
            continue
        waiver_id = entry.get("waiver_id")
        waiver = by_id.get(str(waiver_id))
        if waiver is None:
            findings.append(Finding(f"applicability.{rule_id}.waiver_id", "does not reference an existing waiver"))
        elif waiver.get("rule_id") != rule_id:
            findings.append(Finding(f"applicability.{rule_id}.waiver_id", "waiver is bound to another rule"))


def _validate_artifacts(assessment: Mapping[str, Any], revision: str, findings: list[Finding]) -> None:
    verification = _mapping(assessment.get("artifact_verification"), "artifact_verification", findings)
    exact_revision = _text(verification.get("exact_revision"), "artifact_verification.exact_revision", findings)
    if exact_revision and exact_revision != revision:
        findings.append(Finding("artifact_verification.exact_revision", "must equal repository.revision"))
    artifacts = _sequence(verification.get("artifacts"), "artifact_verification.artifacts", findings)
    if not artifacts:
        findings.append(Finding("artifact_verification.artifacts", "must contain at least one exact artifact"))
    for index, raw in enumerate(artifacts):
        location = f"artifact_verification.artifacts[{index}]"
        artifact = _mapping(raw, location, findings)
        _text(artifact.get("kind"), f"{location}.kind", findings)
        _text(artifact.get("identity"), f"{location}.identity", findings)
        digest = _text(artifact.get("digest"), f"{location}.digest", findings)
        if digest and DIGEST.fullmatch(digest) is None:
            findings.append(Finding(f"{location}.digest", "must be a sha256 digest with 64 lowercase hex digits"))
        _text_list(artifact.get("commands"), f"{location}.commands", findings, nonempty=True)
        if artifact.get("result") != "passed":
            findings.append(Finding(f"{location}.result", "must be passed"))


def _validate_mcp_extension(assessment: Mapping[str, Any], skill_name: str, findings: list[Finding]) -> None:
    if skill_name != "mcp-server-architect":
        return
    extensions = _mapping(assessment.get("extensions"), "extensions", findings)
    mcp = _mapping(extensions.get("mcp"), "extensions.mcp", findings)
    if mcp.get("target_level") not in {"L1", "L2", "L3", "L4"}:
        findings.append(Finding("extensions.mcp.target_level", "must be L1, L2, L3, or L4"))
    _text_list(mcp.get("profiles"), "extensions.mcp.profiles", findings, nonempty=True)
    advertised = set(_text_list(mcp.get("advertised_transports"), "extensions.mcp.advertised_transports", findings, nonempty=True))
    unknown = advertised - MCP_TRANSPORTS
    if unknown:
        findings.append(Finding("extensions.mcp.advertised_transports", f"unsupported transports: {sorted(unknown)}"))
    _text_list(mcp.get("official_client_commands"), "extensions.mcp.official_client_commands", findings, nonempty=True)
    results = _mapping(mcp.get("transport_results"), "extensions.mcp.transport_results", findings)
    for transport in advertised:
        result = _mapping(results.get(transport), f"extensions.mcp.transport_results.{transport}", findings)
        for field in ("capability_listing", "representative_read", "failure_path", "write_boundary"):
            check = _mapping(
                result.get(field),
                f"extensions.mcp.transport_results.{transport}.{field}",
                findings,
            )
            if check.get("result") not in {"passed", "not-applicable"}:
                findings.append(
                    Finding(
                        f"extensions.mcp.transport_results.{transport}.{field}.result",
                        "must be passed or explicitly not-applicable",
                    )
                )
            _text(
                check.get("evidence"),
                f"extensions.mcp.transport_results.{transport}.{field}.evidence",
                findings,
            )


def validate_document(
    assessment: Mapping[str, Any],
    catalog: Mapping[str, Any],
    skills_root: Path,
    *,
    require_approval: bool,
    as_of: date,
) -> list[Finding]:
    """Return every semantic or structural contract violation."""
    findings: list[Finding] = []
    if assessment.get("schema_version") != 1:
        findings.append(Finding("schema_version", "must equal 1"))
    _text(assessment.get("assessment_id"), "assessment_id", findings)
    _iso_datetime(assessment.get("generated_at"), "generated_at", findings)
    prepared_by = _text_list(assessment.get("prepared_by"), "prepared_by", findings, nonempty=True)

    repository = _mapping(assessment.get("repository"), "repository", findings)
    _text(repository.get("name"), "repository.name", findings)
    revision = _text(repository.get("revision"), "repository.revision", findings)
    if revision and FULL_SHA.fullmatch(revision) is None:
        findings.append(Finding("repository.revision", "must be a full lowercase 40-character commit SHA"))
    _text(repository.get("source_branch"), "repository.source_branch", findings)

    skill = _mapping(assessment.get("skill"), "skill", findings)
    skill_name = _text(skill.get("name"), "skill.name", findings)
    skill_version = _text(skill.get("version"), "skill.version", findings)
    if skill_version and not is_semver(skill_version):
        findings.append(Finding("skill.version", "must be canonical SemVer 2.0.0"))
    skill_maturity = _text(skill.get("maturity"), "skill.maturity", findings)
    manifest = _manifest(skill_name, skills_root, findings) if skill_name else {}
    if manifest:
        if skill_version != manifest.get("version"):
            findings.append(Finding("skill.version", "must equal the selected skill manifest version"))
        if skill_maturity != manifest.get("maturity"):
            findings.append(Finding("skill.maturity", "must equal the selected skill manifest maturity"))

    scope = _mapping(assessment.get("scope"), "scope", findings)
    _text_list(scope.get("included"), "scope.included", findings, nonempty=True)
    _text_list(scope.get("excluded"), "scope.excluded", findings)
    _text_list(scope.get("exclusion_rationale"), "scope.exclusion_rationale", findings)

    catalog_rules = _catalog_rules(catalog, skill_name, findings) if skill_name else set()
    _validate_applicability(assessment, catalog_rules, findings, as_of=as_of)
    _validate_compatibility(assessment, manifest, findings)
    _validate_artifacts(assessment, revision, findings)
    _validate_mcp_extension(assessment, skill_name, findings)

    behavior = _mapping(assessment.get("behavior"), "behavior", findings)
    _text_list(behavior.get("preserved"), "behavior.preserved", findings, nonempty=True)
    _text_list(behavior.get("intentionally_changed"), "behavior.intentionally_changed", findings)
    _text_list(behavior.get("removed_legacy"), "behavior.removed_legacy", findings)

    rollback = _mapping(assessment.get("rollback"), "rollback", findings)
    _text_list(rollback.get("trigger_conditions"), "rollback.trigger_conditions", findings, nonempty=True)
    _text_list(rollback.get("procedure"), "rollback.procedure", findings, nonempty=True)
    _text_list(rollback.get("data_recovery"), "rollback.data_recovery", findings, nonempty=True)

    risks = _sequence(assessment.get("residual_risks"), "residual_risks", findings)
    for index, raw in enumerate(risks):
        location = f"residual_risks[{index}]"
        risk = _mapping(raw, location, findings)
        _text(risk.get("risk"), f"{location}.risk", findings)
        _text(risk.get("owner"), f"{location}.owner", findings)
        _text(risk.get("mitigation"), f"{location}.mitigation", findings)
        if risk.get("blocking") not in {True, False}:
            findings.append(Finding(f"{location}.blocking", "must be a boolean"))

    decision = _mapping(assessment.get("decision"), "decision", findings)
    status = decision.get("status")
    if status not in ALLOWED_DECISIONS:
        findings.append(Finding("decision.status", f"must be one of {sorted(ALLOWED_DECISIONS)}"))
    _text(decision.get("rationale"), "decision.rationale", findings)
    reviewer = _text(decision.get("reviewer"), "decision.reviewer", findings)
    if reviewer in prepared_by:
        findings.append(Finding("decision.reviewer", "must be independent from every prepared_by identity"))
    if require_approval and status != "approve":
        findings.append(Finding("decision.status", "must be approve for an acceptance gate"))
    if status == "approve" and any(isinstance(risk, Mapping) and risk.get("blocking") is True for risk in risks):
        findings.append(Finding("decision.status", "cannot approve while a blocking residual risk remains"))

    return sorted(findings, key=lambda finding: (finding.location, finding.message))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assessment", type=Path)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--skills-root", type=Path, default=DEFAULT_SKILLS)
    parser.add_argument("--require-approval", action="store_true")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        assessment = _load_yaml(args.assessment)
        catalog = _load_yaml(args.catalog)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(exc, file=sys.stderr)
        return 2
    findings = validate_document(
        assessment,
        catalog,
        args.skills_root,
        require_approval=args.require_approval,
        as_of=args.as_of,
    )
    for finding in findings:
        print(finding, file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate one completed repository-wide skill adoption assessment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.evidence import EvidenceVerifier, GitHubEvidenceVerifier  # noqa: E402
from contracts.semver import is_semver  # noqa: E402

DEFAULT_CATALOG = Path(__file__).with_name("rule-catalog.yaml")
DEFAULT_SCHEMA = Path(__file__).with_name("adoption-assessment.schema.json")
DEFAULT_SKILLS = ROOT / "skills"
FULL_SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
WORKFLOW_PATH = re.compile(r"[.]github/workflows/[A-Za-z0-9._/-]+[.]ya?ml")
PLACEHOLDER = re.compile(
    r"(?:replace(?:-with|-me)?|full-immutable|yyyy-mm-dd|not-run|not-tested|todo|tbd|example[.]invalid)",
    re.IGNORECASE,
)
ALLOWED_STATUSES = {"applicable", "not-applicable", "deferred"}
ALLOWED_DECISIONS = {"approve", "request-changes", "rejected"}
ALLOWED_RESULTS = {"passed", "failed", "not-run"}
MCP_TRANSPORTS = {"stdio", "streamable_http"}
VERIFICATION_MODES = {"structural-attestation", "provider-backed"}
ACTION_EVENTS = {"pull_request", "push", "workflow_dispatch", "workflow_run"}
FILE_READ_CHUNK_BYTES = 1024 * 1024


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


def _text(
    value: object,
    location: str,
    findings: list[Finding],
    *,
    allow_placeholder: bool = False,
) -> str:
    if not isinstance(value, str) or not value.strip():
        findings.append(Finding(location, "must be a non-empty string"))
        return ""
    normalized = value.strip()
    if not allow_placeholder and PLACEHOLDER.search(normalized):
        findings.append(Finding(location, "must not contain a placeholder value"))
    return normalized


def _text_list(
    value: object,
    location: str,
    findings: list[Finding],
    *,
    nonempty: bool = False,
) -> list[str]:
    values = _sequence(value, location, findings)
    result = [_text(item, f"{location}[{index}]", findings) for index, item in enumerate(values)]
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


def _load_json(path: Path) -> Mapping[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError(f"{path} must contain a JSON object")
    return document


def _schema_findings(assessment: Mapping[str, Any], schema: Mapping[str, Any]) -> list[Finding]:
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    findings: list[Finding] = []
    for error in validator.iter_errors(assessment):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        findings.append(Finding(location, f"schema violation: {error.message}"))
    return findings


def _catalog_rules(catalog: Mapping[str, Any], skill_name: str, findings: list[Finding]) -> set[str]:
    skills = _mapping(catalog.get("skills"), "catalog.skills", findings)
    skill = _mapping(skills.get(skill_name), f"catalog.skills.{skill_name}", findings)
    rules = _sequence(skill.get("rules"), f"catalog.skills.{skill_name}.rules", findings)
    result: set[str] = set()
    for index, raw in enumerate(rules):
        location = f"catalog.skills.{skill_name}.rules[{index}]"
        rule = _mapping(raw, location, findings)
        rule_id = _text(rule.get("id"), f"{location}.id", findings)
        _text(rule.get("source"), f"{location}.source", findings)
        _text(rule.get("description"), f"{location}.description", findings)
        if rule_id in result:
            findings.append(Finding(f"{location}.id", "duplicates a catalog rule"))
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


def _identity(value: object, location: str, findings: list[Finding]) -> tuple[str, int, str]:
    identity = _mapping(value, location, findings)
    provider = _text(identity.get("provider"), f"{location}.provider", findings)
    login = _text(identity.get("login"), f"{location}.login", findings)
    raw_id = identity.get("id")
    if type(raw_id) is not int or raw_id <= 0:
        findings.append(Finding(f"{location}.id", "must be a positive integer"))
        numeric_id = 0
    else:
        numeric_id = raw_id
    return provider.casefold(), numeric_id, login.casefold()


def _positive_int(value: object, location: str, findings: list[Finding]) -> int:
    if type(value) is not int or value <= 0:
        findings.append(Finding(location, "must be a positive integer"))
        return 0
    return value


def _evidence_reference(
    value: object,
    location: str,
    findings: list[Finding],
    *,
    repository: str,
    revision: str,
) -> Mapping[str, Any]:
    evidence = _mapping(value, location, findings)
    if _text(evidence.get("provider"), f"{location}.provider", findings) != "github-actions":
        findings.append(Finding(f"{location}.provider", "must be github-actions"))
    evidence_repository = _text(evidence.get("repository"), f"{location}.repository", findings)
    if evidence_repository and repository and evidence_repository != repository:
        findings.append(Finding(f"{location}.repository", "must equal repository.name"))
    evidence_revision = _text(evidence.get("revision"), f"{location}.revision", findings)
    if evidence_revision and revision and evidence_revision != revision:
        findings.append(Finding(f"{location}.revision", "must equal repository.revision"))
    for field in ("run_id", "job_id", "check_run_id", "workflow_id", "artifact_id"):
        _positive_int(evidence.get(field), f"{location}.{field}", findings)
    workflow_path = _text(evidence.get("workflow_path"), f"{location}.workflow_path", findings)
    if workflow_path and WORKFLOW_PATH.fullmatch(workflow_path) is None:
        findings.append(Finding(f"{location}.workflow_path", "must identify a .github/workflows YAML file"))
    for field in ("workflow_name", "job_name", "lane", "artifact_name", "report_path"):
        _text(evidence.get(field), f"{location}.{field}", findings)
    event = _text(evidence.get("event"), f"{location}.event", findings)
    if event and event not in ACTION_EVENTS:
        findings.append(Finding(f"{location}.event", f"must be one of {sorted(ACTION_EVENTS)}"))
    report_path = evidence.get("report_path")
    if isinstance(report_path, str) and (
        report_path.startswith(("/", "\\"))
        or "\\" in report_path
        or any(part in {"", ".", ".."} for part in report_path.split("/"))
    ):
        findings.append(Finding(f"{location}.report_path", "must be a safe relative POSIX path"))
    for field in ("provider_digest", "report_digest"):
        digest = _text(evidence.get(field), f"{location}.{field}", findings)
        if digest and DIGEST.fullmatch(digest) is None:
            findings.append(
                Finding(
                    f"{location}.{field}",
                    "must be a sha256 digest with 64 lowercase hex digits",
                )
            )
    return evidence


def _acceptance_authority(
    value: object,
    location: str,
    findings: list[Finding],
    *,
    assessed_repository: str,
) -> dict[str, str]:
    """Validate immutable external authority coordinates for final acceptance."""
    authority = _mapping(value, location, findings)
    result: dict[str, str] = {}
    for field in ("verifier_repository", "claim_catalog_repository"):
        text = _text(authority.get(field), f"{location}.{field}", findings)
        if text and assessed_repository and text == assessed_repository:
            findings.append(Finding(f"{location}.{field}", "must be external to the assessed repository"))
        result[field] = text
    for field in ("verifier_revision", "claim_catalog_revision"):
        text = _text(authority.get(field), f"{location}.{field}", findings)
        if text and FULL_SHA.fullmatch(text) is None:
            findings.append(Finding(f"{location}.{field}", "must be a full immutable commit SHA"))
        result[field] = text
    workflow_path = _text(authority.get("workflow_path"), f"{location}.workflow_path", findings)
    if workflow_path and WORKFLOW_PATH.fullmatch(workflow_path) is None:
        findings.append(Finding(f"{location}.workflow_path", "must identify a GitHub workflow YAML file"))
    result["workflow_path"] = workflow_path
    return result


def _provider_findings(location: str, messages: Sequence[str], findings: list[Finding]) -> None:
    for message in messages:
        findings.append(Finding(location, f"provider verification failed: {message}"))


def _command_digest(command: str) -> str:
    return f"sha256:{hashlib.sha256(command.encode('utf-8')).hexdigest()}"


def _commands_digest(commands: Sequence[str]) -> str:
    encoded = json.dumps(list(commands), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _with_claim(evidence: Mapping[str, Any], claim: Mapping[str, Any]) -> Mapping[str, Any]:
    enriched = dict(evidence)
    enriched["_expected_claim"] = dict(claim)
    return enriched


def _combination(value: object, location: str, findings: list[Finding]) -> tuple[str, str, str, str, str]:
    combination = _mapping(value, location, findings)
    return (
        _text(combination.get("operating_system"), f"{location}.operating_system", findings),
        _text(combination.get("architecture"), f"{location}.architecture", findings),
        _text(combination.get("runtime"), f"{location}.runtime", findings),
        _text(combination.get("version"), f"{location}.version", findings),
        _text(combination.get("lane"), f"{location}.lane", findings),
    )


def _combination_object(combination: tuple[str, str, str, str, str]) -> dict[str, str]:
    operating_system, architecture, runtime, version, lane = combination
    return {
        "operating_system": operating_system,
        "architecture": architecture,
        "runtime": runtime,
        "version": version,
        "lane": lane,
    }


def _validate_compatibility(
    assessment: Mapping[str, Any],
    manifest: Mapping[str, Any],
    findings: list[Finding],
    *,
    repository: str,
    revision: str,
    verifier: EvidenceVerifier | None,
) -> None:
    claims = _mapping(assessment.get("compatibility_claims"), "compatibility_claims", findings)
    raw_claims = _sequence(claims.get("combinations"), "compatibility_claims.combinations", findings)
    claimed = {
        _combination(raw, f"compatibility_claims.combinations[{index}]", findings)
        for index, raw in enumerate(raw_claims)
    }
    if not claimed:
        findings.append(Finding("compatibility_claims.combinations", "must claim at least one combination"))
    manifest_compatibility = _mapping(manifest.get("compatibility"), "manifest.compatibility", findings)
    raw_supported = _sequence(
        manifest_compatibility.get("tested_combinations"),
        "manifest.compatibility.tested_combinations",
        findings,
    )
    supported = {
        _combination(raw, f"manifest.compatibility.tested_combinations[{index}]", findings)
        for index, raw in enumerate(raw_supported)
    }
    unsupported = claimed - supported
    if unsupported:
        findings.append(
            Finding(
                "compatibility_claims.combinations",
                f"unsupported combinations: {sorted(unsupported)}",
            )
        )

    raw_results = _sequence(assessment.get("compatibility_results"), "compatibility_results", findings)
    passed: set[tuple[str, str, str, str, str]] = set()
    for index, raw in enumerate(raw_results):
        location = f"compatibility_results[{index}]"
        result = _mapping(raw, location, findings)
        combination = _combination(result, location, findings)
        command = _text(result.get("command"), f"{location}.command", findings)
        evidence = _evidence_reference(
            result.get("evidence"),
            f"{location}.evidence",
            findings,
            repository=repository,
            revision=revision,
        )
        outcome = result.get("result")
        if outcome not in ALLOWED_RESULTS:
            findings.append(Finding(f"{location}.result", f"must be one of {sorted(ALLOWED_RESULTS)}"))
        if str(evidence.get("lane") or "") != combination[4]:
            findings.append(Finding(f"{location}.evidence.lane", "must equal the claimed compatibility lane"))
        if outcome == "passed":
            passed.add(combination)
            if verifier is not None:
                subject = "|".join(combination)
                claim = {
                    "kind": "compatibility",
                    "subject": subject,
                    "result": "passed",
                    "command_digest": _command_digest(command),
                    "combination": _combination_object(combination),
                }
                _provider_findings(
                    f"{location}.evidence",
                    verifier.verify_action(_with_claim(evidence, claim), revision),
                    findings,
                )
    missing = claimed - passed
    if missing:
        findings.append(
            Finding(
                "compatibility_results",
                f"missing passed evidence for combinations: {sorted(missing)}",
            )
        )


def _safe_repository_path(repository_root: Path, raw_path: str) -> Path | None:
    candidate = Path(raw_path)
    if not raw_path or candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        return None
    try:
        root = repository_root.resolve(strict=True)
    except OSError:
        return None
    current = root
    for part in candidate.parts:
        current = current / part
        if os.path.lexists(current):
            try:
                mode = current.lstat().st_mode
            except OSError:
                return None
            if stat.S_ISLNK(mode):
                return None
    try:
        current.resolve(strict=False).relative_to(root)
    except (OSError, ValueError):
        return None
    return current


def _validate_implementation(
    implementation: Mapping[str, Any],
    location: str,
    findings: list[Finding],
    *,
    repository_root: Path,
) -> None:
    path_text = _text(implementation.get("path"), f"{location}.path", findings)
    symbol = _text(implementation.get("symbol"), f"{location}.symbol", findings)
    candidate = _safe_repository_path(repository_root, path_text) if path_text else None
    if candidate is None:
        findings.append(Finding(f"{location}.path", "must be a repository-relative path without symlinks"))
        return
    if not candidate.is_file():
        findings.append(Finding(f"{location}.path", "does not identify an existing file"))
        return
    if symbol:
        try:
            content = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            findings.append(Finding(f"{location}.symbol", "cannot verify a symbol in a non-text implementation"))
        else:
            if symbol not in content:
                findings.append(Finding(f"{location}.symbol", "was not found in the implementation file"))


def _validate_applicability(
    assessment: Mapping[str, Any],
    catalog_rules: set[str],
    findings: list[Finding],
    *,
    as_of: date,
    repository: str,
    revision: str,
    repository_root: Path,
    verifier: EvidenceVerifier | None,
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
        status_value = entry.get("status")
        if status_value not in ALLOWED_STATUSES:
            findings.append(Finding(f"{location}.status", f"must be one of {sorted(ALLOWED_STATUSES)}"))
        _text(entry.get("rationale"), f"{location}.rationale", findings)
        waiver_id = entry.get("waiver_id")
        if status_value == "applicable":
            implementations = _sequence(entry.get("implementation"), f"{location}.implementation", findings)
            verifications = _sequence(entry.get("verification"), f"{location}.verification", findings)
            if not implementations:
                findings.append(Finding(f"{location}.implementation", "applicable rule needs implementation evidence"))
            if not verifications:
                findings.append(Finding(f"{location}.verification", "applicable rule needs executable verification"))
            for impl_index, raw_impl in enumerate(implementations):
                impl_location = f"{location}.implementation[{impl_index}]"
                _validate_implementation(
                    _mapping(raw_impl, impl_location, findings),
                    impl_location,
                    findings,
                    repository_root=repository_root,
                )
            for verification_index, raw_verification in enumerate(verifications):
                verification_location = f"{location}.verification[{verification_index}]"
                verification = _mapping(raw_verification, verification_location, findings)
                command = _text(verification.get("command"), f"{verification_location}.command", findings)
                evidence = _evidence_reference(
                    verification.get("evidence"),
                    f"{verification_location}.evidence",
                    findings,
                    repository=repository,
                    revision=revision,
                )
                if verification.get("result") != "passed":
                    findings.append(Finding(f"{verification_location}.result", "must be passed"))
                elif verifier is not None:
                    claim = {
                        "kind": "rule",
                        "subject": rule_id,
                        "result": "passed",
                        "command_digest": _command_digest(command),
                    }
                    _provider_findings(
                        f"{verification_location}.evidence",
                        verifier.verify_action(_with_claim(evidence, claim), revision),
                        findings,
                    )
            if waiver_id is not None:
                findings.append(Finding(f"{location}.waiver_id", "applicable rule must not use a waiver"))
        elif status_value == "not-applicable":
            if waiver_id is not None:
                findings.append(Finding(f"{location}.waiver_id", "not-applicable rule must not use a waiver"))
        elif status_value == "deferred":
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
        _text_list(
            waiver.get("compensating_controls"),
            f"{location}.compensating_controls",
            findings,
            nonempty=True,
        )
        expiry = _date(waiver.get("expires_at"), f"{location}.expires_at", findings)
        if expiry is not None and expiry < as_of:
            findings.append(Finding(f"{location}.expires_at", f"waiver expired before {as_of.isoformat()}"))
        if rule_id not in catalog_rules:
            findings.append(Finding(f"{location}.rule_id", "does not exist in the stable rule catalog"))

    for rule_id, entry in entries.items():
        if entry.get("status") != "deferred":
            continue
        waiver_id = entry.get("waiver_id")
        linked_waiver = by_id.get(str(waiver_id))
        if linked_waiver is None:
            findings.append(Finding(f"applicability.{rule_id}.waiver_id", "does not reference an existing waiver"))
        elif linked_waiver.get("rule_id") != rule_id:
            findings.append(Finding(f"applicability.{rule_id}.waiver_id", "waiver is bound to another rule"))


def _update_digest_from_regular_file(
    digest: Any,
    path: Path,
    *,
    include_size: bool,
) -> None:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("artifact path must be a regular file")
        if include_size:
            digest.update(metadata.st_size.to_bytes(8, "big"))
        while chunk := os.read(descriptor, FILE_READ_CHUNK_BYTES):
            digest.update(chunk)
    finally:
        os.close(descriptor)


def _tree_digest(path: Path) -> str:
    root_mode = path.lstat().st_mode
    if stat.S_ISLNK(root_mode) or not stat.S_ISDIR(root_mode):
        raise ValueError("artifact directory must be a real directory")
    digest = hashlib.sha256()
    for current_root, directory_names, file_names in os.walk(path, topdown=True, followlinks=False):
        directory_names[:] = sorted(directory_names)
        current = Path(current_root)
        for name in list(directory_names):
            child = current / name
            mode = child.lstat().st_mode
            relative = child.relative_to(path).as_posix()
            if stat.S_ISLNK(mode):
                raise ValueError(f"artifact tree contains symlink: {relative}")
            if not stat.S_ISDIR(mode):
                raise ValueError(f"artifact tree contains a non-directory entry: {relative}")
            relative_bytes = relative.encode("utf-8")
            digest.update(b"D")
            digest.update(len(relative_bytes).to_bytes(8, "big"))
            digest.update(relative_bytes)
        for name in sorted(file_names):
            child = current / name
            mode = child.lstat().st_mode
            relative = child.relative_to(path).as_posix()
            if stat.S_ISLNK(mode):
                raise ValueError(f"artifact tree contains symlink: {relative}")
            if not stat.S_ISREG(mode):
                raise ValueError(f"artifact tree contains a non-regular file: {relative}")
            relative_bytes = relative.encode("utf-8")
            digest.update(b"F")
            digest.update(len(relative_bytes).to_bytes(8, "big"))
            digest.update(relative_bytes)
            _update_digest_from_regular_file(digest, child, include_size=True)
    return f"sha256:{digest.hexdigest()}"


def _path_digest(path: Path) -> str:
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        raise ValueError("artifact path must not be a symlink")
    if stat.S_ISDIR(mode):
        return _tree_digest(path)
    if not stat.S_ISREG(mode):
        raise ValueError("artifact path must be a regular file or directory")
    digest = hashlib.sha256()
    _update_digest_from_regular_file(digest, path, include_size=False)
    return f"sha256:{digest.hexdigest()}"


def _validate_artifacts(
    assessment: Mapping[str, Any],
    revision: str,
    findings: list[Finding],
    *,
    repository: str,
    repository_root: Path,
    verifier: EvidenceVerifier | None,
) -> None:
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
        identity = _text(artifact.get("identity"), f"{location}.identity", findings)
        path_text = _text(artifact.get("path"), f"{location}.path", findings)
        digest = _text(artifact.get("digest"), f"{location}.digest", findings)
        if digest and DIGEST.fullmatch(digest) is None:
            findings.append(Finding(f"{location}.digest", "must be a sha256 digest with 64 lowercase hex digits"))
        commands = _text_list(artifact.get("commands"), f"{location}.commands", findings, nonempty=True)
        evidence = _evidence_reference(
            artifact.get("evidence"),
            f"{location}.evidence",
            findings,
            repository=repository,
            revision=revision,
        )
        provider_digest = str(evidence.get("provider_digest") or "")
        if artifact.get("result") != "passed":
            findings.append(Finding(f"{location}.result", "must be passed"))

        candidate = _safe_repository_path(repository_root, path_text) if path_text else None
        if candidate is None:
            findings.append(Finding(f"{location}.path", "must be a repository-relative path without symlinks"))
        elif not os.path.lexists(candidate):
            findings.append(Finding(f"{location}.path", "must identify an existing non-symlink artifact"))
        elif digest and DIGEST.fullmatch(digest) is not None:
            try:
                observed = _path_digest(candidate)
            except (OSError, ValueError) as exc:
                findings.append(Finding(f"{location}.path", f"cannot read artifact safely: {exc}"))
            else:
                if observed != digest:
                    findings.append(Finding(f"{location}.digest", "does not match the artifact at path"))

        if artifact.get("result") == "passed" and verifier is not None and provider_digest:
            claim = {
                "kind": "artifact",
                "subject": identity,
                "result": "passed",
                "content_digest": digest,
                "commands_digest": _commands_digest(commands),
            }
            _provider_findings(
                f"{location}.evidence",
                verifier.verify_artifact(_with_claim(evidence, claim), revision, provider_digest),
                findings,
            )


def _validate_mcp_extension(
    assessment: Mapping[str, Any],
    skill_name: str,
    findings: list[Finding],
    *,
    repository: str,
    revision: str,
    verifier: EvidenceVerifier | None,
) -> None:
    if skill_name != "mcp-server-architect":
        return
    extensions = _mapping(assessment.get("extensions"), "extensions", findings)
    mcp = _mapping(extensions.get("mcp"), "extensions.mcp", findings)
    if mcp.get("target_level") not in {"L1", "L2", "L3", "L4"}:
        findings.append(Finding("extensions.mcp.target_level", "must be L1, L2, L3, or L4"))
    _text_list(mcp.get("profiles"), "extensions.mcp.profiles", findings, nonempty=True)
    advertised = set(
        _text_list(
            mcp.get("advertised_transports"),
            "extensions.mcp.advertised_transports",
            findings,
            nonempty=True,
        )
    )
    unknown = advertised - MCP_TRANSPORTS
    if unknown:
        findings.append(Finding("extensions.mcp.advertised_transports", f"unsupported transports: {sorted(unknown)}"))
    _text_list(
        mcp.get("official_client_commands"),
        "extensions.mcp.official_client_commands",
        findings,
        nonempty=True,
    )
    results = _mapping(mcp.get("transport_results"), "extensions.mcp.transport_results", findings)
    for transport in advertised:
        result = _mapping(results.get(transport), f"extensions.mcp.transport_results.{transport}", findings)
        for field in ("capability_listing", "representative_read", "failure_path", "write_boundary"):
            location = f"extensions.mcp.transport_results.{transport}.{field}"
            check = _mapping(result.get(field), location, findings)
            if check.get("result") not in {"passed", "not-applicable"}:
                findings.append(Finding(f"{location}.result", "must be passed or explicitly not-applicable"))
            if check.get("result") == "passed":
                evidence = _evidence_reference(
                    check.get("evidence"),
                    f"{location}.evidence",
                    findings,
                    repository=repository,
                    revision=revision,
                )
                if verifier is not None:
                    claim = {
                        "kind": "transport",
                        "subject": f"{transport}:{field}",
                        "result": "passed",
                    }
                    _provider_findings(
                        f"{location}.evidence",
                        verifier.verify_action(_with_claim(evidence, claim), revision),
                        findings,
                    )
            elif check.get("result") == "not-applicable" and check.get("evidence") is not None:
                findings.append(Finding(f"{location}.evidence", "must be null when result is not-applicable"))


def validate_document(
    assessment: Mapping[str, Any],
    catalog: Mapping[str, Any],
    skills_root: Path,
    *,
    require_approval: bool,
    as_of: date,
    schema: Mapping[str, Any] | None = None,
    repository_root: Path = ROOT,
    evidence_verifier: EvidenceVerifier | None = None,
) -> list[Finding]:
    """Return every schema, semantic, local-artifact, and provider violation."""
    effective_schema = schema if schema is not None else _load_json(DEFAULT_SCHEMA)
    findings = _schema_findings(assessment, effective_schema)

    if assessment.get("schema_version") != 1:
        findings.append(Finding("schema_version", "must equal 1"))
    mode = _text(assessment.get("verification_mode"), "verification_mode", findings)
    if mode not in VERIFICATION_MODES:
        findings.append(Finding("verification_mode", f"must be one of {sorted(VERIFICATION_MODES)}"))
    _text(assessment.get("assessment_id"), "assessment_id", findings)
    _iso_datetime(assessment.get("generated_at"), "generated_at", findings)

    raw_prepared = _sequence(assessment.get("prepared_by"), "prepared_by", findings)
    prepared = {_identity(value, f"prepared_by[{index}]", findings) for index, value in enumerate(raw_prepared)}
    if not prepared:
        findings.append(Finding("prepared_by", "must contain at least one canonical identity"))

    repository_value = _mapping(assessment.get("repository"), "repository", findings)
    repository = _text(repository_value.get("name"), "repository.name", findings)
    revision = _text(repository_value.get("revision"), "repository.revision", findings)
    if revision and FULL_SHA.fullmatch(revision) is None:
        findings.append(Finding("repository.revision", "must be a full lowercase 40-character commit SHA"))
    _text(repository_value.get("source_branch"), "repository.source_branch", findings)

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

    decision = _mapping(assessment.get("decision"), "decision", findings)
    decision_status = decision.get("status")
    if decision_status not in ALLOWED_DECISIONS:
        findings.append(Finding("decision.status", f"must be one of {sorted(ALLOWED_DECISIONS)}"))
    approval_gate = require_approval or decision_status == "approve"
    if approval_gate and mode != "provider-backed":
        findings.append(Finding("verification_mode", "approval requires provider-backed evidence"))
    if mode == "provider-backed" and evidence_verifier is None:
        findings.append(Finding("verification_mode", "provider-backed mode requires an evidence verifier"))
    verifier = evidence_verifier if mode == "provider-backed" else None
    authority: dict[str, str] = {}
    if assessment.get("acceptance_authority") is not None:
        authority = _acceptance_authority(
            assessment.get("acceptance_authority"),
            "acceptance_authority",
            findings,
            assessed_repository=repository,
        )
    if approval_gate:
        if not authority:
            findings.append(
                Finding("acceptance_authority", "approval requires an immutable external verifier and claim catalog")
            )
        observed_authority = getattr(verifier, "acceptance_authority", None) if verifier is not None else None
        if not isinstance(observed_authority, Mapping):
            findings.append(
                Finding(
                    "acceptance_authority",
                    "candidate-local verification is diagnostic only; final approval requires a pinned external verifier",
                )
            )
        elif authority and dict(observed_authority) != authority:
            findings.append(Finding("acceptance_authority", "does not match the authority used by the verifier"))

    scope = _mapping(assessment.get("scope"), "scope", findings)
    _text_list(scope.get("included"), "scope.included", findings, nonempty=True)
    _text_list(scope.get("excluded"), "scope.excluded", findings)
    _text_list(scope.get("exclusion_rationale"), "scope.exclusion_rationale", findings)

    catalog_rules = _catalog_rules(catalog, skill_name, findings) if skill_name else set()
    _validate_applicability(
        assessment,
        catalog_rules,
        findings,
        as_of=as_of,
        repository=repository,
        revision=revision,
        repository_root=repository_root,
        verifier=verifier,
    )
    _validate_compatibility(
        assessment,
        manifest,
        findings,
        repository=repository,
        revision=revision,
        verifier=verifier,
    )
    _validate_artifacts(
        assessment,
        revision,
        findings,
        repository=repository,
        repository_root=repository_root,
        verifier=verifier,
    )
    _validate_mcp_extension(
        assessment,
        skill_name,
        findings,
        repository=repository,
        revision=revision,
        verifier=verifier,
    )

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
        if type(risk.get("blocking")) is not bool:
            findings.append(Finding(f"{location}.blocking", "must be a boolean"))

    _text(decision.get("rationale"), "decision.rationale", findings)
    reviewer_raw = decision.get("reviewer")
    reviewer_value: Mapping[str, Any] | None = None
    reviewer_state = ""
    if reviewer_raw is not None:
        reviewer_value = _mapping(reviewer_raw, "decision.reviewer", findings)
        reviewer_identity = _identity(reviewer_value, "decision.reviewer", findings)
        reviewer_repository = _text(
            reviewer_value.get("repository"), "decision.reviewer.repository", findings
        )
        reviewer_revision = _text(
            reviewer_value.get("revision"), "decision.reviewer.revision", findings
        )
        reviewer_state = _text(reviewer_value.get("state"), "decision.reviewer.state", findings)
        if reviewer_repository and repository and reviewer_repository != repository:
            findings.append(Finding("decision.reviewer.repository", "must equal repository.name"))
        if reviewer_revision and revision and reviewer_revision != revision:
            findings.append(Finding("decision.reviewer.revision", "must equal repository.revision"))
        if reviewer_identity in prepared or any(
            reviewer_identity[0] == identity[0]
            and (reviewer_identity[1] == identity[1] or reviewer_identity[2] == identity[2])
            for identity in prepared
        ):
            findings.append(Finding("decision.reviewer", "must be independent from every prepared_by identity"))
    elif decision_status == "approve":
        findings.append(Finding("decision.reviewer", "is required for an approval decision"))

    if decision_status == "approve" and reviewer_state != "APPROVED":
        findings.append(Finding("decision.reviewer.state", "must be APPROVED for an approval decision"))
    if require_approval and decision_status != "approve":
        findings.append(Finding("decision.status", "must be approve for an acceptance gate"))
    if decision_status == "approve" and any(
        isinstance(risk, Mapping) and risk.get("blocking") is True for risk in risks
    ):
        findings.append(Finding("decision.status", "cannot approve while a blocking residual risk remains"))
    if decision_status == "approve" and verifier is not None and reviewer_value is not None:
        _provider_findings("decision.reviewer", verifier.verify_review(reviewer_value, revision), findings)

    return sorted(set(findings), key=lambda finding: (finding.location, finding.message))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assessment", type=Path)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--skills-root", type=Path, default=DEFAULT_SKILLS)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--require-approval", action="store_true")
    parser.add_argument("--github-token-env", default="GITHUB_TOKEN")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        assessment = _load_yaml(args.assessment)
        catalog = _load_yaml(args.catalog)
        schema = _load_json(args.schema)
        Draft202012Validator.check_schema(schema)
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(exc, file=sys.stderr)
        return 2

    verifier: EvidenceVerifier | None = None
    if assessment.get("verification_mode") == "provider-backed":
        token = os.environ.get(args.github_token_env, "")
        if token:
            try:
                verifier = GitHubEvidenceVerifier(token)
            except ValueError as exc:
                print(exc, file=sys.stderr)
                return 2

    findings = validate_document(
        assessment,
        catalog,
        args.skills_root,
        require_approval=args.require_approval,
        as_of=args.as_of,
        schema=schema,
        repository_root=args.repository_root,
        evidence_verifier=verifier,
    )
    for finding in findings:
        print(finding, file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

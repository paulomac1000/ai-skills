#!/usr/bin/env python3
"""Validate a lightweight local conformance report without provider identifiers."""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.rule_applicability import (  # noqa: E402
    RuleContext,
    project_applicability,
    test_case_identity_finding,
)

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
REPORT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_IMPLEMENTATION_BYTES = 2 * 1024 * 1024
DEFAULT_ATOMIC_CATALOG = Path(__file__).with_name("atomic-claim-catalog.yaml")


def _mapping(value: Any, name: str, errors: list[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        errors.append(f"{name}: must be a mapping")
        return {}
    return value


def _exact_fields(
    value: Mapping[str, Any],
    allowed: set[str],
    name: str,
    errors: list[str],
) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        errors.append(f"{name}: unsupported fields {unknown}")


def _strings(value: Any, name: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        errors.append(f"{name}: must be a list of non-empty strings")
        return []
    return value


def _safe_file(
    root: Path,
    raw: Any,
    name: str,
    errors: list[str],
) -> Path | None:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        errors.append(f"{name}: must be a repository-relative POSIX path")
        return None
    pure = PurePosixPath(raw)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        errors.append(f"{name}: must remain inside the repository")
        return None

    current = root
    for part in pure.parts:
        current /= part
        if not os.path.lexists(current):
            errors.append(f"{name}: file does not exist")
            return None
        mode = current.lstat().st_mode
        if stat.S_ISLNK(mode):
            errors.append(f"{name}: path must not contain symlinks")
            return None
    if not current.is_file():
        errors.append(f"{name}: must identify a regular file")
        return None
    return current


def _load_yaml(path: Path, label: str, errors: list[str]) -> Mapping[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        errors.append(f"cannot load {label}: {exc}")
        return {}
    return _mapping(value, label, errors)


def _validate_implementation(
    value: Any,
    location: str,
    repository_root: Path,
    errors: list[str],
) -> None:
    implementation = _mapping(value, location, errors)
    _exact_fields(implementation, {"path", "symbol"}, location, errors)
    file = _safe_file(
        repository_root,
        implementation.get("path"),
        f"{location}.path",
        errors,
    )
    symbol = implementation.get("symbol")
    if not isinstance(symbol, str) or not symbol:
        errors.append(f"{location}.symbol: must be non-empty")
        return
    if file is None:
        return
    if file.stat().st_size > MAX_IMPLEMENTATION_BYTES:
        errors.append(f"{location}.path: implementation file is too large")
        return
    try:
        content = file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        errors.append(f"{location}.symbol: implementation is not UTF-8 text")
        return
    if symbol not in content:
        errors.append(f"{location}.symbol: not found")


def _validate_check(
    check: Mapping[str, Any],
    rule: Mapping[str, Any],
    index: int,
    repository_root: Path,
    errors: list[str],
) -> None:
    location = f"checks[{index}]"
    _exact_fields(
        check,
        {
            "rule_id",
            "status",
            "implementation",
            "command",
            "test_case",
            "result",
            "evidence_types",
            "evidence_paths",
        },
        location,
        errors,
    )
    if check.get("status") != "passed" or check.get("result") != "passed":
        errors.append(f"{location}: applicable rule must be passed")

    command = check.get("command")
    if not isinstance(command, str) or not command.strip():
        errors.append(f"{location}.command: must be executable text")
    test_case_finding = test_case_identity_finding(check.get("test_case"), repository_root)
    if test_case_finding:
        errors.append(f"{location}.test_case: {test_case_finding}")

    evidence_types = set(_strings(check.get("evidence_types"), f"{location}.evidence_types", errors))
    missing_evidence = set(rule["required_evidence"]) - evidence_types
    if missing_evidence:
        errors.append(f"{location}.evidence_types: missing {sorted(missing_evidence)}")

    paths = _strings(check.get("evidence_paths"), f"{location}.evidence_paths", errors)
    if not paths:
        errors.append(f"{location}.evidence_paths: must not be empty")
    for path_index, evidence_path in enumerate(paths):
        _safe_file(
            repository_root,
            evidence_path,
            f"{location}.evidence_paths[{path_index}]",
            errors,
        )

    implementations = check.get("implementation")
    if not isinstance(implementations, list) or not implementations:
        errors.append(f"{location}.implementation: must not be empty")
        return
    for implementation_index, implementation in enumerate(implementations):
        _validate_implementation(
            implementation,
            f"{location}.implementation[{implementation_index}]",
            repository_root,
            errors,
        )


def validate(
    report_path: Path,
    repository_root: Path,
    catalog_path: Path,
    atomic_catalog_path: Path = DEFAULT_ATOMIC_CATALOG,
) -> list[str]:
    """Return all structural and semantic conformance findings."""
    errors: list[str] = []
    report = _load_yaml(report_path, "$", errors)
    catalog = _load_yaml(catalog_path, "catalog", errors)
    atomic_catalog = _load_yaml(atomic_catalog_path, "atomic catalog", errors)
    if errors:
        return errors

    _exact_fields(
        report,
        {
            "schema_version",
            "report_id",
            "generated_at",
            "repository",
            "skill",
            "context",
            "checks",
            "residual_risks",
        },
        "$",
        errors,
    )
    if report.get("schema_version") != 1:
        errors.append("schema_version: must equal 1")
    report_id = report.get("report_id")
    if not isinstance(report_id, str) or not REPORT_ID.fullmatch(report_id):
        errors.append("report_id: must be a stable 1-128 character identifier")

    generated = report.get("generated_at")
    try:
        datetime.fromisoformat(str(generated).replace("Z", "+00:00"))
    except ValueError:
        errors.append("generated_at: must be an ISO-8601 date-time")

    repository = _mapping(report.get("repository"), "repository", errors)
    _exact_fields(repository, {"name", "revision"}, "repository", errors)
    repository_name = repository.get("name")
    if not isinstance(repository_name, str) or not REPOSITORY.fullmatch(repository_name):
        errors.append("repository.name: must be owner/repository")
    revision = repository.get("revision")
    if not isinstance(revision, str) or not FULL_SHA.fullmatch(revision):
        errors.append("repository.revision: must be a full immutable SHA")

    skill = _mapping(report.get("skill"), "skill", errors)
    _exact_fields(skill, {"name", "version"}, "skill", errors)
    skill_name = skill.get("name")
    if not isinstance(skill_name, str) or not SKILL_NAME.fullmatch(skill_name):
        errors.append("skill.name: must be a safe skill identifier")
        return errors
    manifest_path = _safe_file(
        repository_root,
        f"skills/{skill_name}/manifest.yaml",
        "skill manifest",
        errors,
    )
    if manifest_path is None:
        return errors
    manifest = _load_yaml(manifest_path, "skill manifest", errors)
    reported_version = skill.get("version")
    manifest_version = manifest.get("version")
    if not isinstance(reported_version, str) or not reported_version:
        errors.append("skill.version: must be a non-empty string")
    elif not isinstance(manifest_version, str) or reported_version != manifest_version:
        errors.append("skill.version: must equal the local skill manifest")

    context_raw = _mapping(report.get("context"), "context", errors)
    _exact_fields(
        context_raw,
        {"target_level", "profiles", "capabilities"},
        "context",
        errors,
    )
    profiles = _strings(context_raw.get("profiles", []), "context.profiles", errors)
    capabilities = _strings(
        context_raw.get("capabilities", []),
        "context.capabilities",
        errors,
    )
    try:
        context = RuleContext(
            str(context_raw.get("target_level")),
            frozenset(profiles),
            frozenset(capabilities),
        )
        projection = project_applicability(catalog, atomic_catalog, skill_name, context)
        rules = projection.parent_rules
    except ValueError as exc:
        errors.append(f"context or catalog: {exc}")
        return errors

    expected = {str(rule["id"]): rule for rule in rules}
    raw_checks = report.get("checks")
    if not isinstance(raw_checks, list):
        errors.append("checks: must be a list")
        raw_checks = []

    checks: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(raw_checks):
        location = f"checks[{index}]"
        check = _mapping(raw, location, errors)
        rule_id = check.get("rule_id")
        if not isinstance(rule_id, str) or not rule_id:
            errors.append(f"{location}.rule_id: must be non-empty")
            continue
        if rule_id in checks:
            errors.append(f"{location}.rule_id: duplicate")
        checks[rule_id] = check
        rule = expected.get(rule_id)
        if rule is None:
            errors.append(f"{location}.rule_id: not applicable for selected context")
            continue
        _validate_check(check, rule, index, repository_root, errors)

    missing = set(expected) - set(checks)
    if missing:
        errors.append(f"checks: missing applicable rules {sorted(missing)}")
    if not isinstance(report.get("residual_risks"), list):
        errors.append("residual_risks: must be a list")
    return errors


def main() -> int:
    """Run the lightweight conformance validator."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path(__file__).with_name("rule-catalog.yaml"),
    )
    args = parser.parse_args()
    errors = validate(
        args.report,
        args.repository_root.resolve(),
        args.catalog,
    )
    for error in errors:
        print(f"ERROR: {error}")
    print(f"conformance findings: {len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

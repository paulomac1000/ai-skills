#!/usr/bin/env python3
"""Validate atomic child-control definitions and one optional conformance report."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.rule_applicability import (  # noqa: E402
    RuleContext,
    project_applicability,
    test_case_identity_finding,
    validate_rule_metadata,
)

DEFAULT_CATALOG = Path(__file__).with_name("atomic-claim-catalog.yaml")
DEFAULT_PARENT_CATALOG = Path(__file__).with_name("rule-catalog.yaml")
DEFAULT_SCHEMA = Path(__file__).with_name("atomic-claim-report.schema.json")
MAX_STRUCTURED_BYTES = 512 * 1024
MAX_SOURCE_BYTES = 4 * 1024 * 1024
SELECTOR = re.compile(r"^(tests/[A-Za-z0-9_./-]+[.]py)::(test_[A-Za-z0-9_]+)$")
HEADING = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)
NON_SLUG = re.compile(r"[^a-z0-9 -]")
SPACES = re.compile(r"[ -]+")


def _slug(value: str) -> str:
    normalized = NON_SLUG.sub("", value.casefold().strip())
    return SPACES.sub("-", normalized).strip("-")


def _safe_file(root: Path, raw: str, *, maximum: int = MAX_SOURCE_BYTES) -> Path:
    if not raw or "\\" in raw:
        raise ValueError("must be a non-empty repository-relative POSIX path")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("must remain inside the repository")
    current = root
    for part in pure.parts:
        current /= part
        if not os.path.lexists(current):
            raise ValueError("does not exist")
        mode = current.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise ValueError("must not contain symlinks")
    metadata = current.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("must identify a regular file")
    if metadata.st_size > maximum:
        raise ValueError(f"exceeds {maximum} bytes")
    return current


def _read_utf8(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"must be readable UTF-8: {exc}") from exc


def _load_mapping(path: Path, *, maximum: int = MAX_STRUCTURED_BYTES) -> Mapping[str, Any]:
    if path.is_symlink():
        raise ValueError(f"{path}: must not be a symlink")
    try:
        metadata = path.stat()
    except OSError as exc:
        raise ValueError(f"{path}: cannot inspect file: {exc}") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{path}: must be a regular file")
    if metadata.st_size > maximum:
        raise ValueError(f"{path}: exceeds {maximum} bytes")
    text = _read_utf8(path)
    try:
        value = json.loads(text) if path.suffix.casefold() == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"{path}: invalid structured data: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"{path}: root must be an object")
    return value


def _parent_rules(catalog: Mapping[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    skills = catalog.get("skills")
    if not isinstance(skills, Mapping):
        raise ValueError("parent catalog skills must be an object")
    for skill_name, raw_skill in skills.items():
        if not isinstance(skill_name, str) or not isinstance(raw_skill, Mapping):
            raise ValueError("parent catalog skill entries must be objects")
        raw_rules = raw_skill.get("rules")
        if not isinstance(raw_rules, list):
            raise ValueError(f"parent catalog skill {skill_name!r} has no rule list")
        identifiers: set[str] = set()
        for raw_rule in raw_rules:
            if not isinstance(raw_rule, Mapping) or not isinstance(raw_rule.get("id"), str):
                raise ValueError(f"parent catalog skill {skill_name!r} contains an invalid rule")
            identifiers.add(str(raw_rule["id"]))
        result[skill_name] = identifiers
    return result


def _source_finding(
    source: object,
    skill: str,
    root: Path,
) -> str | None:
    if not isinstance(source, str) or source.count("#") != 1:
        return "source must use a full repository path followed by one anchor"
    raw_path, anchor = source.split("#", 1)
    if not raw_path.startswith(f"skills/{skill}/"):
        return "source must belong to the declared skill and use a full repository path"
    if not anchor or _slug(anchor) != anchor:
        return "source anchor must be a canonical lowercase slug"
    try:
        path = _safe_file(root, raw_path)
        headings = {_slug(match) for match in HEADING.findall(_read_utf8(path))}
    except ValueError as exc:
        return f"invalid source: {exc}"
    if anchor not in headings:
        return f"source anchor {anchor!r} does not exist"
    return None


def _selector_finding(selector: object, root: Path) -> str | None:
    if not isinstance(selector, str):
        return "test selector must be a string"
    match = SELECTOR.fullmatch(selector)
    if match is None:
        return "test selector must be an exact tests/file.py::test_name identity without wildcards"
    raw_path, function_name = match.groups()
    try:
        path = _safe_file(root, raw_path)
        tree = ast.parse(_read_utf8(path), filename=raw_path)
    except (SyntaxError, ValueError) as exc:
        return f"invalid test selector source: {exc}"
    functions = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if function_name not in functions:
        return f"test function {function_name!r} does not exist"
    return None


def validate_catalog(
    catalog_path: Path = DEFAULT_CATALOG,
    parent_catalog_path: Path = DEFAULT_PARENT_CATALOG,
    repository_root: Path = ROOT,
) -> list[str]:
    """Return deterministic structural and semantic findings for the child-control catalog."""
    try:
        catalog = _load_mapping(catalog_path)
        parents = _parent_rules(_load_mapping(parent_catalog_path))
        root = repository_root.resolve(strict=True)
    except (OSError, ValueError) as exc:
        return [str(exc)]

    findings: list[str] = []
    if catalog.get("schema_version") != 1:
        findings.append("schema_version: must equal 1")
    if not isinstance(catalog.get("catalog_version"), str):
        findings.append("catalog_version: must be a non-empty string")
    controls = catalog.get("controls")
    if not isinstance(controls, list) or not controls:
        return [*findings, "controls: must be a non-empty list"]

    allowed = {
        "id",
        "parent_rule_id",
        "skill",
        "source",
        "description",
        "applies_when",
        "severity",
        "waivable",
        "required_evidence",
        "test_selectors",
    }
    seen: set[str] = set()
    for index, raw in enumerate(controls):
        location = f"controls[{index}]"
        if not isinstance(raw, Mapping):
            findings.append(f"{location}: must be an object")
            continue
        unknown = sorted(set(raw) - allowed)
        if unknown:
            findings.append(f"{location}: unsupported fields {unknown}")
        control_id = raw.get("id")
        if not isinstance(control_id, str) or not control_id:
            findings.append(f"{location}.id: must be a non-empty string")
            continue
        if control_id in seen:
            findings.append(f"{location}.id: duplicates another child control")
        seen.add(control_id)

        skill = raw.get("skill")
        parent = raw.get("parent_rule_id")
        if not isinstance(skill, str) or skill not in parents:
            findings.append(f"{location}.skill: unknown skill")
        elif not isinstance(parent, str) or parent not in parents[skill]:
            findings.append(f"{location}.parent_rule_id: is not a rule owned by {skill}")
        if isinstance(skill, str):
            source_finding = _source_finding(raw.get("source"), skill, root)
            if source_finding:
                findings.append(f"{location}.source: {source_finding}")
        if not isinstance(raw.get("description"), str) or not str(raw["description"]).strip():
            findings.append(f"{location}.description: must be non-empty")

        normalized = dict(raw)
        normalized.pop("parent_rule_id", None)
        normalized.pop("skill", None)
        normalized.pop("source", None)
        normalized.pop("description", None)
        normalized.pop("test_selectors", None)
        for message in validate_rule_metadata(normalized):
            findings.append(f"{location}: {message}")

        selectors = raw.get("test_selectors")
        if not isinstance(selectors, list) or not selectors:
            findings.append(f"{location}.test_selectors: must be a non-empty list")
        else:
            if len(selectors) != len(set(str(value) for value in selectors)):
                findings.append(f"{location}.test_selectors: must be unique")
            for selector_index, selector in enumerate(selectors):
                selector_finding = _selector_finding(selector, root)
                if selector_finding:
                    findings.append(f"{location}.test_selectors[{selector_index}]: {selector_finding}")
    return findings


def _controls(
    catalog: Mapping[str, Any],
    parent_catalog: Mapping[str, Any],
    skill: str,
    context: RuleContext,
) -> dict[str, Mapping[str, Any]]:
    projection = project_applicability(parent_catalog, catalog, skill, context)
    return {str(control["id"]): control for control in projection.child_controls}


def _schema_findings(report: Mapping[str, Any], schema: Mapping[str, Any]) -> list[str]:
    Draft202012Validator.check_schema(schema)
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in sorted(
            Draft202012Validator(schema).iter_errors(report),
            key=lambda item: tuple(str(part) for part in item.absolute_path),
        )
    ]


def _check_implementation(
    value: object,
    location: str,
    root: Path,
    findings: list[str],
) -> None:
    if not isinstance(value, Mapping):
        findings.append(f"{location}: must be an object")
        return
    raw_path = value.get("path")
    symbol = value.get("symbol")
    if not isinstance(raw_path, str) or not isinstance(symbol, str) or not symbol:
        findings.append(f"{location}: path and symbol must be non-empty strings")
        return
    try:
        path = _safe_file(root, raw_path)
        content = _read_utf8(path)
    except ValueError as exc:
        findings.append(f"{location}.path: {exc}")
        return
    if symbol not in content:
        findings.append(f"{location}.symbol: was not found in the implementation file")


def validate_report(
    report_path: Path,
    *,
    catalog_path: Path = DEFAULT_CATALOG,
    parent_catalog_path: Path = DEFAULT_PARENT_CATALOG,
    schema_path: Path = DEFAULT_SCHEMA,
    repository_root: Path = ROOT,
) -> list[str]:
    """Return findings for one maturity-scaled atomic child-control report."""
    findings = validate_catalog(catalog_path, parent_catalog_path, repository_root)
    if findings:
        return findings
    try:
        report = _load_mapping(report_path)
        catalog = _load_mapping(catalog_path)
        parent_catalog = _load_mapping(parent_catalog_path)
        schema = _load_mapping(schema_path)
        root = repository_root.resolve(strict=True)
    except (OSError, ValueError) as exc:
        return [str(exc)]

    findings = _schema_findings(report, schema)
    if findings:
        return findings
    skill = report.get("skill")
    context_raw = report.get("context")
    if not isinstance(skill, str) or not isinstance(context_raw, Mapping):
        return findings
    try:
        context = RuleContext(
            str(context_raw.get("target_level")),
            frozenset(str(value) for value in context_raw.get("profiles", [])),
            frozenset(str(value) for value in context_raw.get("capabilities", [])),
        )
    except (TypeError, ValueError) as exc:
        return [*findings, f"context: {exc}"]

    try:
        expected = _controls(catalog, parent_catalog, skill, context)
    except ValueError as exc:
        return [*findings, f"applicability: {exc}"]
    checks = report.get("checks")
    if not isinstance(checks, list):
        return findings
    seen: set[str] = set()
    for index, raw in enumerate(checks):
        location = f"checks[{index}]"
        if not isinstance(raw, Mapping):
            continue
        control_id = raw.get("control_id")
        if not isinstance(control_id, str):
            continue
        if control_id in seen:
            findings.append(f"{location}.control_id: duplicate")
        seen.add(control_id)
        control = expected.get(control_id)
        if control is None:
            findings.append(f"{location}.control_id: not applicable for the selected context")
            continue
        test_case = raw.get("test_case")
        test_case_finding = test_case_identity_finding(test_case, root)
        if test_case_finding:
            findings.append(f"{location}.test_case: {test_case_finding}")
        elif test_case not in control.get("test_selectors", []):
            findings.append(f"{location}.test_case: is not an approved selector for {control_id}")
        evidence_types = raw.get("evidence_types")
        observed = set(evidence_types) if isinstance(evidence_types, list) else set()
        required = set(control.get("required_evidence", []))
        missing = sorted(required - observed)
        if missing:
            findings.append(f"{location}.evidence_types: missing {missing}")
        for implementation_index, implementation in enumerate(raw.get("implementation", [])):
            _check_implementation(
                implementation,
                f"{location}.implementation[{implementation_index}]",
                root,
                findings,
            )
        for evidence_index, raw_path in enumerate(raw.get("evidence_paths", [])):
            if not isinstance(raw_path, str):
                continue
            try:
                _safe_file(root, raw_path)
            except ValueError as exc:
                findings.append(f"{location}.evidence_paths[{evidence_index}]: {exc}")

    missing_controls = sorted(set(expected) - seen)
    if missing_controls:
        findings.append(f"checks: missing applicable child controls {missing_controls}")
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", nargs="?", type=Path)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--parent-catalog", type=Path, default=DEFAULT_PARENT_CATALOG)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    args = parser.parse_args(argv)

    if args.report is None:
        findings = validate_catalog(
            args.catalog,
            args.parent_catalog,
            args.repository_root,
        )
    else:
        findings = validate_report(
            args.report,
            catalog_path=args.catalog,
            parent_catalog_path=args.parent_catalog,
            schema_path=args.schema,
            repository_root=args.repository_root,
        )
    for finding in findings:
        print(f"ERROR: {finding}")
    print(f"atomic claim findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

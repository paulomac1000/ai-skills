"""Machine-readable applicability rules for skill conformance reports."""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

LEVELS = {"L1": 1, "L2": 2, "L3": 3, "L4": 4}
SEVERITIES = {"blocking", "advisory"}
EVIDENCE_TYPES = {
    "unit",
    "integration",
    "official-client",
    "artifact",
    "security",
    "review",
}


@dataclass(frozen=True, slots=True)
class RuleContext:
    """Maturity, deployment-profile, and capability context for one adoption."""

    target_level: str
    profiles: frozenset[str] = frozenset()
    capabilities: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.target_level not in LEVELS:
            raise ValueError(f"unknown maturity level: {self.target_level}")


def _string_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and all(isinstance(item, str) and item for item in value)
        and len(value) == len(set(value))
    )


def validate_rule_metadata(rule: Mapping[str, Any]) -> list[str]:
    """Return catalog metadata errors for one rule."""
    errors: list[str] = []
    rule_id = rule.get("id", "<unknown>")
    applies = rule.get("applies_when", {})
    if not isinstance(applies, Mapping):
        return [f"{rule_id}: applies_when must be a mapping"]

    allowed_conditions = {
        "maturity_at_least",
        "profiles_any",
        "profiles_all",
        "capabilities_any",
        "capabilities_all",
    }
    unknown_conditions = sorted(set(applies) - allowed_conditions)
    if unknown_conditions:
        errors.append(f"{rule_id}: unsupported applicability fields {unknown_conditions}")

    level = applies.get("maturity_at_least", "L1")
    if level not in LEVELS:
        errors.append(f"{rule_id}: invalid maturity_at_least {level!r}")

    for field in (
        "profiles_any",
        "profiles_all",
        "capabilities_any",
        "capabilities_all",
    ):
        if not _string_list(applies.get(field, [])):
            errors.append(f"{rule_id}: {field} must be a list of non-empty strings")

    if rule.get("severity") not in SEVERITIES:
        errors.append(f"{rule_id}: severity must be blocking or advisory")
    if type(rule.get("waivable")) is not bool:
        errors.append(f"{rule_id}: waivable must be boolean")

    evidence = rule.get("required_evidence")
    if not isinstance(evidence, list) or not evidence or not all(item in EVIDENCE_TYPES for item in evidence):
        errors.append(f"{rule_id}: required_evidence must use known evidence types")
    return errors


def rule_applies(rule: Mapping[str, Any], context: RuleContext) -> bool:
    """Return whether one validated rule applies to the selected context."""
    applies = rule.get("applies_when", {})
    assert isinstance(applies, Mapping)
    if LEVELS[context.target_level] < LEVELS[str(applies.get("maturity_at_least", "L1"))]:
        return False

    profiles_any = set(applies.get("profiles_any", []))
    profiles_all = set(applies.get("profiles_all", []))
    capabilities_any = set(applies.get("capabilities_any", []))
    capabilities_all = set(applies.get("capabilities_all", []))
    return (
        (not profiles_any or bool(profiles_any & context.profiles))
        and profiles_all <= context.profiles
        and (not capabilities_any or bool(capabilities_any & context.capabilities))
        and capabilities_all <= context.capabilities
    )


def expected_rules(
    catalog: Mapping[str, Any],
    skill_name: str,
    context: RuleContext,
) -> list[Mapping[str, Any]]:
    """Select every valid catalog rule that applies to the supplied context."""
    skills = catalog.get("skills")
    if not isinstance(skills, Mapping) or skill_name not in skills:
        raise ValueError(f"unknown skill in rule catalog: {skill_name}")

    skill = skills[skill_name]
    rules = skill.get("rules") if isinstance(skill, Mapping) else None
    if not isinstance(rules, Sequence):
        raise ValueError(f"rule catalog for {skill_name} has no rules")

    result: list[Mapping[str, Any]] = []
    for raw in rules:
        if not isinstance(raw, Mapping):
            raise ValueError(f"rule catalog for {skill_name} contains a non-mapping rule")
        normalized = dict(raw)
        normalized.setdefault("applies_when", {"maturity_at_least": "L1"})
        normalized.setdefault("severity", "blocking")
        normalized.setdefault("waivable", False)
        normalized.setdefault("required_evidence", ["unit"])
        errors = validate_rule_metadata(normalized)
        if errors:
            raise ValueError("; ".join(errors))
        if rule_applies(normalized, context):
            result.append(normalized)
    return result


TEST_CASE_IDENTITY = re.compile(r"^(tests/[A-Za-z0-9_./-]+[.]py)::(test_[A-Za-z0-9_]+)$")
_TestCaseSourceLoader = Callable[[str], str]
_TEST_CASE_SOURCE_LOADER: ContextVar[_TestCaseSourceLoader | None] = ContextVar(
    "ai_skills_test_case_source_loader",
    default=None,
)


@dataclass(frozen=True, slots=True)
class ApplicabilityProjection:
    """One context projection shared by parent rules and atomic child controls."""

    parent_rules: tuple[Mapping[str, Any], ...]
    child_controls: tuple[Mapping[str, Any], ...]


def project_applicability(
    parent_catalog: Mapping[str, Any],
    child_catalog: Mapping[str, Any],
    skill_name: str,
    context: RuleContext,
) -> ApplicabilityProjection:
    """Project parent and child applicability and reject child-without-parent states."""
    parents = tuple(expected_rules(parent_catalog, skill_name, context))
    parent_ids = {str(rule["id"]) for rule in parents}
    raw_controls = child_catalog.get("controls", [])
    if not isinstance(raw_controls, list):
        raise ValueError("atomic child-control catalog controls must be a list")
    children: list[Mapping[str, Any]] = []
    for raw in raw_controls:
        if not isinstance(raw, Mapping):
            raise ValueError("atomic child control must be an object")
        if raw.get("skill") != skill_name:
            continue
        parent_id = raw.get("parent_rule_id")
        control_id = raw.get("id")
        if not isinstance(parent_id, str) or not isinstance(control_id, str):
            raise ValueError("atomic child control has invalid parent or control identity")
        if not rule_applies(raw, context):
            continue
        if parent_id not in parent_ids:
            raise ValueError(f"child control {control_id} applies while parent rule {parent_id} does not")
        children.append(raw)
    return ApplicabilityProjection(parents, tuple(children))


@contextmanager
def test_case_source_loader(loader: _TestCaseSourceLoader) -> Iterator[None]:
    """Temporarily bind test-identity inspection to an immutable external source loader."""
    token = _TEST_CASE_SOURCE_LOADER.set(loader)
    try:
        yield
    finally:
        _TEST_CASE_SOURCE_LOADER.reset(token)


def _test_tree(source: str, raw_path: str) -> ast.Module | str:
    try:
        return ast.parse(source, filename=raw_path)
    except SyntaxError as exc:
        return f"cannot inspect test file: {exc}"


def test_case_identity_finding(value: object, repository_root: Path) -> str | None:
    """Validate one exact repository test identity without executing candidate code."""
    if not isinstance(value, str):
        return "must be an exact tests/file.py::test_name identity"
    match = TEST_CASE_IDENTITY.fullmatch(value)
    if match is None:
        return "must be an exact tests/file.py::test_name identity"
    raw_path, function_name = match.groups()
    pure = PurePosixPath(raw_path)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        return "test path must remain inside the repository"

    loader = _TEST_CASE_SOURCE_LOADER.get()
    if loader is not None:
        try:
            source = loader(raw_path)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            return f"cannot inspect immutable test file: {exc}"
        parsed = _test_tree(source, raw_path)
        if isinstance(parsed, str):
            return parsed
        tree = parsed
    else:
        root = repository_root.resolve(strict=True)
        current = root
        for part in pure.parts:
            current /= part
            if current.is_symlink():
                return "test path must not contain symlinks"
        if not current.is_file():
            return "test file does not exist"
        try:
            source = current.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return f"cannot inspect test file: {exc}"
        parsed = _test_tree(source, raw_path)
        if isinstance(parsed, str):
            return parsed
        tree = parsed

    functions = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if function_name not in functions:
        return f"test function {function_name!r} does not exist"
    return None

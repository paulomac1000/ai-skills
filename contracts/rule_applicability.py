"""Machine-readable applicability rules for skill conformance reports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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
    if (
        not isinstance(evidence, list)
        or not evidence
        or not all(item in EVIDENCE_TYPES for item in evidence)
    ):
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

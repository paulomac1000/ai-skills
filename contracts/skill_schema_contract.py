"""Canonical skill-to-live-schema contractRef compatibility model."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class Compatibility(StrEnum):
    COMPATIBLE = "COMPATIBLE"
    COMPATIBLE_ADDITION = "COMPATIBLE_ADDITION"
    INCOMPATIBLE_REMOVAL = "INCOMPATIBLE_REMOVAL"
    ENUM_REVIEW_REQUIRED = "ENUM_REVIEW_REQUIRED"
    SEMANTIC_REVIEW_REQUIRED = "SEMANTIC_REVIEW_REQUIRED"
    NOT_VERIFIED = "NOT_VERIFIED"


@dataclass(frozen=True)
class ContractRef:
    capability: str
    required_fields: tuple[str, ...]
    required_semantics: Mapping[str, object]
    minimum_revision: str


@dataclass(frozen=True)
class SchemaSnapshot:
    available: bool
    capability: str
    revision: str
    skill_revision: str
    fields: frozenset[str]
    enums: Mapping[str, tuple[str, ...]]
    semantics: Mapping[str, object]


def _revision(value: str) -> tuple[int, ...] | None:
    parts = value.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def classify_contract(
    ref: ContractRef,
    *,
    skill_revision: str,
    snapshot: SchemaSnapshot | None,
) -> Compatibility:
    """Compare one exact skill revision with one exact live/snapshot schema."""
    if snapshot is None or not snapshot.available:
        return Compatibility.NOT_VERIFIED
    if not ref.capability or snapshot.capability != ref.capability:
        return Compatibility.NOT_VERIFIED
    if not skill_revision or snapshot.skill_revision != skill_revision:
        return Compatibility.NOT_VERIFIED
    minimum = _revision(ref.minimum_revision)
    observed = _revision(snapshot.revision)
    if minimum is None or observed is None:
        return Compatibility.NOT_VERIFIED
    if observed < minimum:
        return Compatibility.SEMANTIC_REVIEW_REQUIRED
    if any(field not in snapshot.fields for field in ref.required_fields):
        return Compatibility.INCOMPATIBLE_REMOVAL

    for key, expected in ref.required_semantics.items():
        if key.endswith(".enum"):
            field = key.removesuffix(".enum")
            expected_values = tuple(expected) if isinstance(expected, (list, tuple)) else ()
            if tuple(snapshot.enums.get(field, ())) != expected_values:
                return Compatibility.ENUM_REVIEW_REQUIRED
        elif snapshot.semantics.get(key) != expected:
            return Compatibility.SEMANTIC_REVIEW_REQUIRED

    if snapshot.fields.difference(ref.required_fields):
        return Compatibility.COMPATIBLE_ADDITION
    return Compatibility.COMPATIBLE

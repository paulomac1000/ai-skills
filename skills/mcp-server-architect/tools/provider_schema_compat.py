"""Recursive public-schema compatibility checks against versioned provider subsets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

_REQUIRED_RESTRICTIONS = {
    "allowTypeUnions",
    "allowNullableObjectArray",
    "allowAnyOf",
    "allowOneOf",
    "allowRef",
    "allowDefaults",
    "allowAdditionalProperties",
}


@dataclass(frozen=True)
class ProviderProfile:
    provider: str
    contractRevision: str
    schemaRestrictions: Mapping[str, object]
    sourceEvidence: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.contractRevision.strip():
            raise ValueError("provider and contractRevision must be non-empty")
        if not self.sourceEvidence or any(not item.strip() for item in self.sourceEvidence):
            raise ValueError("sourceEvidence must contain at least one non-empty reference")


@dataclass(frozen=True)
class CompatibilityResult:
    compatible: bool
    activation_allowed: bool
    violations: tuple[str, ...]


def check_provider_schema(schema: Mapping[str, object], profile: ProviderProfile) -> CompatibilityResult:
    """Validate recursively; incomplete/unknown provider rules fail closed."""
    restrictions = profile.schemaRestrictions
    missing = sorted(_REQUIRED_RESTRICTIONS - set(restrictions))
    invalid = sorted(
        key for key in _REQUIRED_RESTRICTIONS if key in restrictions and not isinstance(restrictions[key], bool)
    )
    if missing or invalid:
        detail = []
        if missing:
            detail.append(f"profile_unknown:missing={','.join(missing)}")
        if invalid:
            detail.append(f"profile_unknown:non_boolean={','.join(invalid)}")
        return CompatibilityResult(False, False, tuple(detail))

    violations: list[str] = []
    _check_node(schema, profile.schemaRestrictions, "$", violations)
    compatible = not violations
    return CompatibilityResult(compatible, compatible, tuple(violations))


def _check_node(
    node: Mapping[str, object],
    restrictions: Mapping[str, object],
    path: str,
    violations: list[str],
) -> None:
    node_type = node.get("type")
    types: tuple[str, ...]
    if isinstance(node_type, str):
        types = (node_type,)
    elif isinstance(node_type, Sequence) and not isinstance(node_type, (str, bytes)):
        types = tuple(item for item in node_type if isinstance(item, str))
        if len(types) != len(node_type) or not restrictions["allowTypeUnions"]:
            violations.append(f"{path}:type_union_unsupported")
        if "null" in types and any(item in types for item in ("object", "array")):
            if not restrictions["allowNullableObjectArray"]:
                violations.append(f"{path}:nullable_object_array_unsupported")
    else:
        types = ()

    object_compatible = "object" in types and (
        len(types) == 1
        or (
            restrictions["allowTypeUnions"] is True
            and restrictions["allowNullableObjectArray"] is True
            and set(types) <= {"object", "null"}
        )
    )
    array_compatible = "array" in types and (
        len(types) == 1
        or (
            restrictions["allowTypeUnions"] is True
            and restrictions["allowNullableObjectArray"] is True
            and set(types) <= {"array", "null"}
        )
    )

    if "properties" in node or "required" in node:
        if not object_compatible:
            violations.append(f"{path}:object_keywords_on_incompatible_node")
    if "items" in node and not array_compatible:
        violations.append(f"{path}:items_on_incompatible_node")

    for keyword, rule in (
        ("anyOf", "allowAnyOf"),
        ("oneOf", "allowOneOf"),
        ("$ref", "allowRef"),
        ("default", "allowDefaults"),
        ("additionalProperties", "allowAdditionalProperties"),
    ):
        if keyword in node and restrictions[rule] is not True:
            violations.append(f"{path}:{keyword}_unsupported")

    properties = node.get("properties")
    if isinstance(properties, Mapping):
        for name, child in properties.items():
            if isinstance(name, str) and isinstance(child, Mapping):
                _check_node(child, restrictions, f"{path}.properties.{name}", violations)

    items = node.get("items")
    if isinstance(items, Mapping):
        _check_node(items, restrictions, f"{path}.items", violations)

    for keyword in ("anyOf", "oneOf"):
        variants = node.get(keyword)
        if isinstance(variants, Sequence) and not isinstance(variants, (str, bytes)):
            for index, child in enumerate(variants):
                if isinstance(child, Mapping):
                    _check_node(child, restrictions, f"{path}.{keyword}[{index}]", violations)

    additional = node.get("additionalProperties")
    if isinstance(additional, Mapping):
        _check_node(additional, restrictions, f"{path}.additionalProperties", violations)

    defs = node.get("$defs")
    if isinstance(defs, Mapping):
        for name, child in defs.items():
            if isinstance(name, str) and isinstance(child, Mapping):
                _check_node(child, restrictions, f"{path}.$defs.{name}", violations)

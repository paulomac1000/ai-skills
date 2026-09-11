#!/usr/bin/env python3
"""Validate MCP consumer runtime identity references against the canonical contract."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypeAlias

from jsonschema import Draft202012Validator, FormatChecker

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_IDENTITY_SCHEMA = REPOSITORY_ROOT / "contracts/runtime-identity.schema.json"

# Consumer code may use this name for typing, but the value itself is the
# canonical runtime-identity object. There is deliberately no second DTO.
RuntimeIdentityRef: TypeAlias = Mapping[str, Any]


def _validator(schema_path: Path = RUNTIME_IDENTITY_SCHEMA) -> Draft202012Validator:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_runtime_identity_ref(
    identity: RuntimeIdentityRef,
    *,
    schema_path: Path = RUNTIME_IDENTITY_SCHEMA,
) -> RuntimeIdentityRef:
    """Return the same canonical object after fail-closed schema validation."""
    if not isinstance(identity, Mapping):
        raise ValueError("RuntimeIdentityRef must be a mapping")
    errors = sorted(
        _validator(schema_path).iter_errors(identity),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    if errors:
        path = ".".join(str(part) for part in errors[0].absolute_path)
        prefix = f"{path}: " if path else ""
        raise ValueError(f"invalid canonical runtime identity: {prefix}{errors[0].message}")
    return identity


def runtime_instance_key(identity: RuntimeIdentityRef) -> tuple[str, str]:
    """Return canonical runtime/generation identity without inventing aliases."""
    validate_runtime_identity_ref(identity)
    return str(identity["runtime_id"]), str(identity["instance_generation"])

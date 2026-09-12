#!/usr/bin/env python3
"""Validate layered MCP action outcomes against the canonical contract."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ACTION_OUTCOME_SCHEMA = REPOSITORY_ROOT / "contracts/action-outcome.schema.json"

type ActionOutcome = Mapping[str, Any]


def _validator(schema_path: Path = ACTION_OUTCOME_SCHEMA) -> Draft202012Validator:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_layered_outcome(
    outcome: ActionOutcome,
    *,
    schema_path: Path = ACTION_OUTCOME_SCHEMA,
) -> ActionOutcome:
    """Return the same outcome after fail-closed canonical validation."""
    if not isinstance(outcome, Mapping):
        raise ValueError("layered action outcome must be a mapping")
    errors = sorted(
        _validator(schema_path).iter_errors(outcome),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    if errors:
        path = ".".join(str(part) for part in errors[0].absolute_path)
        prefix = f"{path}: " if path else ""
        raise ValueError(f"invalid canonical layered outcome: {prefix}{errors[0].message}")
    return outcome

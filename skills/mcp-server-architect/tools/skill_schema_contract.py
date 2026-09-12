"""Architect-facing alias for the canonical skill/schema contract model."""

from contracts.skill_schema_contract import (
    Compatibility,
    ContractRef,
    SchemaSnapshot,
    classify_contract,
)

__all__ = ["Compatibility", "ContractRef", "SchemaSnapshot", "classify_contract"]

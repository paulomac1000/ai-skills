"""Consumer-facing alias for canonical contractRef compatibility checks."""

from contracts.skill_schema_contract import (
    Compatibility,
    ContractRef,
    SchemaSnapshot,
    classify_contract,
)

__all__ = ["Compatibility", "ContractRef", "SchemaSnapshot", "classify_contract"]

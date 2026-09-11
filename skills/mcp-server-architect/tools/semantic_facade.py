"""Validation for the bounded agent-backed MCP semantic-façade profile."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticFacadeDesign:
    public_tools: tuple[str, ...]
    public_schema_bytes: int
    max_public_tools: int
    max_public_schema_bytes: int
    upstream_tools_internal: bool
    deterministic_core: bool
    bounded_llm: bool
    durable_jobs: bool
    typed_mutations: bool
    evidence_by_reference: bool
    unrestricted_mutation_prompt: bool = False


def semantic_facade_violations(design: SemanticFacadeDesign) -> tuple[str, ...]:
    """Return stable violations; declared budgets never weaken the <=10 profile ceiling."""
    violations: list[str] = []
    if design.max_public_tools <= 0 or design.max_public_tools > 10:
        violations.append("max_public_tools must be in 1..10")
    if design.max_public_schema_bytes <= 0:
        violations.append("max_public_schema_bytes must be positive")
    if len(design.public_tools) > min(max(design.max_public_tools, 0), 10):
        violations.append("public tool count exceeds declared semantic-facade budget")
    if design.public_schema_bytes < 0 or design.public_schema_bytes > design.max_public_schema_bytes:
        violations.append("public schema bytes exceed declared semantic-facade budget")
    if len(set(design.public_tools)) != len(design.public_tools) or any(
        not name.strip() for name in design.public_tools
    ):
        violations.append("public semantic tool names must be unique and non-empty")
    if not design.upstream_tools_internal:
        violations.append("low-level upstream tools must remain internal by default")
    if not design.deterministic_core:
        violations.append("deterministic discovery/policy/execution/verification core is required")
    if not design.bounded_llm:
        violations.append("LLM reasoning must be optional and bounded")
    if not design.durable_jobs:
        violations.append("long-running work must use durable jobs")
    if not design.typed_mutations or design.unrestricted_mutation_prompt:
        violations.append("privileged mutations require typed target/action constraints")
    if not design.evidence_by_reference:
        violations.append("detailed evidence must be persisted and retrieved by reference")
    return tuple(violations)


def validate_semantic_facade(design: SemanticFacadeDesign) -> SemanticFacadeDesign:
    """Fail closed when the public surface or execution profile violates its budget."""
    violations = semantic_facade_violations(design)
    if violations:
        raise ValueError("semantic facade invalid: " + "; ".join(violations))
    return design

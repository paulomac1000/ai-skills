---
description: Bounded discovery, pagination, detail selection, and capability-version negotiation for MCP consumers.
doc_id: reference.mcp-consumer-pagination-negotiation
type: reference
status: active
rigor: informative
owners: [repository-maintainers]
---

# MCP consumer pagination and negotiation

## Discovery budget

Start with server and category summaries. Fetch full schemas only for plausible candidates. Stop when one safe capability satisfies the outcome or when the budget is exhausted. A larger catalog is not evidence of a better choice.

## Detail selection

Inspect the input schema before emitting optional detail flags. Use `detail_level: summary|minimal|compact` only when present in an accepted enum. Emit `compact: true` or `summary: true` only when the schema accepts the boolean literal `true` through type, const, enum, or an explicit union.

## Pagination

Use page count, result count, context budget, and outcome completion as independent stop conditions. A server's `has_more: false` stops. A non-empty string cursor is opaque and returned unchanged. Do not stringify lists, maps, booleans, or arbitrary objects. Offsets exclude booleans and negative integers.

## Version negotiation

Prefer explicit capability fields and schema inspection. Version numbers can guide compatibility but do not substitute for feature detection. When a server omits an optional feature, do not synthesize it from naming conventions.

## Stable identifiers

Carry identifiers exactly between list, detail, mutation, and verification calls. Do not use display names when the contract exposes an immutable ID. Preserve server namespace in multi-server aggregations.

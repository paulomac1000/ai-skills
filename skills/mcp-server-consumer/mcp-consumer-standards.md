---
description: Decision and execution standard for agents consuming MCP capabilities
doc_id: reference.mcp-consumer-standard
type: reference
status: active
rigor: normative
owners: [mcp-maintainers]
schema_version: 3
upstream: [reference.mcp-server-standard]
---

# MCP consumer standard

## DISCOVERY

**MCP-CON-001 — Outcome first.** The consumer MUST define the required outcome and constraints before selecting a capability.

**MCP-CON-002 — Standard discovery.** Use protocol discovery for tools, resources, and prompts. A custom capability index MAY supplement it with policy, category, latency, or cost data.

**MCP-CON-003 — No unsafe fallback.** When side effects, data sensitivity, or authorization are unknown, the consumer MUST NOT default to read-only or invoke automatically.

**MCP-CON-004 — Bounded context.** Load only relevant schemas. For large catalogs, search or filter before reading full definitions.

## SELECTION

**MCP-CON-010 — Semantic fit.** Choose the capability whose contract directly satisfies the outcome. Names are hints; schema and description determine fit.

**MCP-CON-011 — Efficient shape.** Prefer search, summary, batch, composite, or workflow capabilities when they reduce calls without hiding required control or verification.

**MCP-CON-012 — Stable identifiers.** Carry identifiers returned by discovery and list calls into later invocations. Do not repeatedly resolve a known target by friendly name.

**MCP-CON-013 — Negative capability.** Absence from a partial page or filtered result is not proof of absence. Respect pagination and catalog scope.

## POLICY

Before invocation, classify:

- effect: read, write, destructive, unknown,
- data: ordinary, sensitive, prohibited-to-display,
- target scope: exact, set, open-ended,
- retry: safe, conditional, unsafe, unknown,
- authorization evidence: present or absent,
- user intent: informational, requested mutation, explicitly confirmed high-impact action.

**MCP-CON-020 — Read.** A known read with acceptable data handling may be invoked without confirmation.

**MCP-CON-021 — Write.** A write requires a clear user goal, bounded targets, and server authorization. Confirmation may cover a coherent workflow when impact and target set are explicit.

**MCP-CON-022 — Destructive.** A destructive or difficult-to-reverse action requires separate, explicit confirmation that states capability, targets, impact, and recovery limits.

**MCP-CON-023 — Unknown.** Unknown effect, target, or authorization yields defer or reject, never automatic invocation.

**MCP-CON-024 — Metadata limits.** Tool annotations, descriptions, custom manifests, and risk prefixes inform the decision but do not prove authorization or safety.

## INVOCATION

**MCP-CON-030 — Minimal valid input.** Send only required and intentionally selected optional parameters.

**MCP-CON-031 — Correlation.** Preserve request or trace identifiers returned by the server and include them in diagnostics.

**MCP-CON-032 — Native result parsing.** Interpret MCP content blocks, `structuredContent`, protocol errors, and `isError`. Legacy envelopes are handled by adapters. Unknown compatible fields are preserved or ignored safely.

**MCP-CON-033 — Empty success.** An empty list or zero count is a valid successful result unless the capability contract says otherwise.

**MCP-CON-034 — Partial execution.** Stop dependent steps after a prerequisite failure. Report completed and skipped steps separately.

## RETRY AND RECOVERY

**MCP-CON-040 — Compound retry decision.** Retry only when the operation is safe to repeat and the failure is transient. Server retry hints cannot override an unsafe operation contract.

**MCP-CON-041 — Bound.** Automatic retries are bounded and use delay with jitter where appropriate. Authentication, authorization, validation, not-found, and destructive uncertainty are not automatically retried.

**MCP-CON-042 — Repair input once.** The consumer MAY correct a clearly local schema or identifier error once when the intended value is unambiguous. It MUST NOT guess credentials, targets, or destructive parameters.

**MCP-CON-043 — Diagnostics.** Failure reporting includes capability, target, error category, server message, correlation ID, attempts, completed side effects, and the next safe action.

## WORKFLOWS

**MCP-CON-050 — Plan dependencies.** Multi-capability plans state prerequisites, mutation points, verification, and stop conditions.

**MCP-CON-051 — Concurrency.** Parallelize only independent, known concurrent-safe reads or idempotent operations. Serialize shared-target mutations unless the contract explicitly supports concurrency.

**MCP-CON-052 — Verification.** Verify a mutation through observable state. A successful call result alone is insufficient when post-state can be read.

**MCP-CON-053 — Compensation.** A reversible workflow identifies compensation before mutation. Compensation is not called automatically if it could worsen an unknown state.

## DATA HANDLING

**MCP-CON-060 — Minimize.** Request and display the least sensitive detail needed for the task.

**MCP-CON-061 — No casual persistence.** Sensitive outputs are not copied into logs, long-lived memory, issue bodies, or unrelated prompts.

**MCP-CON-062 — Cross-server boundary.** Data from one server is not forwarded to another unless the user goal requires it and both authorization and sensitivity policies allow it.

## ACCEPTANCE

A completed workflow reports the result, verification evidence, tool calls that changed state, partial failures, retries, and unresolved uncertainty. It never represents an unverified mutation as complete.

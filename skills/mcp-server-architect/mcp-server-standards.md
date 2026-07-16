---
description: Language-neutral standard for secure, testable, consumer-oriented MCP servers
doc_id: reference.mcp-server-standard
type: reference
status: active
rigor: normative
owners: [mcp-maintainers]
schema_version: 3
aliases: [MCP server rules, tool design, Streamable HTTP]
entities: [stdio, Streamable HTTP, structuredContent, isError]
---

# MCP server standard

## SCOPE

This standard governs server capability design, domain boundaries, protocol results, transports, authorization, resilience, observability, and testing. Language and framework mechanics live in references.

The stable compatibility baseline is the currently published MCP protocol revision selected by the project. Preview protocol behavior is opt-in and isolated behind a compatibility profile.

## CAPABILITY DESIGN

**MCP-SRV-001 — Workflow-first surface.** A server MUST model user or agent workflows before mapping upstream endpoints. A tool MUST have a clear purpose that a consumer can select from its name, description, and schema.

**MCP-SRV-002 — Primitive choice.** Use:

- resources for addressable, read-oriented context,
- tools for computation or side effects,
- prompts for reusable user-invoked templates,
- metadata for discovery facts that do not require execution.

**MCP-SRV-003 — Bounded catalog.** Avoid synonymous tools and endpoint-shaped duplication. For large domains, provide search, summary, batch, or workflow tools and measure selection quality. Custom discovery tools MAY complement standard discovery but MUST NOT replace protocol discovery.

**MCP-SRV-004 — Stable identifiers.** List and search results SHOULD return identifiers accepted by detail and action tools. Friendly labels are display data, not identifiers.

**MCP-SRV-005 — Bounded output.** Potentially large results MUST support pagination, filtering, limits, or compact detail. Empty results are successful results unless the contract states that absence is exceptional.

## CONTRACTS

**MCP-SRV-010 — Schema accuracy.** Input and output schemas MUST describe the actual accepted and returned shape. Validation runs before external I/O.

**MCP-SRV-011 — Native results.** Use MCP content blocks and `structuredContent` where appropriate. Set `isError` for tool execution failures represented as tool results. Protocol errors remain protocol errors. A project MAY provide a legacy envelope adapter, but it is not the canonical contract.

**MCP-SRV-012 — Error taxonomy.** Errors MUST distinguish invalid input, unauthorized or forbidden action, unavailable dependency, timeout or cancellation, not found, conflict, rate limit, upstream failure, and internal defect when those states are observable. Do not leak secrets or raw internal traces.

**MCP-SRV-013 — Annotations are hints.** Read-only, destructive, idempotent, and open-world annotations MUST reflect reality, but consumers and servers MUST NOT treat them as authorization.

**MCP-SRV-014 — Version tolerance.** Consumers may send unknown metadata and servers may add optional fields. Implementations MUST ignore compatible unknown fields and MUST document breaking schema changes.

## ARCHITECTURE

**MCP-SRV-020 — Domain isolation.** Business logic, upstream clients, validation, and policy MUST be callable without an MCP transport. Registration is a thin adapter.

**MCP-SRV-021 — Transport isolation.** Tool logic MUST NOT depend on sockets, HTTP request objects, stdio streams, or session affinity unless the capability contract explicitly requires request context.

**MCP-SRV-022 — State declaration.** A server MUST declare whether it is stateless, session-scoped, or backed by shared durable state. Remote horizontal scaling MUST NOT rely on accidental process-local state.

**MCP-SRV-023 — Configuration ownership.** Defaults have one code owner. Secrets come from the deployment secret mechanism. Generated dependency and compatibility facts do not live in prose.

## TRANSPORTS

**MCP-SRV-030 — stdio.** Use stdio for local child-process integrations. Protocol output owns stdout; application logs use stderr.

**MCP-SRV-031 — Remote HTTP.** Use Streamable HTTP for new remote servers. Validate allowed hosts and request origins where applicable, bind intentionally, enforce authentication, and configure body, concurrency, and timeout limits.

**MCP-SRV-032 — Legacy SSE.** HTTP+SSE MAY remain behind a compatibility entry point for existing clients. Do not make it the default for a new implementation.

**MCP-SRV-033 — No mandatory side API.** Health or administrative HTTP endpoints MAY exist when required by deployment. A parallel REST mirror of every tool is optional and requires an independent consumer or test justification.

## SECURITY AND SIDE EFFECTS

**MCP-SRV-040 — Server-enforced policy.** Every protected operation MUST pass server-side identity, permission, scope, and target checks before I/O.

**MCP-SRV-041 — Default deny.** Write, destructive, privileged, raw-command, filesystem, and sensitive-data capabilities are denied unless explicitly enabled and authorized.

**MCP-SRV-042 — Confirmation.** Destructive or high-impact operations MUST require an interaction that proves user intent when the client supports it. Confirmation does not replace authorization.

**MCP-SRV-043 — Command and path safety.** Commands use argument arrays or typed APIs, not interpolated shells. Allowed operations and paths are explicit; canonicalized targets are checked against the allowed boundary.

**MCP-SRV-044 — Token integrity.** A server MUST NOT pass through a client token to an unrelated upstream service. Tokens are audience-bound and secrets are redacted from logs and results.

**MCP-SRV-045 — Data minimization.** Return only fields needed for the workflow. Sensitive source data and raw credentials must not cross the model boundary when a derived flag or summary is sufficient.

## RESILIENCE

**MCP-SRV-050 — Bounds.** External I/O has a timeout and cancellation path. Retries are bounded, use backoff, and occur only for operations known to be safe to retry.

**MCP-SRV-051 — Failure containment.** One dependency failure must not prevent unrelated capabilities from starting when graceful degradation is feasible. Startup failure is correct when a required security or data dependency is unavailable.

**MCP-SRV-052 — Exception policy.** Expected domain and upstream failures are mapped deliberately. Unexpected defects are logged with correlation context and surfaced as sanitized internal errors; they are not disguised as success.

**MCP-SRV-053 — Cache semantics.** Cached data declares scope, freshness, invalidation, and stale-data behavior. A cache must not weaken authorization boundaries.

## OBSERVABILITY

**MCP-SRV-060 — Correlation.** Each invocation SHOULD carry a correlation ID through logs and upstream calls.

**MCP-SRV-061 — Audit.** Protected mutations record actor, capability, target, decision, outcome, and timestamp without recording secrets or prohibited payloads.

**MCP-SRV-062 — Useful telemetry.** Measure latency, errors, cancellation, rate limits, payload size, cache behavior, and capability usage. Do not emit high-cardinality sensitive labels.

## TESTING

**MCP-SRV-070 — Layered evidence.** Test domain logic, schemas, policy decisions, protocol registration, transport behavior, and representative upstream integration separately.

**MCP-SRV-071 — Real contract evidence.** Mocks prove local branches, not upstream compatibility. Each upstream integration needs a maintained contract fixture, recorded cassette, sandbox, or live smoke test with a documented freshness policy.

**MCP-SRV-072 — Security tests.** Protected servers test unauthorized, forbidden, cross-target, path traversal, command injection, token leakage, oversized input, concurrency, cancellation, and unsafe retry cases relevant to their surface.

**MCP-SRV-073 — Consumer tests.** A representative client MUST list and invoke capabilities. Large catalogs additionally test tool selection, ambiguous naming, pagination, and context cost.

## ACCEPTANCE

A server is ready when its chosen protocol and transport work with a representative client, policy tests prove the default-deny boundary, upstream evidence is current, operational telemetry exists, and documentation states compatibility limits.

---
description: Architecture decisions for enhanced MCP server standard — Streamable HTTP, middleware pipeline, progressive discovery, multi-language support, transport bridging
doc_id: decision.006-mcp-enhanced-standard
type: decision
status: proposed
rigor_tier: L3
ttl_days: 0
version: 1.0.0
stability: volatile
ai_scope: editable
source_of_truth: true
tags: ["adr", "mcp", "standards", "architecture", "streamable-http", "middleware"]
upstream:
  - ref.mcp-server-standards
  - decision.002-mcp-standard-decisions
supersedes: null
superseded_by: null
last_verified: 2026-06-06
owners: ["backend-team"]
verification_status:
  - ai_analyzed
doc_kind: atomic
glossary_terms: []
ttl_policy: permanent
---

# ADR: Enhanced MCP Server Standard — v2.0 Architecture

> [!NOTE]
> Based on deep analysis of 25+ MCP proxy repos, the official `modelcontextprotocol/servers`, Streamable HTTP transport spec, embedded MCP patterns (Obsidian/VS Code/Godot), and 2026-07-28 spec release candidate.

## CONTEXT

The existing `mcp-server-standards.md` (v1.x, ~1500 lines) is a mature, battle-tested standard for Python/FastMCP MCP servers with L1-L4 maturity tiers. It defines tool design, response contracts, testing hierarchies, security patterns, and operational safety.

However, the MCP ecosystem has evolved dramatically since its creation:

1. **Streamable HTTP is now the default transport** — the 2026-07-28 spec release candidate makes the protocol fully stateless with `Mcp-Method`/`Mcp-Name` headers, `ttlMs`/`cacheScope`, and formal OAuth 2.1 support. SSE is deprecated.

2. **The proxy explosion proves missing abstractions** — 25+ MCP proxy repositories (sparfenyuk/mcp-proxy 2,576★, agentgateway 3,076★, tbxark/mcp-proxy 695★, MikkoParkkola/mcp-gateway, etc.) exist primarily to fill gaps the protocol doesn't address: transport bridging, tool aggregation, auth layers, and progressive discovery.

3. **TypeScript dominates** — 66M+ monthly npm downloads vs the Python-focused current standard. Go (tbxark), Rust (agentgateway, MikkoParkkola), and C# (microsoft/mcp-gateway) all have production-grade MCP implementations.

4. **Context window bloat is existential** — Perplexity's CTO reports 40-50% of context consumed by tool descriptions. The meta-gateway pattern (14 meta-tools instead of 100+) proves that on-demand discovery saves 85-89% tokens.

5. **Embedded MCP is mainstream** — Obsidian plugins (337★ aaronsb), VS Code extensions (372★ juehang, 214★ BifrostMCP), and game engines (86★ Godot) embed MCP servers. Every implementation reinvents the same HTTP server + session management layer.

## DECISION

### 1. Language-Agnostic Core with Per-Language Implementation Notes

**Problem:** Current standard is Python/FastMCP-exclusive. 66M+ monthly TypeScript SDK downloads prove the ecosystem is multi-language.

**Decision:** Refactor the standard into a **language-agnostic CORE** (rules, patterns, contracts) with **per-language implementation appendices** (Python/FastMCP, TypeScript/Node.js, and stub sections for Go, Rust, C#). The core remains the SSOT for architectural rules; language appendices provide canonical code templates.

**Rationale:** Tool design rules (two-layer pattern, response contracts, risk annotations, manifest schema) are language-agnostic. What changes is the implementation: Python uses FastMCP decorators, TypeScript uses `McpServer.registerTool()`, Go uses struct-based `AddTool()`. Documenting these per-language eliminates the "but how do I do this in TypeScript?" gap.

### 2. Streamable HTTP as Primary Transport Architecture

**Problem:** Current standard treats SSE as primary, mentions Streamable HTTP only in passing. The 2026-07-28 RC makes Streamable HTTP the ONLY remote transport.

**Decision:** Add a new "Transport Architecture" section covering:

- **Stateless server design** — no sticky sessions, `Mcp-Session-Id` optional, `Mcp-Method`/`Mcp-Name` headers for routing
- **EventStore pattern** — correct implementation of resumable SSE streams (fixing the reference-implementation bug from modelcontextprotocol/servers#4087)
- **Multi-transport servers** — one codebase, multiple transports (stdio for local dev, Streamable HTTP for production)
- **Session lifecycle** — creation, validation, expiry, termination via DELETE
- **Resumability** — `Last-Event-ID`, per-stream event IDs, replay semantics
- **OAuth 2.1 PKCE** — standard auth flow with Dynamic Client Registration

**Rationale:** The 2026-07-28 stateless rework is the largest spec change since MCP launched. Server design must adapt. The current standard's stateful assumptions (handshake → session → tools) must be updated for stateless operation where any instance handles any request.

### 3. Composable Middleware Pipeline

**Problem:** Every MCP server reinvents auth, rate limiting, logging, CORS, and observability from scratch. The proxy repos prove this is the #1 boilerplate problem.

**Decision:** Add a "Middleware Pipeline" section defining a **composable middleware chain** pattern:

```
Request → [Auth] → [RateLimit] → [Logging] → [Validation] → [Tool Handler] → Response
```

Define standard middleware interfaces:
- `AuthMiddleware` — Bearer token, API key, OAuth 2.1
- `RateLimitMiddleware` — per-tool, per-session quotas
- `LoggingMiddleware` — structured logging with correlation IDs
- `ValidationMiddleware` — input schema validation
- `ObservabilityMiddleware` — OpenTelemetry spans, metrics

**Rationale:** Express.js popularized middleware because it's the right abstraction for HTTP services. MCP servers are HTTP services (Streamable HTTP). The middleware pattern eliminates the 100+ lines of boilerplate every server currently writes for auth + CORS + logging.

### 4. Progressive Tool Discovery

**Problem:** `tools/list` returns everything. Agents burn 40-50% of context on tool descriptions they never use. The meta-gateway pattern (MikkoParkkola/mcp-gateway, lazy-mcp) proves hierarchical discovery saves 85-89% tokens.

**Decision:** Add "Progressive Tool Discovery" as a design pattern:

- **Category-level listing** — `tools/list_categories` returns `{"categories": [{"name": "filesystem", "description": "...", "tool_count": 5}]}`
- **On-demand schema** — agents fetch full tool schema only when needed via `tools/get_schema`
- **Tool search** — `tools/search {"query": "restart"}` returns matching tools with descriptions
- **Compact listing** — `tools/list?detail=minimal` returns names + one-line descriptions only
- **Lazy registration** — tools registered but schemas fetched on first use (lazy-mcp pattern)

**Rationale:** The meta-gateway pattern is not a workaround — it's the correct architecture. The protocol should support hierarchical discovery natively. The 2026-07-28 spec's `ttlMs`/`cacheScope` on list results makes this pattern even more viable (clients cache category listings).

### 5. Transport Bridging and Aggregation Patterns

**Problem:** 25+ proxy repos exist primarily because the base MCP model has no native aggregation or transport bridging. Every aggregator invents its own collision resolution.

**Decision:** Add "Multi-Server Patterns" section covering:

- **Tool namespacing** — `{server_name}/{tool_name}` convention for aggregated tools
- **Transport bridge** — canonical pattern for stdio↔SSE↔Streamable HTTP conversion
- **Aggregation hub** — single endpoint exposing tools from N backend servers
- **Meta-protocol gateway** — fixed meta-tools replacing N variable backend tools
- **Health aggregation** — `/health` returning per-backend status
- **Error fan-out** — partial failure semantics when one of N backends fails

**Rationale:** These patterns exist in production across 25+ repos. Standardizing them eliminates fragmentation and provides a migration path for proxy authors to converge.

### 6. Embedded MCP Server Pattern

**Problem:** Obsidian plugins, VS Code extensions, and game engines embed MCP servers but have no standard pattern. Every implementation writes the same HTTP server + session management boilerplate.

**Decision:** Add "Embedded MCP Server" pattern covering:
- **Plugin lifecycle integration** — start server on host activation, stop on deactivation
- **Port management** — auto-port-detection, conflict resolution
- **In-app configuration** — settings UI instead of JSON config files
- **`.mcpb` installer pattern** — clickable file that auto-configures MCP clients
- **Certificate management** — self-signed cert generation for HTTPS

**Rationale:** The embedded pattern represents a massive developer audience (Obsidian alone has 337★ for its MCP plugin). Standardizing removes the biggest barrier to entry.

### 7. Server Generator and Scaffolding

**Problem:** Zero tooling exists to bootstrap a best-practice MCP server. Every project copy-pastes from `modelcontextprotocol/servers`.

**Decision:** Define a `create-mcp-server` specification — the CLI interface that a generator tool SHOULD implement:
- `create-mcp-server my-server --language typescript --transport streamable-http`
- Project layout, tool templates, test fixtures, CI config
- Middleware pre-configured (auth, rate limiting, logging)
- Health endpoint, Dockerfile, `.env.example` generated automatically

**Rationale:** `create-react-app`, `create-next-app`, `npm init` — every mature ecosystem has scaffolding. MCP has 13,000+ servers and no scaffolding. This is an obvious gap.

### 8. TypeScript/Node.js Implementation Appendix

**Problem:** Current standard has Python/FastMCP implementation notes but nothing for the dominant SDK (66M+ downloads).

**Decision:** Add a "TypeScript/Node.js Implementation" appendix covering:
- `McpServer` high-level API pattern
- `StreamableHTTPServerTransport` setup
- Express/Hono/Fastify middleware adapters
- `registerTool()` with Zod schemas and annotations
- `ResourceTemplate` for dynamic resources
- `EventStore` implementation for resumability
- Testing with `vitest` + mock transports
- Project structure: `src/tools/`, `src/resources/`, `src/transports/`

**Rationale:** TypeScript has the largest MCP developer base. A standard that ignores it is incomplete.

## CONSEQUENCES

**Positive:**
- Language-agnostic core + per-language appendices serve the entire MCP ecosystem
- Streamable HTTP architecture prepares servers for the 2026-07-28 stateless spec
- Middleware pipeline eliminates the #1 boilerplate problem
- Progressive discovery directly addresses the 40-50% context bloat crisis
- Multi-server patterns absorb the proxy ecosystem into the standard
- Embedded pattern opens MCP to plugin/extension developers
- Scaffolding spec provides a target for tooling authors

**Negative:**
- Standard size increases significantly (from ~1500 to ~3000+ lines)
- Per-language appendices require maintenance as SDKs evolve
- Some patterns (progressive discovery, namespacing) require protocol changes not yet in spec

**Risks:**
- 2026-07-28 spec is still a release candidate — details may change
- Progressive discovery and namespacing are not yet in the MCP spec
- Multi-language appendices risk staleness if not maintained

**Mitigations:**
- Monitor 2026-07-28 spec for final changes before standard reaches `stable`
- Mark protocol-dependent patterns as `[PROPOSED]` until spec adoption
- Per-language appendices reference SDK versions explicitly

## STATUS

- `proposed: 2026-06-06` — Based on comprehensive analysis of 25+ MCP proxy repos, official servers, Streamable HTTP spec, embedded MCP patterns, and 2026-07-28 RC
- `accepted: pending` — Requires team review

## CHANGELOG

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0.0 | 2026-06-06 | Initial ADR documenting all v2.0 architecture decisions | Sisyphus |

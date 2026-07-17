---
name: mcp-server-architect
description: Design, implement, review, and harden MCP servers across Python and .NET with explicit contracts, trust boundaries, and production verification.
---

# MCP server architect

Use this skill for new MCP servers, transport migrations, security reviews, SDK upgrades, or production-readiness audits.

## Workflow

1. Define consumer outcomes, tool boundaries, risk, authorization, and response contracts before choosing an SDK.
2. Separate domain operations from MCP registration and transport.
3. Choose transport and session state deliberately; prefer stateless HTTP when sessions are unnecessary.
4. Define deadlines, cancellation, idempotency, retry, error, and partial-failure semantics.
5. Add authentication, per-tool authorization, confused-deputy controls, input validation, and secret boundaries.
6. Design consumer-friendly discovery, summaries, pagination, stable identifiers, and empty-success behavior.
7. Implement observability with correlation, traces, metrics, audit events, and sanitized logs.
8. Test domain, schema, policy, registration, transport, and representative real-client workflows in separate layers.
9. Build and smoke-test the deployment artifact.
10. Review the relevant SDK profile and cross-language incident map before accepting framework-specific code.

Read `STANDARD.md`, then use `references/python-fastmcp.md` or `references/dotnet-mcp.md`. Use `testing-strategy.md`, `security-and-operations.md`, and `problem-solution-matrix.md` for production work.

## Constraints

- Do not place business logic only inside decorated tool functions.
- Do not inspect private SDK registries as a stable contract.
- Do not use stdout for logs on stdio transport.
- Do not build shell commands from agent-controlled text.
- Do not swallow cancellation or convert it into generic failure.
- Do not claim parity between SDKs without mapping the invariant to each platform's lifecycle and DI model.

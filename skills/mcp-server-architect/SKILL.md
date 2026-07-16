---
name: mcp-server-architect
description: Design, implement, refactor, or review Model Context Protocol servers. Use for MCP tools, resources, prompts, transports, authorization, Python FastMCP, C#/.NET SDK, testing, migration from legacy SSE, and agent-friendly capability design.
---

# MCP server architect

Use `mcp-server-standards.md` for language-neutral rules.

## Route the implementation

| Need | Load |
|---|---|
| Python server | `references/python.md` |
| C#/.NET server | `references/dotnet.md` |
| Authentication, permissions, destructive tools | `references/security.md` |
| Lessons from the author's production-style servers | `references/reference-server-lessons.md` |
| Protocol migration or version compatibility | `references/protocol-versions.md` |

## Procedure

1. Inspect the consumer, deployment boundary, protocol version, transport, authentication, data sensitivity, and expected workload.
2. Model user workflows before defining primitives. Prefer a small coherent surface over one wrapper per upstream endpoint.
3. Decide whether each capability belongs in a tool, resource, prompt, or server metadata.
4. Define input schema, native MCP result, errors, annotations, authorization, idempotency, timeout, cancellation, pagination, and observability.
5. Keep domain logic independent of MCP registration and transport.
6. Implement the smallest vertical slice and verify it with an official inspector or SDK client.
7. Add contract, policy, transport, integration, and security tests appropriate to the risk.
8. Measure tool-selection quality and payload size for large catalogs.
9. Document compatibility workarounds as profiles, not universal protocol rules.

## Defaults

- Local child process: stdio.
- Remote server: Streamable HTTP with exact host/origin policy and authentication.
- New server: stable protocol profile; preview revisions require an explicit opt-in.
- Tool result: native MCP content plus `structuredContent` when structured output helps the consumer.
- Write capability: disabled or unauthorized by default until an explicit policy enables it.
- Destructive capability: server-side authorization and explicit user confirmation; annotations alone are insufficient.

## Do not

- Do not require legacy HTTP+SSE for a new server.
- Do not require a custom `success` envelope when native MCP result and `isError` are sufficient.
- Do not expose a second REST API merely for testing unless a real non-MCP consumer needs it.
- Do not treat annotations or tool descriptions as an authorization boundary.
- Do not catch every exception and convert programmer bugs into successful protocol responses.
- Do not force Python module layouts, port counts, response wrappers, or test frameworks into the language-neutral core.
- Do not copy package versions into prose.

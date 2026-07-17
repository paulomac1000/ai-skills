---
name: mcp-server-architect
description: Design, implement, refactor, or review secure and agent-friendly MCP servers in any language, including capability contracts, transport boundaries, authorization, reliability, and tests.
---

# MCP server architect

Read `STANDARD.md` before implementation.

## Workflow

1. Identify user workflows, consumers, deployment boundaries, data sensitivity, side effects, and failure impact.
2. Model tools, resources, and prompts by user semantics rather than by upstream endpoint shape.
3. Define names, descriptions, schemas, result shapes, errors, pagination, cancellation, authorization, idempotency, and observability.
4. Keep domain logic independent of MCP registration and transport.
5. Implement one vertical slice and test it with a real client or protocol inspector.
6. Add policy, contract, integration, transport, and security tests according to risk.
7. Measure selection quality and context cost when the capability catalog is large.
8. Document compatibility adapters without turning them into defaults.
9. Verify the server's behavior, not only schema registration.

## Defaults

- Use stdio for local child-process integrations.
- Use Streamable HTTP for new remote deployments when supported by the selected SDK and client set.
- Prefer native MCP content and structured output over custom envelopes.
- Deny write, destructive, raw-command, filesystem, and sensitive capabilities until explicitly authorized.
- Bound output, time, retries, concurrency, and external calls.
- Return sanitized errors with stable categories and correlation information.

## Constraints

- Do not expose upstream APIs one endpoint at a time without workflow design.
- Do not trust annotations as authorization.
- Do not write protocol traffic and logs to the same stdout stream.
- Do not retry unknown or non-idempotent mutations automatically.
- Do not leak secrets, internal stack traces, or unnecessary sensitive data.

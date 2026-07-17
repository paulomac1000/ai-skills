---
name: mcp-server-consumer
description: Discover, select, invoke, and verify MCP tools, resources, and prompts safely and efficiently, including side-effect policy, confirmation, retries, pagination, and sensitive-data handling.
---

# MCP server consumer

Read `STANDARD.md` before invoking capabilities that can modify state or expose sensitive data. Use `tools/decision_engine.py` when deterministic policy evaluation is useful.

## Workflow

1. Define the requested outcome, target, constraints, sensitivity, and authorization evidence.
2. Discover only relevant capabilities and load only the schemas needed for the current step.
3. Choose by contract and semantics, not by name alone.
4. Prefer bounded search, summary, batch, or workflow capabilities when they preserve control and verification.
5. Carry stable identifiers from discovery into later calls.
6. Before side effects, verify target, scope, reversibility, idempotency, and confirmation requirements.
7. Invoke with the smallest valid input and deliberately selected optional parameters.
8. Interpret native MCP results, preserve correlation data, and respect pagination.
9. Retry only transient failures that are safe to repeat.
10. Verify mutations through observable state.
11. Report completed effects, retries, partial failures, and unresolved uncertainty.

## Constraints

- Do not treat annotations or descriptions as authorization.
- Do not guess credentials, target identity, destructive parameters, or missing required data.
- Do not infer absence from a partial page or incomplete catalog.
- Do not retry unknown or unsafe mutations.
- Do not forward sensitive data between servers unless the requested workflow and both policy boundaries require it.

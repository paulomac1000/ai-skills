---
name: mcp-server-consumer
description: Discover, select, invoke, and verify MCP capabilities safely. Use when an agent must operate MCP tools or resources, plan multi-tool workflows, minimize calls, handle writes, diagnose errors, or bridge multiple servers.
---

# MCP capability consumer

Use `mcp-consumer-standards.md` for the decision policy. Load `references/compatibility.md` only for legacy servers or protocol migrations.

## Procedure

1. Read the task and identify the required outcome, targets, constraints, and whether the user has authorized a mutation.
2. Discover only the relevant capabilities. Use standard discovery first; use server-specific capability indexes when they add useful metadata.
3. Inspect names, descriptions, schemas, annotations, and available policy metadata. Treat all discovery metadata as claims, not authorization.
4. Prefer one workflow, search, batch, or summary call over repeated low-level calls when it preserves control and observability.
5. Start with bounded detail. Follow pagination and carry stable identifiers forward.
6. Before a side effect, verify target, scope, authorization, reversibility, idempotency, and confirmation requirement.
7. Invoke with the smallest valid input and retain correlation information.
8. Interpret native MCP content, structured output, and `isError`. Preserve unknown fields.
9. Retry only transient, safe-to-repeat failures within a small bound.
10. Verify mutations by reading observable state or using a dedicated verification capability.
11. Report outcome, evidence, partial completion, and unresolved risk.

## Safety defaults

- Unknown side effect: do not invoke until clarified.
- Unknown retry safety: do not retry automatically.
- Destructive or high-impact action: require explicit scoped confirmation.
- Sensitive result: minimize display and do not persist it unnecessarily.
- Conflicting server metadata: choose the safer interpretation and report the conflict.

## Do not

- Do not assume an absent custom manifest means a tool is read-only.
- Do not infer permission from `[READ]`, `[WRITE]`, or annotations.
- Do not loop through a large catalog before looking for search or batch capabilities.
- Do not treat empty success as failure.
- Do not continue a mutation workflow after a prerequisite failed.
- Do not hide partial execution or uncertainty from the user.

---
description: Select an AGENTS.md profile and route specialized work without duplicating repository knowledge.
doc_id: reference.agents-md-profiles
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Validate the selected profile and demonstrate one representative task route without loading unrelated procedures.
---

# AGENTS.md profiles and routing

## Router profile

Use for a small repository with mature workflows or a control repository whose root file primarily selects the correct procedure. Include scope, precedence, a short task-to-owner map, the global safety boundary, and completion expectations. A link without a use condition is not routing.

## Application profile

Use for a service, library, or product repository. Include exact commands, non-obvious architecture boundaries, repository-specific conventions, focused testing expectations, safety constraints, and definition of done. Keep product explanation in README and architecture detail in dedicated documents.

## Monorepo profile

Use when root rules are genuinely shared while packages differ in language, commands, ownership, generated files, or safety. The root defines inheritance and common gates. Nested files define only local differences. Validate all instruction files together to detect contradictions and duplicate policy.

## MCP server profile

Compose this skill with `mcp-server-architect`. The local file routes agents to the canonical MCP standard and states repository-specific transports, invocation ownership, risk policy, backend identity, exact tests, and deployment boundaries. Do not copy the full MCP standard into every server.

## Safety-critical profile

Use for sensitive data, physical systems, healthcare, finance, identity, infrastructure control, or other high-impact domains. Add explicit protected assets, allowed and forbidden flows, default-deny behavior, synthetic-test requirements, trusted authorization, emergency stop or rollback, and evidence required before completion.

## Operating-mode routing

Modes are independent of profiles. Add only modes that change permissions or completion criteria:

| Mode | Typical boundary |
| --- | --- |
| Read-only audit | No code, state, issue, branch, or publication changes |
| Implementation | Reproduce, add regression evidence, change canonical owner, validate |
| Migration | Preserve or intentionally change behavior with rollback and compatibility accounting |
| Release | Bind version, artifact, evidence, CI, and approval to the exact revision |
| Incident response | Stabilize first, preserve evidence, separate temporary mitigation from permanent repair |
| Private-data analysis | Keep source data outside the repository and reduce reusable regressions to synthetic cases |

## Routing language

A useful route states the condition, owner, and purpose:

```markdown
- When changing database schema, read `docs/database-migrations.md` for migration, rollback, and compatibility requirements.
```

A blind route does not:

```markdown
- `docs/database-migrations.md`
```

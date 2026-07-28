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

Use for a small repository with mature workflows or a control repository whose root file primarily selects the correct procedure. Include scope, a short task-to-owner map, the global safety boundary, and completion expectations. A link without a use condition is not routing.

## Application profile

Use for a service, library, or product repository. Include exact commands, non-obvious architecture boundaries, repository-specific conventions, focused testing expectations, safety constraints, and definition of done. Keep product explanation in README and architecture detail in dedicated documents.

## Monorepo profile

Use when root rules are genuinely shared while packages differ in language, commands, ownership, generated files, or safety. The root defines the intended inheritance model for the selected platform and common gates. Nested files define only local differences.

Run the validator on the root and every nested file in one invocation. It detects bounded lexical and structural conflicts, duplicated sections, and empty local overlays; it cannot prove arbitrary semantic equivalence, so manual platform-aware review remains required.

## MCP server profile

This profile activates the conditional `mcp-server-architect` dependency declared in `manifest.yaml`. Load that skill before authoring. The local file routes agents to the canonical MCP standard and states only repository-specific transports, invocation ownership, risk policy, backend identity, exact tests, and deployment boundaries.

## Safety-critical profile

Use for sensitive data, physical systems, healthcare, finance, identity, infrastructure control, or other high-impact domains. Add explicit protected assets, allowed and forbidden flows, default-deny behavior, synthetic-test requirements, trusted authorization, emergency stop or rollback, and evidence required before completion.

## Operating-mode routing

Modes are independent of profiles. Add only modes that change permissions or completion criteria:

| Mode | Typical boundary |
| --- | --- |
| Read-only audit | No code, state, issue, branch, or publication changes |
| Implementation | Reproduce, add regression evidence, change the canonical owner, validate |
| Migration | Preserve or intentionally change behavior with rollback and compatibility accounting |
| Release | Bind version, artifact, evidence, CI, and approval to the exact revision |
| Incident response | Stabilize first, preserve evidence, separate mitigation from permanent repair |
| Private-data analysis | Keep source data outside the repository and reduce regressions to synthetic cases |

## Routing language

A useful route states the condition, owner, and purpose:

```markdown
- When changing database schema, read [the migration contract](docs/database-migrations.md) for rollback and compatibility requirements.
```

A blind route does not:

```markdown
- [Database migrations](docs/database-migrations.md)
```

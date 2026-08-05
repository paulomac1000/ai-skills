---
description: Select an AGENTS.md layout and domain profile, then route specialized work without duplicating repository knowledge.
doc_id: reference.agents-md-profiles
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Validate the selected layout and domain profile together and demonstrate one representative task route without loading unrelated procedures.
---

# AGENTS.md profiles and routing

Layout and domain are independent axes. Do not use one profile name to hide the other decision.

## Layout axis

### Single layout

Use one root file when no subtree needs materially different commands, ownership, technology, generated-file rules, or safety boundaries.

### Monorepo layout

Use shared root rules plus local subtree differences. The root defines the intended inheritance model for the selected platform and common gates. Nested files define only local differences.

Run the validator on the root and every nested file in one invocation with `--layout monorepo`. Tree checks remain active when the domain profile is `application`, `mcp-server`, or `safety-critical`.

## Domain profile axis

### Router profile

Use for a small repository with mature workflows or a control repository whose root file primarily selects the correct procedure. Include scope, a short task-to-owner map, the global safety boundary, and completion expectations. A link without a use condition is not routing.

### Application profile

Use for a service, library, or product repository. Include exact commands, non-obvious architecture boundaries, repository-specific conventions, focused testing expectations, safety constraints, and definition of done. Keep product explanation in README and architecture detail in dedicated documents.

### MCP server profile

This profile activates the conditional `mcp-server-architect` dependency declared in `manifest.yaml`. Load that skill before authoring. The local file routes agents to the canonical MCP standard and states only repository-specific transports, invocation ownership, risk policy, backend identity, exact tests, and deployment boundaries.

### Safety-critical profile

Use for sensitive data, physical systems, healthcare, finance, identity, infrastructure control, or other high-impact domains. Add explicit protected assets, allowed and forbidden flows, default-deny behavior, synthetic-test requirements, trusted authorization, emergency stop or rollback, and evidence required before completion.

## Composition examples

- `--layout monorepo --profile application` validates root and package-local commands.
- `--layout monorepo --profile mcp-server` keeps tree checks and adds MCP safety and risk contracts.
- `--layout monorepo --profile safety-critical` keeps tree checks and requires protected-data and fail-closed safety contracts in root and local scopes.

The legacy `--profile monorepo` input maps to `--layout monorepo --profile application` only for compatibility. New instructions and examples use the two-axis form.

## Operating-mode routing

Modes are independent of layout and domain profiles. Add only modes that change permissions or completion criteria:

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

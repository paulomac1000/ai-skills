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


## Trigger-safe progressive routing

A conditional route must be knowable before its first governed action. Keep the trigger on an always-visible surface unless the selected platform has verified pre-load metadata that is visible before destination loading. Do not put the only “read me when…” instruction inside the unopened destination.

When extraction needs mechanical proof, pair one route marker in the applicable `AGENTS.md` with one destination marker:

```markdown
<!-- agents-md: route owner="docs/release.md" when="when a candidate becomes release-ready" purpose="release identity and landing gates" invoke-owner="Makefile" -->
- When a candidate becomes release-ready, read [the release contract](docs/release.md) before publication.

<!-- destination: docs/release.md -->
<!-- agents-md: conditional-owner -->
```

The marker is a structural declaration, not a substitute for readable prose. `owner`, `when`, and `purpose` are required. `invoke-owner` is optional and should point to the launcher, manifest, task catalog, or other canonical file from which the exact supported invocation is discovered. The repository auditor rejects missing/stale/symlinked owners, marked owners with no reachable route, duplicate route owners, and a route whose destination is not marked.

For transition-time loading, evaluate the route again when task state changes. Representative transitions include implementation → migration, implementation → external/destructive effect, validation → user decision, normal operation → recovery, candidate → release, and ordinary work → sensitive-data handling.

Negative routing matters too: when a task never reaches the trigger, do not preload the full migration/release/recovery procedure just because it is catalogued.

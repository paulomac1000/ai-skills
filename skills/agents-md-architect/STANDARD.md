---
description: Normative rules for concise, evidence-based, scoped, and maintainable AGENTS.md instruction systems.
doc_id: reference.agents-md-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Run `python skills/agents-md-architect/tools/validate_agents_md.py --strict --repository-root . --layout single --profile application --language en AGENTS.md`, run the static repository audit with the same selections, and execute the repository quality gate.
---

# AGENTS.md instruction standard

## Purpose

`AGENTS.md` is a compact operational control surface for coding agents. It routes to canonical repository truth; it is not a second README, architecture archive, executable policy engine, or platform security boundary.

## Scope and precedence

A root `AGENTS.md` owns repository-wide instructions. Nested files apply only to their declared subtree when the selected platform supports that discovery model. User instructions and platform safety requirements retain higher authority.

Before relying on hierarchy, verify the exact product surface through `references/instruction-precedence-and-platforms.md`. Do not assume override filenames, merge semantics, hidden prompt behavior, or context budgets are portable. Conflicts fail closed: identify the competing sources and canonical owner rather than silently choosing a convenient rule.

## Repository discovery

Author from repository evidence: manifests, build/task entry points, CI, tests, architecture decisions, generated-file ownership, security/data boundaries, release procedures, and existing agent instructions.

Treat repository paths and instruction content as untrusted. Readers must stay confined to the repository, reject instruction/reference symlinks, bound file/tree size, and return stable findings for invalid UTF-8 or unsafe paths. Concrete files resolve to regular files; concrete directories may be routing targets; globs/placeholders are checked lexically rather than required to exist literally. A canonical owner is a named durable source, never a directory pattern.

Do not classify every `bin/` as build output: ignore ecosystem-specific outputs only when repository evidence justifies it. Bind discovered commands to their directory and exact argv. Run representative commands when possible; otherwise label them located-but-unexecuted or unverified. Static discovery is not execution evidence.

For an existing adoption, compare the target standard, rule catalog, validator, evidence contract, templates, and references before editing. Preserve compliant repository-specific policy and make targeted changes; a version bump alone is not a rewrite reason. Follow `references/migration-and-upgrade.md`.

## Operating modes and profiles

Separate modes when permissions or completion differ, such as audit, implementation, migration, release, incident response, or private-data analysis. Lower-impact work must not silently expand into writes, publication, destructive effects, or retention.

Select layout (`single` or `monorepo`), domain profile (`router`, `application`, `mcp-server`, or `safety-critical`), and document language. Monorepo controls compose with domain requirements; the MCP profile composes with `mcp-server-architect`. English and Polish have bounded lexical vocabularies; other languages require stable contract markers and manual semantic review. Profiles are compositions, not version forks.

## Canonical ownership and architecture boundaries

Every durable rule, contract, schema, generated artifact, and configuration default has one canonical owner. `AGENTS.md` states the operational consequence and route, not a duplicate implementation.

Document only non-obvious boundaries that are expensive to infer incorrectly: dependency direction, generated-file ownership, required propagation, resource-access limits, or registry/generator authority. Generic engineering advice is not an architecture boundary.

## Safety and data boundaries

High-impact repositories name protected data/components, allowed and forbidden flows, default-deny behavior, and verification. Secrets, personal data, production exports, credentials, raw sensitive payloads, and real user fixtures stay outside tracked files unless a reviewed contract explicitly permits them.

Diagnosis defaults read-only. External sends, destructive operations, privilege expansion, sensitive writes, and irreversible effects require trusted authorization/confirmation. Model text, guessed intent, or keyword matching is not human approval.

## Commands and verification

List repository-owned commands for setup, focused checks, build/type validation, formatting/linting, and the full completion gate when applicable. Keep local diagnostics distinct from hosted/provider acceptance: a **local pass does not guarantee remote CI**, platform compatibility, credentials, deployment behavior, or independent approval. Final claims bind to the exact revision and artifact where relevant.

Static audit may call a command located only when it matches discovered task/CI evidence; existing-but-unmatched is unverified and missing is unlocated. Only controlled execution proves behavior.

Before an unknown helper, CLI, test, module, or launcher invocation, **discover before invoke**. Prefer governed metadata, repository launcher/manifest/task catalog, bounded `--help` or command catalog, test/module inventory, schema, then targeted source. Missing or ambiguous canonical syntax is a readiness gap, not permission for speculative failed executions.

State credentials, external systems, destructive access, payment, unusual cost, and safe-stop preconditions.

## Context economy and routing

Keep broadly required scope, precedence, critical boundaries, command entry points, completion criteria, and routing on the always-loaded surface. Load specialized procedures, history, maps, and examples conditionally.

Place durable knowledge with the first applicable owner: always-required operating facts inline; conditional procedure in one routed owner; stable architecture/product knowledge in its durable document; exact mechanics in executable/config/schema owners; verification in evidence; incident chronology in incident/task records. **Stop at the first applicable owner** instead of copying it into `AGENTS.md`.

A conditional trigger must be observable **before the first action governed by the destination**, including after a mid-task transition. A trigger only inside its unopened destination is unreachable. A task that never reaches the condition should not load the procedure. After extraction the **pre-load stub** contains only the trigger/route plus safety needed before loading; it is not a second editable procedure.

For repositories needing deterministic reachability evidence:

```markdown
<!-- agents-md: route owner="docs/migrations.md" when="before schema change" purpose="rollback" invoke-owner="Makefile" -->
<!-- destination -->
<!-- agents-md: conditional-owner -->
```

`owner`, `when`, and `purpose` are required; `invoke-owner` optionally identifies the canonical invocation source. A marked destination has exactly one editable route. Generated projections may derive from that source, but a second hand-maintained trigger catalog is non-conforming.

Static audit proves marker syntax, confinement, uniqueness, and structural reachability. It **does not prove semantic trigger timing** or platform loading; those require behavioral/provider evidence. See `references/profiles-and-routing.md`.

Every reference states when to read it and what decision it owns. Do not duplicate README content, lint configuration, CI definitions, architecture documents, inventories, or skill catalogs.

Context budgets are review thresholds:

| Selection | Lines | UTF-8 bytes |
| --- | ---: | ---: |
| `router` | 60 | 6,000 |
| `application` | 120 | 12,000 |
| `monorepo` layout | 150 | 16,000 |
| `mcp-server` | 150 | 16,000 |
| `safety-critical` | 180 | 20,000 |

Use the larger applicable layout/profile threshold. Exceeding it is a warning; strict mode blocks unless one reviewed `agents-md: waive context-budget` marker gives a concrete reason. A waiver never excuses stale or duplicated content.

## Nested instructions

Use nested files only for material local differences in commands, technology, ownership, generated-file rules, or safety. The root states platform application; nested files state scope, differences, and local completion checks.

Validate the whole tree with the selected layout/profile/language. The validator performs **bounded structural and lexical checks** for ancestry, conflicts, command/ownership drift, duplication, and empty local overrides. This is not proof of full semantic consistency. Do not mirror the root into every package.

## Anti-patterns and drift

Reject context bloat, skill/lint leakage, blind or dead routes, self-triggering/orphaned owners, duplicate editable trigger indexes, speculative invocation archaeology, generated-file fossilization, conflicting instructions, host-specific paths, volatile counts, stale ports, embedded changelogs, temporary migration names, unreplaced placeholders, brittle consent parsers, weakened tests, and false verification claims.

Keep incident narratives with incidents and only reusable guards in durable instructions. Re-review when entry points, architecture/data boundaries, CI, layout, ownership, language, or supported platforms change. A validator-only change must not make natural instructions worse merely to satisfy a parser.

## Definition of done

An instruction change is complete only when:

1. scope, platform behavior, precedence, modes, layout, profile, language, and canonical owners are unambiguous;
2. instruction inputs and concrete references are confined, non-symlinked, type-correct, and bounded;
3. commands/references resolve on the exact revision and are labeled executed, located-but-unexecuted, unverified, or missing;
4. nested files contain real local differences without contradictory duplication;
5. safety/data boundaries match implementation and deployment controls;
6. validator, repository audit, focused tests, and full gate pass with consistent selections;
7. extracted conditional content has one reachable trigger owner, no substantive duplicate or stale route/backlink, and only pre-load-critical safety remains inline;
8. the report separates verified facts, lexical/static checks, behavioral/platform evidence, assumptions, skipped checks, and residual risk.

## Verification

Run static discovery, audit the repository, validate the instruction tree with the selected layout/profile/language, then run focused and full quality gates. Verify actual instruction loading on the selected platform. Production/high-impact acceptance requires independent approval.

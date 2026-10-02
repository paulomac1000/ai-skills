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

This standard defines how repository instructions for coding agents are discovered, scoped, structured, delegated, verified, and maintained. `AGENTS.md` is an operational control surface, not a replacement for product documentation, executable policy, or platform security controls.

## Scope and precedence

A root `AGENTS.md` states the repository-wide contract and the scope it governs. A nested file may apply to its subtree only when the selected agent platform supports that discovery model. Direct user instructions and platform-level safety requirements retain higher authority than repository content.

Before relying on hierarchy, follow `references/instruction-precedence-and-platforms.md` and verify the exact product surface. Portable guidance must not assume tool-specific override files, hidden prompt behavior, or identical merge semantics. Platform adapters remain thin and must not duplicate the portable core.

Conflicts fail closed. Identify the competing sources and canonical owner; do not silently select the easier rule.

## Repository discovery

Instructions are derived from repository evidence. Before creating or materially changing them, inspect applicable manifests, build files, task runners, CI workflows, test entry points, architecture decisions, generated-file ownership, security boundaries, data locations, release procedures, and existing agent instructions.

Treat the repository root, input instruction files, referenced paths, and symlinks as untrusted. Static tools must verify confinement before reading and must not follow instruction-file or reference symlinks. Concrete file references must resolve to regular files; concrete directory references may resolve to real directories for routing or layout; path patterns, globs, and placeholders are validated lexically rather than required to exist literally. A canonical owner remains a concrete named file or other explicit durable owner, never a directory or pattern. Invalid UTF-8, oversized files, and oversized instruction trees fail with stable findings rather than tracebacks.

Discovery must not treat every directory name as universal build output. In particular, root `bin/` scripts and language entry points remain discoverable; ecosystem-specific output such as `.NET` project `bin/` and `obj/` directories may be ignored only with project evidence.

Commands must exist on the assessed revision. Unless a command explicitly selects or changes directories, interpret it from the directory containing the applicable `AGENTS.md`. Evidence derived from directory-scoped task definitions must remain bound to the directory containing that definition, and discovered entry points must preserve exact `argv` boundaries. Run representative commands when the environment permits; otherwise label them located-but-unexecuted or unverified and name the missing evidence. Static path discovery is not proof that an exact command ran or that it matches hosted CI. Incident-derived guards belong here only when the failure can recur and is not already eliminated by code or automation.

When upgrading an existing adoption, compare the old and target normative standard, rule catalog, validator behavior, evidence contract, templates, and references before editing prose. A version change alone is not a reason to rewrite a useful canonical `AGENTS.md`. Preserve compliant repository-specific instructions and make targeted integration or evidence changes unless the normative contract or repository boundaries actually changed. Follow `references/migration-and-upgrade.md`.

## Operating modes and profiles

Distinguish modes whose permissions or completion criteria materially differ, including read-only audit, implementation, migration, release, incident response, or private-data analysis. A lower-impact request must not expand silently into writes, publication, destructive operations, or data retention.

Select two independent axes:

- layout: `single` or `monorepo`;
- domain profile: `router`, `application`, `mcp-server`, or `safety-critical`.

The `monorepo` layout adds root/nested inheritance, conflict, duplication, and local-difference checks without replacing domain requirements. A safety-critical or MCP monorepo therefore keeps both tree controls and its domain-specific safety contracts. The `mcp-server` profile composes with the conditional `mcp-server-architect` dependency.

Select the document language using `references/language-and-contract-markers.md`. English and Polish have bounded lexical vocabularies. Other languages require stable `agents-md: contract` markers for strict validation. Lexical analysis must never be described as universal semantic understanding.

Profiles and layouts are composition guidance, not separate versions of the standard.

## Canonical ownership and architecture boundaries

Every durable rule, contract, schema, generated artifact, and configuration default has one canonical owner. `AGENTS.md` summarizes the operational consequence and links to that owner. It does not preserve obsolete behavior through numbered files, parallel current implementations, or undocumented compatibility branches.

State non-obvious architecture boundaries that are expensive to infer incorrectly: dependency direction, generated files that must not be edited, registry or generator ownership, required update propagation, and components that may access specific resources. Generic advice is not an architecture boundary.

## Safety and data boundaries

High-impact repositories name protected data, privileged components, allowed flows, forbidden flows, default-deny behavior, and the checks that prove each boundary. Secrets, personal data, production exports, credentials, raw sensitive payloads, and real user fixtures remain outside tracked files unless an explicit reviewed contract states otherwise.

Read-only operations are the default for diagnosis. External sends, destructive actions, privilege expansion, sensitive writes, and irreversible changes require a trusted authorization and confirmation mechanism. Model-controlled text, guessed intent, or keyword matching is not proof of human approval.

## Commands and verification

List exact commands for setup, the smallest focused check, build or type validation, formatting or linting, and the full completion gate when those operations exist. Prefer repository-owned scripts over duplicated command sequences.

Separate local diagnostics from hosted or provider-backed acceptance. A local pass does not guarantee remote CI, platform compatibility, integration credentials, deployment behavior, or independent approval. Final claims bind to the exact revision and, where applicable, the exact built or published artifact.

A static audit may report an exact command reference as located when it matches a discovered task runner or CI definition. It must report existing-but-unmatched invocations as unverified and missing invocations as unlocated. Only controlled execution proves execution behavior.

Before the first helper, CLI, test, module, or launcher invocation whose supported form is not already current in the loaded contract, **discover before invoke**. Resolve the interface from the nearest canonical owner in this order: governed skill/runtime-dependency metadata; repository launcher, manifest, or task catalog; bounded `--help` or supported-command catalog; test/module inventory; schema/contract; targeted source lookup only when the canonical interface is incomplete. Missing or ambiguous canonical invocation is a readiness gap, not permission for repeated speculative execution.

Commands requiring credentials, external systems, destructive access, payment, or unusual runtime cost state those preconditions and their safe stop behavior.

## Context economy and routing

The root file contains rules needed for most tasks: scope, precedence, core modes, critical boundaries, command entry points, completion criteria, and task routing. Specialized procedures, incident histories, exhaustive maps, and long examples load on demand.

Place new durable knowledge with the first applicable owner:

1. always-required operating facts needed before routing or for nearly every task stay on the always-loaded instruction surface;
2. a named conditional procedure or invariant belongs to one routed skill, reference, or workflow;
3. stable architecture, product, and contributor knowledge stays in its canonical durable document, with only the operational consequence and route in `AGENTS.md`;
4. exact flags, schemas, command mechanics, generated inventories, and configuration stay with executable/config/schema owners when possible;
5. verification results and exact observations stay with evidence owners;
6. incident/task chronology stays in incident, task, or PR evidence after reusable invariants are distilled.

Stop at the first applicable owner rather than copying the fact into a convenient always-loaded file.

A conditional route is conforming only when its trigger is observable **before the first action governed by the destination**. The trigger has one canonical owner. A trigger that exists only inside its own unopened destination is unreachable. The route must still work when the condition appears mid-task—for example implementation becoming migration, validation requiring a user decision, normal work entering recovery, or a candidate entering release. A task that never reaches the condition should not load the unrelated full procedure.

After extraction, the always-loaded **pre-load stub** keeps only (a) the trigger/route and (b) any safety invariant that must hold before or while obtaining the conditional instructions. Do not keep a partial editable copy of the procedure “just in case.”

For repositories that need deterministic reachability evidence, the static auditor supports paired markers. The route marker lives in the applicable always-loaded instruction file and names an exact regular-file owner; the destination opts in with a conditional-owner marker:

```markdown
<!-- agents-md: route owner="docs/database-migrations.md" when="before changing database schema" purpose="rollback and compatibility" invoke-owner="Makefile" -->
- Before changing database schema, read [the migration contract](docs/database-migrations.md) for rollback and compatibility.

<!-- in docs/database-migrations.md -->
<!-- agents-md: conditional-owner -->
```

`owner`, `when`, and `purpose` are required. `invoke-owner` is optional and names the canonical repository file that owns the supported invocation when one exists. Exactly one editable route marker may target a marked conditional owner across the audited instruction tree. A generated projection may be derived from these canonical declarations, but a second hand-maintained trigger catalog is non-conforming.

The static auditor proves marker syntax, path confinement, owner uniqueness, and structural reachability only. It **does not prove semantic trigger timing**, that a platform exposed the trigger before use, or that a model loaded the destination at the right moment; those claims require behavioral and platform evidence.

Every reference states when to read it and what decision it owns. Concrete repository file references resolve to confined, regular, non-symlink files; concrete directory references may resolve to confined, non-symlink directories when the route itself is the useful target. Patterns and placeholders describe families of paths and are not tested as literal files. Do not use a directory or pattern as a substitute for a named canonical owner. Do not duplicate README content, linter configuration, full CI definitions, complete architecture documents, current inventories, or skill catalogs.

Context budgets are review thresholds, not quality scores. The effective threshold is the larger of the selected layout and domain-profile budgets:

| Selection | Review above lines | Review above UTF-8 bytes |
| --- | ---: | ---: |
| `router` | 60 | 6,000 |
| `application` | 120 | 12,000 |
| `monorepo` layout | 150 | 16,000 |
| `mcp-server` | 150 | 16,000 |
| `safety-critical` | 180 | 20,000 |

Exceeding either threshold produces a warning. A strict gate treats that warning as blocking unless the file contains one reviewed waiver with a concrete reason of at least 20 characters:

```markdown
<!-- agents-md: waive context-budget reason="Critical emergency boundaries must remain visible in every session." -->
```

A waiver does not excuse duplicated or stale content.

## Nested instructions

Use nested files only when a subtree has materially different commands, technology, ownership, generated-file rules, or safety boundaries. The root declares how local files are intended to apply for the selected platform. Each local file identifies its scope and contains only differences plus local completion checks.

Validate root and nested files together with `--layout monorepo` and the selected domain profile. The executable validator performs bounded structural and lexical checks for ancestry, conflicting generated-file and test-integrity directives, command and ownership drift, duplicated sections, and files with no local difference. English and Polish conflict vocabularies are bounded; other languages require markers and manual semantic review. These checks do not prove full semantic consistency.

Do not mirror the complete root file into every package. A nested file that only links to the root adds no value.

## Anti-patterns and drift

Reject context bloat, skill leakage, lint leakage, blind references, self-triggering or orphaned conditional owners, duplicate editable trigger indexes, speculative command archaeology, generated-file fossilization, conflicting instructions, host-specific absolute paths, volatile counts, stale ports, embedded changelogs, temporary migration names, unreplaced `REPLACE_...` tokens, and claims not tied to evidence.

Reject brittle consent parsers, instructions that weaken tests to obtain green results, and statements equating mock coverage with real integration behavior. Keep incident narratives in incident documents and retain only the durable guard in the instruction system.

Review the instruction tree when build entry points, architecture boundaries, data flows, CI gates, repository layout, ownership, document language, or supported agent platforms change. Structural validation is not proof that every factual claim remains current. If a validator upgrade is the only source of churn, distinguish a real contract change from a parser limitation before making the document less natural or less precise.

## Definition of done

An instruction change is complete only when:

1. scope, platform behavior, precedence, operating modes, layout, domain profile, document language, and canonical owners are unambiguous;
2. input files and concrete repository references are confined and non-symlinked, concrete file references resolve to regular files, concrete directory references resolve to directories, and path-pattern references remain lexically confined within bounded size limits;
3. commands and references resolve on the exact revision and are labeled as executed, located-but-unexecuted, unverified, or missing;
4. nested files contain material local differences without contradictory duplication while retaining domain-specific safety requirements;
5. safety and data boundaries match implementation and deployment configuration;
6. the validator, repository audit, focused tests, and full quality gate pass with the same layout, profile, and language selections;
7. extracted conditional content has one reachable trigger owner, no substantive duplicate procedure, no stale route/backlink, and only necessary pre-load safety facts remain inline;
8. the final report distinguishes verified facts, lexical checks, behavioral/platform evidence, assumptions, skipped checks, and residual risks.

## Verification

Run static discovery, audit the full repository, validate every instruction file together with the selected layout, domain profile, and language, then execute focused and full quality gates. Verify actual instruction loading in the selected platform. Independent approval is required when the instruction system governs production acceptance or high-impact operations.

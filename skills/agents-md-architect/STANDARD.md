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

Treat the repository root, input instruction files, referenced paths, and symlinks as untrusted. Static tools must verify confinement before reading, must not follow instruction-file or referenced-file symlinks, must require repository references to resolve to regular files, and must never execute commands discovered from repository content. Invalid UTF-8, oversized files, and oversized instruction trees fail with stable findings rather than tracebacks.

Discovery must not treat every directory name as universal build output. In particular, root `bin/` scripts and language entry points remain discoverable; ecosystem-specific output such as `.NET` project `bin/` and `obj/` directories may be ignored only with project evidence.

Commands must exist on the assessed revision. Unless a command explicitly selects or changes directories, interpret it from the directory containing the applicable `AGENTS.md`. Evidence derived from directory-scoped task definitions must remain bound to the directory containing that definition, and discovered entry points must preserve exact `argv` boundaries. Run representative commands when the environment permits; otherwise label them located-but-unexecuted or unverified and name the missing evidence. Static path discovery is not proof that an exact command ran or that it matches hosted CI. Incident-derived guards belong here only when the failure can recur and is not already eliminated by code or automation.

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

Commands requiring credentials, external systems, destructive access, payment, or unusual runtime cost state those preconditions and their safe stop behavior.

## Context economy and routing

The root file contains rules needed for most tasks: scope, precedence, core modes, critical boundaries, command entry points, completion criteria, and task routing. Specialized procedures, incident histories, exhaustive maps, and long examples load on demand.

Every reference states when to read it and what decision it owns. Repository references resolve to confined, regular, non-symlink files. Do not use a directory as a substitute for a named canonical owner. Do not duplicate README content, linter configuration, full CI definitions, complete architecture documents, current inventories, or skill catalogs.

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

Reject context bloat, skill leakage, lint leakage, blind references, generated-file fossilization, conflicting instructions, host-specific absolute paths, volatile counts, stale ports, embedded changelogs, temporary migration names, unreplaced `REPLACE_...` tokens, and claims not tied to evidence.

Reject brittle consent parsers, instructions that weaken tests to obtain green results, and statements equating mock coverage with real integration behavior. Keep incident narratives in incident documents and retain only the durable guard in the instruction system.

Review the instruction tree when build entry points, architecture boundaries, data flows, CI gates, repository layout, ownership, document language, or supported agent platforms change. Structural validation is not proof that every factual claim remains current.

## Definition of done

An instruction change is complete only when:

1. scope, platform behavior, precedence, operating modes, layout, domain profile, document language, and canonical owners are unambiguous;
2. input files and referenced paths are confined, regular, non-symlink repository files within bounded size limits;
3. commands and references resolve on the exact revision and are labeled as executed, located-but-unexecuted, unverified, or missing;
4. nested files contain material local differences without contradictory duplication while retaining domain-specific safety requirements;
5. safety and data boundaries match implementation and deployment configuration;
6. the validator, repository audit, focused tests, and full quality gate pass with the same layout, profile, and language selections;
7. the final report distinguishes verified facts, lexical checks, assumptions, skipped checks, and residual risks.

## Verification

Run static discovery, audit the full repository, validate every instruction file together with the selected layout, domain profile, and language, then execute focused and full quality gates. Verify actual instruction loading in the selected platform. Independent approval is required when the instruction system governs production acceptance or high-impact operations.

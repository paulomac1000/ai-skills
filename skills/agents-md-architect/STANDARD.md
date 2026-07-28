---
description: Normative rules for concise, evidence-based, scoped, and maintainable AGENTS.md instruction systems.
doc_id: reference.agents-md-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Run `python skills/agents-md-architect/tools/validate_agents_md.py --strict --profile application AGENTS.md` with the applicable profile and execute the repository quality gate.
---

# AGENTS.md instruction standard

## Purpose

This standard defines how repository instructions for coding agents are discovered, scoped, structured, delegated, verified, and maintained. `AGENTS.md` is an operational control surface for work in a repository, not a replacement for product documentation or executable policy.

## Scope and precedence

A root `AGENTS.md` states the repository-wide contract and the scope it governs. A nested file applies only to its subtree and may refine or replace inherited rules where the agent platform supports hierarchical instructions. Direct user instructions and platform-level safety requirements retain higher authority than repository content.

Portable guidance must not assume tool-specific override filenames, hidden prompt features, or a particular agent runtime. When behavior differs by platform, state the portable rule and route platform-specific mechanics to a named reference.

Conflicts fail closed. The agent identifies the competing sources, determines the canonical owner, and stops rather than silently selecting the easier rule.

## Repository discovery

Instructions are derived from repository evidence. Before creating or materially changing them, inspect applicable manifests, build files, task runners, CI workflows, test entry points, architecture decisions, generated-file ownership, security boundaries, data locations, release procedures, and existing agent instructions.

Commands must exist on the assessed revision. Run representative commands when the environment permits; otherwise label them unverified and name the evidence still required. Repeated review findings and incidents may justify a concise guard only when the failure can recur and is not already eliminated by code or automation.

## Operating modes and profiles

The file distinguishes modes whose permissions or completion criteria materially differ, including read-only audit, implementation, migration, release, incident response, or private-data analysis. It must not allow a lower-impact request to expand silently into code changes, publication, destructive operations, or data retention.

Select the smallest fitting profile:

- `router` for a small entry point that delegates most procedures;
- `application` for a service or library with repository-specific commands and invariants;
- `monorepo` for shared root rules plus local subtree differences;
- `mcp-server` for an MCP implementation that also follows `mcp-server-architect`;
- `safety-critical` for sensitive data, physical control, financial, medical, identity, or similarly high-impact systems.

Profiles are composition guidance, not separate versions of the standard.

## Canonical ownership and architecture boundaries

Every durable rule, contract, schema, generated artifact, and configuration default has one canonical owner. `AGENTS.md` summarizes the operational consequence and links to that owner. It does not preserve obsolete behavior through numbered files, parallel current implementations, or undocumented compatibility branches.

State non-obvious architecture boundaries that are expensive to infer incorrectly: dependency direction, generated files that must not be edited, registry or generator ownership, required update propagation, and components that may access specific resources. Generic advice such as “write clean code” is not a boundary.

## Safety and data boundaries

High-impact repositories name protected data, privileged components, allowed flows, forbidden flows, default-deny behavior, and the checks that prove each boundary. Secrets, personal data, production exports, credentials, raw sensitive payloads, and real user fixtures remain outside tracked files unless an explicit reviewed contract states otherwise.

Read-only operations are the default for diagnosis. External sends, destructive actions, privilege expansion, sensitive writes, and irreversible changes require the repository's trusted authorization and confirmation mechanism. Model-controlled text, guessed intent, or keyword matching is not proof of human approval.

## Commands and verification

List exact commands for environment setup, the smallest focused check, build or type validation, formatting or linting, and the full completion gate when those operations exist. Prefer repository-owned scripts over duplicated command sequences.

Separate local diagnostics from hosted or provider-backed acceptance. A local pass does not guarantee remote CI, platform compatibility, integration credentials, deployment behavior, or independent approval. Final claims bind to the exact revision and, where applicable, the exact built or published artifact.

Commands that require credentials, external systems, destructive access, payment, or unusual runtime cost state those preconditions and their safe skip or stop behavior.

## Context economy and routing

The root file contains rules needed for most tasks: scope, precedence, core modes, critical boundaries, command entry points, completion criteria, and task routing. Specialized domain procedures, incident histories, exhaustive file maps, and long examples are loaded on demand.

Every reference states when to read it and what decision it owns. A bare list of links is insufficient. Do not duplicate README content, linter configuration, full CI definitions, complete architecture documents, current inventories, or skill catalogs.

Treat length as a review trigger rather than a mechanical target. Router profiles normally remain within 20–60 lines, application profiles within 60–120 lines, and safety-critical profiles within 100–180 lines. A file beyond 180 lines requires an explicit justification or decomposition review.

## Nested instructions

Use nested files only when a subtree has materially different commands, technology, ownership, generated-file rules, or safety boundaries. The root declares that local instructions exist and how precedence works. Each local file identifies its scope and contains only differences plus the local completion checks.

Do not mirror the complete root file into every package. Duplicated inherited rules create conflicting instructions and maintenance drift. A nested file that only links to the root adds no value.

## Anti-patterns and drift

Reject context bloat, skill leakage, lint leakage, blind references, generated-file fossilization, conflicting instructions, host-specific absolute paths, volatile counts, stale ports, embedded changelogs, temporary migration names, and claims not tied to evidence.

Reject brittle consent parsers based on words in a message, instructions that weaken tests to obtain green results, and statements that equate mock coverage with real integration behavior. Record the durable lesson from an incident, but keep the narrative and timeline in an incident document.

Review `AGENTS.md` when build entry points, architecture boundaries, data flows, CI gates, repository layout, ownership, or supported agent platforms change. Validation passing proves structural consistency, not that every instruction remains factually correct.

## Definition of done

An instruction change is complete only when:

1. scope, precedence, operating modes, and canonical owners are unambiguous;
2. links and referenced paths resolve on the exact revision;
3. commands are verified or explicitly marked as unverified with required follow-up evidence;
4. nested files contain local differences without contradictory duplication;
5. safety and data boundaries match implementation and deployment configuration;
6. the validator and relevant repository tests pass;
7. the final report distinguishes verified facts, assumptions, skipped checks, and residual risks.

## Verification

Run the validator with the selected profile, then execute the repository's focused and full quality gates. For monorepos, validate every root and nested `AGENTS.md`. Reviewers compare the instructions with manifests, CI, implementation, deployment boundaries, and representative task execution. Independent approval is required when the instruction system governs production acceptance or high-impact operations.

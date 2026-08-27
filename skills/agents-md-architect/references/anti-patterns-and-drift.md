---
description: Detect instruction smells, overgrown AGENTS.md files, and repository drift before they misdirect agents.
doc_id: reference.agents-md-anti-patterns
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Run the AGENTS.md validator in strict mode, validate operational-claims.yaml when volatile runtime or configuration facts are referenced, and compare each warning with current repository evidence.
---

# AGENTS.md anti-patterns and drift

## Context bloat

The file loads large architecture explanations, exhaustive indexes, incident histories, inventories, or examples for every task. Move specialized material to task-routed documents and keep only the decision that affects common work.

## Skill leakage

A rare or domain-specific procedure is embedded in the root file. Convert it into a workflow, reference, or skill and leave a route that states when it applies.

## Lint leakage

The file restates formatter, linter, compiler, or static-analysis configuration. Prefer the executable command and document only non-obvious repository behavior that automation cannot express.

## Blind references

The file lists paths without explaining when to read them or what they own. Each reference must answer both questions.

## Fossilized initialization

A generated instruction file contains stale counts, versions, dates, ports, package lists, paths, or temporary migration state. Derive volatile facts automatically or remove them from durable policy.

## Runtime capability staleness

Do not preserve statements such as “the agent cannot self-enable this integration,” “this API supports field X,” or “this hook is effective” as timeless facts after observing one build. External platform and runtime capabilities are volatile. Bind a durable capability claim to one exact product/build version and a fresh-context probe observation in `operational-claims.yaml`, validated by `contracts/validate_operational_claims.py`.

A schema/field-presence check proves compatibility shape only. It does not prove that the effective prompt, runtime path, activation flow, middleware, hook, or transport actually uses that field. Behavior claims require a canary that exercises the public path in a fresh process/session and records the observed result. When no such probe is available, phrase the instruction as an unresolved prerequisite or route to current discovery rather than “verified”.

## Hand-maintained operational mirrors

Do not maintain a second editable truth for enabled services, runtime state, feature flags, deployment status, or similar operational inventory. The instruction system points to the canonical configuration or to generated output derived from it.

When a concise mirrored state is genuinely useful, record it as a `configuration-state` entry in `operational-claims.yaml`. The claim names the canonical JSON/YAML path and selector; validation fails when the canonical value changes. Reconcile the canonical source before auditing the prose mirror. A stale registry must never overrule the runtime configuration it summarizes.

## Conflicting instructions

Root, nested, tool-specific, or legacy files disagree. Identify precedence and remove obsolete copies. Do not solve conflict by adding another current variant.

## Weak safety language

Phrases such as “be careful” or “ask before dangerous changes” do not identify protected assets, authorization, forbidden flows, or verification. Replace them with concrete boundaries and trusted controls.

## Brittle approval parsing

Keyword lists, last-message scanners, or model-generated confirmations are not authorization. Use the platform or repository's trusted human-approval mechanism and preserve the exact action preview when required.

## False verification claims

A local hook does not prove hosted CI, a mocked unit test does not prove an external integration, and a green job does not prove the exact artifact was exercised. State the actual evidence boundary.

## Versioned current names

Names such as `implementation-v3`, `final-new`, or `AGENTS-v2.md` usually indicate unresolved ownership. Keep one canonical current name. Retain a version only when it is part of an explicit external compatibility contract with owner, tests, migration, and removal conditions.

## Generic advice

“Write clean code,” “follow best practices,” and similar prose does not change agent behavior. Replace it with a repository-specific invariant, command, boundary, or remove it.

## Drift triggers

Review the instruction tree when any of these change:

- build, test, release, or deployment entry points;
- repository layout or generated-file ownership;
- architecture or dependency direction;
- authentication, authorization, data flow, mounts, or network exposure;
- supported agent platforms, versions, runtime capabilities, or instruction precedence;
- recurring incident or review evidence;
- canonical operational configuration, registries, documents, skills, or workflows referenced from the file.

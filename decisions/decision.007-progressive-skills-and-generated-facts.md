---
description: Adopt progressive skill disclosure, language-neutral cores, generated dependency facts, and benchmark-gated AFDS changes
doc_id: decision.007-progressive-skills
type: decision
status: active
rigor: normative
owners: [repository-maintainers]
schema_version: 3
supersedes: [decision.002-mcp-standard-decisions, decision.006-mcp-enhanced-standard]
---

# Progressive skills and generated facts

## Context

The previous skills copied complete standards, framework workarounds, templates, current dependency versions, and project-specific lessons into large prompts. This created contradictions, stale instructions, excessive context use, and universal rules derived from individual Python servers.

## Decision

- Keep each `SKILL.md` as a routing and execution layer.
- Put stable language-neutral requirements in a core standard.
- Load framework and project lessons from references only when relevant.
- Derive volatile dependency facts from manifests maintained by Dependabot.
- Require deterministic retrieval and mutation benchmarks before making AFDS structure mandatory.
- Maintain Python and .NET MCP profiles under one protocol-level core.

## Alternatives

- Continue expanding monolithic prompts: rejected because every addition taxes every task.
- Create separate unrelated standards per project: rejected because shared protocol and security invariants would drift.
- Remove standards and rely on agent judgment: rejected because high-risk behavior needs testable constraints.

## Consequences

Existing v2 documents and templates are compatibility inputs, not authoritative rules. Projects migrate incrementally. The repository must maintain benchmark snapshots, validators, and reference implementations as evidence.

## Validation

The AFDS benchmark generated 2,160 documents and 1,800 queries. The accepted v3 profile improved MRR from 0.425 to 0.983 and reduced top-three context by about 74% relative to AFDS v2. Two later schema expansions produced no MRR gain and were rejected. The mutation suite detected 120 of 120 injected structural defects.

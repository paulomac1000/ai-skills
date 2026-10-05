---
description: Acceptance playbooks for workflow, reference, system, guide, decision, and contract documents.
doc_id: reference.documentation-type-playbooks
type: reference
status: active
rigor: informative
owners: [repository-maintainers]
---

# Documentation type playbooks

Use this playbook to write or repair technical documentation after evidence, ownership, and verification are known; load only the matching type section.

## Workflow

Include the objective, prerequisites, authorization boundary, ordered actions, expected observations, validation, failure branches, rollback or safe stop, and escalation. Commands are copyable and identify their working directory and required environment. Do not hide irreversible steps inside a general sequence.

## Reference

Define scope, vocabulary, stable facts, constraints, defaults, examples, non-goals, and links to sources of truth. Separate durable rules from volatile inventories. A reference is not a tutorial and should answer lookups quickly.

## System

Describe responsibility, boundaries, components, data and control flows, state ownership, concurrency, lifecycle, interfaces, trust boundaries, failure modes, degradation, observability, capacity assumptions, and recovery. Diagrams supplement rather than replace textual contracts.

## Guide

Name the reader, prerequisites, target outcome, conceptual model, walkthrough, trade-offs, common mistakes, and next steps. A guide may simplify, but it must link to authoritative contracts when details matter.

## Decision

Record context, decision drivers, selected option, rejected alternatives, consequences, risks, implementation impact, and review triggers. Do not rewrite history to make the selected option appear inevitable.

When the decision materially drives implementation, extend that same `decision` document with a bounded implementation contract: name affected obligations/criteria and consumers, order material implementation consequences, and cover migration/compatibility, rollout, rollback, superseded-path cleanup, required verification, downstream review, and completion semantics where applicable. Do not add empty sections for irrelevant dimensions.

Keep authority and realization separate. A decision can be accepted/current while implementation is partial. A claim that implementation is complete requires every declared mandatory consequence to be resolved and every required verification consequence to point to current evidence; pending, blocked, unknown, or unreviewed required consequences keep the claim incomplete. Use the lifecycle/change-impact protocol for downstream consequences instead of maintaining a second dependency graph.

## Contract

Specify producer and consumer responsibilities, input and output schemas, validation, idempotency, ordering, timeouts, cancellation, retries, errors, compatibility, security, examples, and conformance tests. Ambiguous prose does not override a machine-readable schema or executable contract test.

When the contract is also the durable behavioral/acceptance source for a non-trivial change, distinguish requirements/obligations, observable acceptance criteria, assumptions, examples, and evidence. Cover normal and negative/failure behavior, public/compatibility effects, decision links, and verification mapping where applicable. Reuse stable obligation/criterion references from the canonical owning contract rather than copying its machine schema, and point verification to the owning proof mechanism instead of embedding mutable execution results in the document.

## Cross-type rules

A document that needs a different owner, audience, lifecycle, or verification method becomes a separate document. A short summary may link across types, but copied normative text is not maintained in parallel.

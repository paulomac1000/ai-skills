---
description: Acceptance playbooks for workflow, reference, system, guide, decision, and contract documents.
doc_id: reference.documentation-type-playbooks
type: reference
status: active
rigor: informative
owners: [repository-maintainers]
---

# Documentation type playbooks

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

## Contract

Specify producer and consumer responsibilities, input and output schemas, validation, idempotency, ordering, timeouts, cancellation, retries, errors, compatibility, security, examples, and conformance tests. Ambiguous prose does not override a machine-readable schema or executable contract test.

## Cross-type rules

A document that needs a different owner, audience, lifecycle, or verification method becomes a separate document. A short summary may link across types, but copied normative text is not maintained in parallel.

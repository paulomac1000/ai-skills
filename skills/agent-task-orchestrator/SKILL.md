---
name: agent-task-orchestrator
description: Preserve task intent and safely coordinate bounded delegated agent work through evidence-bound completion.
---

# Agent task orchestrator

Use this skill when a task spans multiple phases, continuations, or delegated/background agents and completion must preserve the user's exact requirements, scope, execution methods, authority, and evidence.

## Workflow

1. Create or reconcile one current intent ledger from `contracts/intent-ledger.schema.json`. Preserve stable requirement IDs, provenance, current `intent_revision`, scope, required capabilities/methods, prohibitions, and acceptance criteria.
2. Before side effects, run exact scope admission. Newly discovered targets remain out of scope until task-owner authority updates the ledger.
3. For repository-backed work, capture immutable planning and execution repository/ref/revision identities. Do not rewrite the planning base after branch movement.
4. Classify base state. Admit a descendant only after explicit non-overlap/assumption revalidation; rebase, divergence, target changes, overlap, and unknown state stop or replan.
5. Define each child as the smallest useful contract: intent revision, exact bases, plan revision, capabilities, authority subset, resource domains, expected outputs, and work requirement.
6. Admit capabilities, authority, and resource domains before dispatch. Secret handles and deployment authority remain governed by their repository-level contracts.
7. Dispatch once under a durable attempt ID. Record the provider's durable child/job ID. An accepted launch is not completion evidence.
8. Continue an existing child with a bounded delta. Reconcile before retry; a fresh redispatch uses a new attempt ID.
9. Track meaningful evidence-backed progress. Stop/reconcile bounded no-progress loops. Continue independent parent work while background children run rather than waiting unnecessarily.
10. Reconcile terminal child results against expected artifacts, authoritative side-effect state, published revision, verification, and execution identity. Treat `COMPLETED_NO_EVIDENCE` as suspicious.
11. Serialize overlapping writer/resource domains unless a stronger concurrency contract proves independence.
12. Before reporting task completion, run the parent completion gate against the current intent revision. Every current mandatory requirement, required capability/method, and acceptance criterion needs valid evidence.
13. Compact or hand off using stable IDs, scope, active child identities, execution revisions, and opaque references rather than replaying full history or secrets.

Read `STANDARD.md` before use. `tools/task_orchestrator.py` provides deterministic reference helpers for admission, scheduling, reconciliation, and completion; provider adapters remain outside the portable core.

## Constraints

- Do not create separate mutable task ledgers in parent and child agents.
- Do not silently drop user-required methods or capabilities when a preferred tool is unavailable.
- Do not expand scope due to time, cost, token, or provider pressure.
- Do not treat branch movement, launch success, exit zero, or child `done` as sufficient acceptance evidence.
- Do not redispatch an existing durable attempt before reconciliation.
- Do not give a child broader authority than its bounded subtask requires.
- Do not duplicate shared action-outcome, runtime-identity, audit, lease, or secret-taint semantics inside this skill.

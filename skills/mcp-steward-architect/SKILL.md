---
name: mcp-steward-architect
description: Design, generate, review, and harden durable MCP Steward control planes with explicit enforcement gates, resumable work, claim-bound evidence, and fail-closed recovery.
---

# MCP Steward architect

Use this skill when an MCP service owns bounded durable workflow responsibility rather than only synchronous request/response capabilities. A Steward is a deterministic policy-governed application: models may advise, plan, classify, summarize, or propose, but they do not own canonical state, authority, proof, side effects, or completion.

## Base standards

A conforming Steward extends, and never weakens, `mcp-server-architect` for its public MCP/runtime surface and `mcp-server-consumer` for downstream capability use. Route findings to their canonical owner instead of duplicating generic transport, SDK, browser, container, or consumer policy here.

## Design-first protocol

Before implementation produce a machine-readable Steward Design Pack covering:

- authority envelope: owned/observed state, allowed mutations, verification/parent authority, forbidden claims;
- durable state machine: states, terminality, lanes, legal transitions, progress, recovery, cancellation, fences;
- identity: exact subject/candidate, lineage, semantic generation, attempt, optimistic version, decision/freshness dimensions;
- proof catalog: claims, producers, authority/observation grade, binding, coverage, freshness, completion obligations;
- every stateful external effect, including submit/cancel ambiguity, reconciliation, idempotency, affinity and handle recovery;
- mutation state/effect and invariant-enforcement matrices;
- deadline/budget algebra including reserve-before-start and deterministic finalization reserve;
- persistence, disclosure, response, audit and provider projections; concurrency lanes; recovery equivalence; acceptance plan.

Do not implement a material path with unknown authority, fabricated identity fallback, unowned state, or no failure/recovery disposition.

## Required enforcement gates

- **Work Admission Gate**: admits durable work only from current identity, authority, capability, completion-contract and budget facts.
- **Mutation Admission Gate**: immediately before an authority-bearing effect re-proves current lineage/generation/attempt, effective authority, lease when required, exact subject/candidate, reviewed capability provenance, durable operation identity, ambiguity state and budget/deadline.
- **Evidence Promotion Gate**: limits claims to what producer, binding, coverage, freshness and epistemic rules actually prove; missing observation is never a negative observation.
- **Completion Publication Gate**: proves current obligations, exact candidate/subject, evidence authority/freshness, external-effect resolution and lineage ownership before publication.

Gate results are typed outcomes such as `Admitted`, `LostAuthority`, `StaleCandidate`, `CapabilityUnavailable`, `ReconciliationRequired`, `InsufficientEvidence`, or `BudgetUnavailable`; material decisions are never bare booleans.

## Implementation invariants

1. Persist durable admission before returning a long-running job ID; public control roles are `submit/status/get/cancel/doctor` rather than a request-lived workflow.
2. Capture semantic generation at admission/claim and fence every successor, side effect, evidence record and publication; optimistic record version remains distinct.
3. Admit capabilities only from reviewed source/id/revision/digest contracts; health/liveness never proves capability support.
4. For disclosure-bearing calls construct an explicitly approved safe projection before egress.
5. Commit operation identity/start intent and mutation decision before the first byte of stateful dispatch.
6. Distinguish rejection, pre-dispatch failure, delivered, delivery-unknown, caller cancellation and cancellation-delivery-unknown; reconcile ambiguity before replay.
7. Treat remote cancellation as its own stateful operation. Local `cancelled` never proves remote stop when the contract requires remote resolution.
8. Preserve recoverable remote handles and move reconstructable external waits to a bounded maintenance/reconciliation lane rather than occupying the primary worker.
9. Make retries canonical-first: after dedupe/CAS/no-op, reload canonical persisted identity/output before any downstream decision.
10. Bind verification/evidence to immutable `CandidateIdentity`; `verify(X)` may authorize only `publish(X)`.
11. Promote evidence monotonically: incomplete binding/coverage, `unknown`, or `unobserved` cannot become stronger or complete-negative claims.
12. Reserve operation budget before a leg starts; durable wall-clock deadlines survive restart and transport defaults cannot silently redefine them.
13. Preserve inbound completion obligations and finalize only through the Completion Publication Gate after exact current subject/candidate re-read.
14. Emit a durable structured timeline sufficient to reconstruct admission, mutation, dispatch, ambiguity, cancellation, evidence, recovery and publication without secrets.
15. Status observation is bounded and progress-aware; repeated identical upstream state does not advance semantic progress or justify hot polling.

## Review hot spots

Prioritize stale generation adoption; mutation-gate→dispatch authority drift; health→capability confusion; verification→publication candidate drift; dispatch→handle-bind crash windows; local cancel→remote reality; terminal result→evidence overclaim/hot loops; observation→claim causal gaps; live→restart divergence; and focused tests→production acceptance overclaim.

## References and tools

Read `STANDARD.md` first. Use `references/authority-and-mutation-admission.md`, `durable-state-and-recovery.md`, `external-operations-and-reconciliation.md`, `evidence-authority-and-completion.md`, `credentials-and-failover.md`, `observability-and-diagnostics.md`, and `testing-strategy.md` for the corresponding deep contracts. Use `tools/validate_steward.py` for schema/semantic checks and `tools/generate_steward.py` to extend the canonical MCP generators.

## Ownership boundary and constraints

This skill owns reusable Steward service/runtime architecture, not a competing mutable TaskBrief/RequirementLedger/session/delegation/model-routing owner. External orchestrators may provide an immutable/snapshot work or completion contract; the Steward preserves and proves against it.

Never use queues/logs/model context as canonical state; dispatch before durable reservation; retry possible writes after ambiguous delivery; let stale work adopt a newer generation; synthesize authority-bearing identity/lease/capability truth; equate configured with observed-effective state; treat producer success as proof; publish a different candidate than verified; convert missing observation to a negative fact; mark remote cancellation resolved while ambiguous; or claim production acceptance from scaffolding/focused/candidate-owned evidence alone.

The assessed revision MUST NOT be the sole authority used to approve itself when independent verification is required.

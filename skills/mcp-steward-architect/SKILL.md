---
name: mcp-steward-architect
description: Design, generate, review, and harden durable MCP Steward control planes with bounded authority, resumable work, provenance-bound evidence, and fail-closed recovery.
---

# MCP Steward architect

Use this skill when an MCP service is not merely a request/response capability surface but owns a bounded, long-running workflow such as verification, runtime diagnosis, research/evidence acquisition, release/change coordination, or another durable control-plane responsibility.

A Steward is a durable policy-governed application. An LLM may advise, classify, summarize, plan, review, or propose hypotheses; it is never the Steward itself.

## Base standards

A conforming Steward extends rather than replaces:

- `mcp-server-architect` for MCP protocol, transports, capability manifests, server-side authorization, target/resource binding, bounded responses, packaging, and exact-artifact acceptance;
- `mcp-server-consumer` for outcome-first downstream selection, exact capability identity, consumer-owned trust, bounded discovery, retry safety, reconciliation, pagination, and cross-server workflows.

Apply both prerequisite standards. A Steward rule MUST NOT weaken either standard.

## Workflow

1. Define the Steward's bounded domain responsibility and declare what it owns, observes, may mutate, may verify, and must never claim.
2. Define exact subject identity, relevant freshness dimensions, and the decision dimensions that can invalidate prior plans, evidence, approvals, or completion candidates.
3. Define durable job, lineage, semantic generation/work epoch, attempt, optimistic record version, lease, cancellation, deadline, and terminal semantics independently from MCP transport and provider SDKs. Do not overload optimistic versioning and work invalidation when stale work could otherwise inherit a newer generation.
4. Require each worker/stage to capture the semantic generation under which it was admitted and propagate that captured generation through successor enqueue, deferred work, projections, side-effect authorization, artifacts, and publication. Never let persistence silently substitute the latest generation for stale work.
5. Perform capability admission before committing work that cannot satisfy its required completion obligations.
6. For disclosure-bearing outbound calls, construct an explicit policy-approved disclosure-safe projection before the external boundary. Prompt-role separation or prompt-injection defenses do not authorize data egress.
7. Persist stateful external-operation intent/receipt before dispatch, distinguish delivery ambiguity explicitly, and reconcile before replay. If a remote handle was observed but local binding persistence fails, preserve recoverable dispatch/binding uncertainty rather than regressing to not-dispatched.
8. Model upstreams through semantic ports with observed operational contracts: idempotency, recovery, cancellation, progress, credential affinity, evidence classes, bounds, and confidentiality/egress constraints.
9. Make retry canonical-first: if a stable stage/artifact identity already has a committed result, dedupe/CAS loss/retry must reload and return that canonical value/reference/digest, and every downstream gate/job/handoff must consume it instead of an attempt-local value.
10. Keep model output advisory until deterministic policy and appropriate evidence authority promote it. Caller-declared metadata must never mint independent authority.
11. Bind evidence and reusable decisions to exact subject identity, producer identity, provenance, freshness, generation/revision, and policy/proof identity when applicable.
12. Fence mutable updates by the required version/attempt identity and all actionable terminal publication by current lineage generation/current job.
13. Make deterministic transition preconditions discoverable before mutation when the Steward already knows them: exact revision/generation, lease/assignment identity, verification/completion profile, required authority class, and required evidence axes.
14. Separate heartbeat from semantic progress. Expose a stable state/progress revision for long-running observation when useful, prefer bounded server-side wait or next-poll guidance over model-turn polling, reserve finalization capacity, and bound retries, time, calls, tokens, artifacts, and cleanup.
15. Route secrets through a credential broker; keep credential failover distinct from retry and provider/model substitution.
16. Emit structured durable events sufficient to reconstruct the workflow without raw provider payloads or secrets, and provide bounded operator diagnostics for ownership, progress, ambiguity, recovery, and dependency state.
17. Finalize only through a completion gate that checks required obligations, evidence, ambiguity, freshness, current lineage ownership, and actual authority.
18. Test the failure interleavings that matter: stale worker successor enqueue after generation advance; canonical artifact A versus retry-local artifact B; successful remote dispatch followed by failed local handle bind; cancellation/invalidation versus successor scheduling/publication; blocked private/unknown egress sentinels; repeated unchanged status; false self-declared authority; crash/restart; lost wakeups; and exact deployment artifacts.

Read `STANDARD.md` first. Use the references selectively rather than reconstructing these mechanisms from memory:

- `references/durable-state-and-recovery.md` for generation/version separation, captured-generation fencing, canonical persisted state, leases, wakeups, and restart recovery;
- `references/external-operations-and-reconciliation.md` for receipts, dispatch ambiguity, remote-handle recovery, disclosure-before-dispatch, and retry eligibility;
- `references/evidence-authority-and-completion.md` for evidence classes, actual authority, discoverable completion/verification preconditions, and completion gates;
- `references/credentials-and-failover.md` for secret handling and credential/provider fallback policy;
- `references/observability-and-diagnostics.md` for progress revisions, durable timelines, doctor views, and bounded diagnostics;
- `references/testing-strategy.md` for deterministic race/fault scenarios and exact-artifact acceptance.

Use the templates for machine-readable Steward/upstream/proof/credential contracts, `tools/validate_steward.py` for semantic validation, and `tools/generate_steward.py` to extend the canonical MCP server generator instead of starting from an empty server.

## Review hot spots

During design or code review, inspect these boundaries explicitly before spending time on style or local abstractions:

- state transition -> successor enqueue: can stale work adopt the current generation?
- non-deterministic stage -> dedupe/CAS/no-op persistence: does downstream use the canonical committed value or the retry-local value?
- remote dispatch -> local handle persistence: can a real remote job become orphaned or blindly duplicated?
- raw/caller-controlled/private data -> external reasoning/research/review: is there an explicit disclosure-safe projection before the call?
- long-running status -> repeated observation: can clients detect that no new semantic information arrived?
- verification/completion mutation -> policy gate: were exact revision, authority, lease, profile, and evidence requirements discoverable before the caller attempted the transition?
- independent verification -> caller metadata: is authority derived from authenticated/effective identity rather than a caller-supplied label?

A green happy-path suite does not close these risks; require negative regressions for the applicable boundaries.

## Ownership boundary

This skill owns service/runtime architecture for durable Stewards. It does not create a second canonical owner for mutable user-intent ledgers, session rotation, model-routing workflow state, or external-worker delegation when those concerns are already owned by a workflow/orchestrator standard. Profile-specific ledgers may be composed only when the domain actually owns them.

## Constraints

- Do not implement `agent_execute(prompt)` as the primary Steward API.
- Do not bind long-running work to one MCP request lifetime.
- Do not make an in-memory queue, model session, log stream, or memory product the authoritative job store.
- Do not treat timeout after dispatch as proof of non-delivery.
- Do not let stale generations or attempts publish current actionable results or inherit a newer semantic generation.
- Do not continue downstream with an attempt-local artifact after dedupe/CAS/no-op persistence if another canonical value already owns the stable identity.
- Do not treat prompt-injection safety as permission to disclose private, mixed, unknown, or caller-controlled data to an external provider.
- Do not lose an observed remote handle merely because the ordinary local binding write failed.
- Do not allow callers, workers, or models to mint trusted evidence authority through declared metadata.
- Do not hide deterministic transition preconditions and force callers to discover them through mutation/error loops.
- Do not rotate credentials to bypass authorization, policy denial, or an ambiguous stateful submission.
- Do not use one `success` flag to represent execution, delivery, evidence, verification, and completion.
- Do not hold durable-state locks or transactions while awaiting a remote provider.
- Do not claim semantic progress from repeated identical polling observations.
- Do not claim production acceptance from generated scaffolding or candidate-owned evidence alone.

The assessed revision MUST NOT be the sole authority used to approve itself when independent verification is required.

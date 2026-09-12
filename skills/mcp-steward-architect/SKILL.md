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
2. Define exact subject identity and freshness dimensions before defining workflow stages or tools.
3. Define durable job, lineage, generation, attempt, lease, cancellation, deadline, and terminal semantics independently from MCP transport and provider SDKs.
4. Perform capability admission before committing work that cannot satisfy its required completion obligations.
5. Persist stateful external-operation intent/receipt before dispatch, distinguish delivery ambiguity explicitly, and reconcile before replay.
6. Model upstreams through semantic ports with observed operational contracts: idempotency, recovery, cancellation, progress, credential affinity, evidence classes, and bounds.
7. Keep model output advisory until deterministic policy and appropriate evidence authority promote it.
8. Bind evidence and reusable decisions to exact subject identity, producer identity, provenance, freshness, and policy/proof identity.
9. Fence all state updates by version/attempt and all actionable terminal publication by current lineage generation.
10. Separate heartbeat from semantic progress, reserve finalization capacity, and bound retries, time, calls, tokens, artifacts, and cleanup.
11. Route secrets through a credential broker; keep credential failover distinct from retry and provider/model substitution.
12. Emit structured durable events sufficient to reconstruct the workflow without raw provider payloads or secrets.
13. Finalize only through a completion gate that checks required obligations, evidence, ambiguity, freshness, and authority.
14. Test crash windows, lost responses, stale workers, concurrency, cancellation, recovery, fallback, and exact deployment artifacts before claiming acceptance.

Read `STANDARD.md` first. Use the templates for machine-readable Steward/upstream/proof/credential contracts, `tools/validate_steward.py` for semantic validation, and `tools/generate_steward.py` to extend the canonical MCP server generator instead of starting from an empty server.

## Ownership boundary

This skill owns service/runtime architecture for durable Stewards. It does not create a second canonical owner for mutable user-intent ledgers, session rotation, model-routing workflow state, or external-worker delegation when those concerns are already owned by a workflow/orchestrator standard. Profile-specific ledgers may be composed only when the domain actually owns them.

## Constraints

- Do not implement `agent_execute(prompt)` as the primary Steward API.
- Do not bind long-running work to one MCP request lifetime.
- Do not make an in-memory queue, model session, log stream, or memory product the authoritative job store.
- Do not treat timeout after dispatch as proof of non-delivery.
- Do not let stale generations or attempts publish current actionable results.
- Do not allow callers, workers, or models to mint trusted evidence authority.
- Do not rotate credentials to bypass authorization, policy denial, or an ambiguous stateful submission.
- Do not use one `success` flag to represent execution, delivery, evidence, verification, and completion.
- Do not hold durable-state locks or transactions while awaiting a remote provider.
- Do not claim production acceptance from generated scaffolding or candidate-owned evidence alone.

The assessed revision MUST NOT be the sole authority used to approve itself when independent verification is required.

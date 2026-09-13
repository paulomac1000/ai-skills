---
description: Structured correlation, durable event timelines, semantic-progress revisions, redaction boundaries, and operator diagnostics for MCP Stewards.
doc_id: reference.mcp-steward-observability-diagnostics
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Reconstruct representative normal, ambiguous, cancelled, superseded, credential-fallback, unchanged-poll, and recovery flows from durable events while confirming secrets and protected raw payloads remain absent.
---

# Observability and diagnostics

Use three separate data classes: diagnostic telemetry, durable audit events, and decision evidence. They may reference one another but one does not substitute for another.

## Correlation

Useful fields include request ID, job ID, lineage ID, generation, attempt ID, external operation ID, stage, logical port, adapter/provider, subject identity/digest, request digest, non-secret credential slot, policy/decision identity, trace ID, and failure classification.

## Semantic progress versus observation traffic

Record worker/process liveness separately from semantic progress. A practical long-running state exposes:

- `heartbeatAt` for worker/runtime liveness;
- `progressAt` for the most recent semantic progress;
- `stateRevision`/`progressRevision` or equivalent monotonic/stable marker that changes only when the durable observable state/progress meaningfully changes.

Repeated status requests, provider `RUNNING` responses, or heartbeats with the same progress marker are not progress. Do not advance `progressAt` merely because the system answered another poll.

Public status/doctor responses should make unchanged observations detectable. When possible include a bounded next-action/wait hint such as server-side wait support, `retryAfter`, `nextPollAt`, or an equivalent policy-owned value. This lets consumers avoid model turns whose only function is repeatedly reading identical state.

## Durable timeline

Emit bounded machine-readable events for admission, lease changes, generation invalidation, stale-successor rejection, dispatch, observed-handle binding uncertainty, ambiguous delivery, reconciliation, retry, canonical-artifact reuse after dedupe/CAS loss, circuit state, credential fallback, disclosure rejection, evidence acceptance/rejection, cancellation, cleanup, stale-result discard, supersession, final identity check, and handoff seal.

## Doctor

A production-capable Steward should expose an operator diagnostic view that can answer: who owns this job, what generation/attempt owns publication, what is it waiting on, is it making semantic progress, has the progress revision changed since the caller's previous observation, what deadlines remain, what external operations are ambiguous or have uncertain handle binding, what provider/credential circuits are degraded, what work is recoverable/orphaned, and what recent durable transitions led here.

For transition failures, diagnostics should distinguish a real runtime failure from an unmet deterministic precondition such as wrong revision, stale generation, missing lease, insufficient effective authority, or missing evidence profile requirement.

Normal logs contain IDs/digests/counts/sanitized summaries rather than secrets or full provider/model payloads. Large/raw diagnostic material belongs in a governed artifact store with explicit classification and retention.

A disclosure denial should log only bounded policy/field classifications and references; never log the blocked private value merely to prove that redaction worked.

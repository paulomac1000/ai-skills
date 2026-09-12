# Observability and diagnostics

Use three separate data classes: diagnostic telemetry, durable audit events, and decision evidence. They may reference one another but one does not substitute for another.

## Correlation

Useful fields include request ID, job ID, lineage ID, generation, attempt ID, external operation ID, stage, logical port, adapter/provider, subject identity/digest, request digest, non-secret credential slot, policy/decision identity, trace ID, and failure classification.

## Durable timeline

Emit bounded machine-readable events for admission, lease changes, dispatch, ambiguous delivery, reconciliation, retry, circuit state, credential fallback, evidence acceptance/rejection, cancellation, cleanup, stale-result discard, supersession, final identity check, and handoff seal.

## Doctor

A production-capable Steward should expose an operator diagnostic view that can answer: who owns this job, what is it waiting on, is it making semantic progress, what deadlines remain, what external operations are ambiguous, what provider/credential circuits are degraded, what work is recoverable/orphaned, and what recent durable transitions led here.

Normal logs contain IDs/digests/counts/sanitized summaries rather than secrets or full provider/model payloads. Large/raw diagnostic material belongs in a governed artifact store with explicit classification and retention.

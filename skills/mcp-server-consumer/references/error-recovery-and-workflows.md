---
description: MCP consumer error matrix, retry rules, partial execution, compensation, and read-select-mutate-verify workflows.
doc_id: reference.mcp-consumer-error-workflows
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Execute scenario tests for each error category, conflict refresh, partial batch completion, and compensation decisions.
---

# MCP consumer error recovery and workflows

## Error matrix

| Category | Default action | Retry requirement |
| --- | --- | --- |
| validation failed | correct input or escalate | no automatic retry |
| authentication failed | re-establish identity | no replay with same credentials |
| authorization failed | stop and explain boundary | no automatic retry |
| not found | verify identifier and scope | no blind retry |
| conflict | re-read and recompute | refreshed precondition plus idempotency |
| rate limited | wait bounded server guidance | explicit opt-in and budget |
| timeout | inspect uncertainty | idempotency and explicit opt-in |
| unavailable | bounded retry or degrade | explicit opt-in |
| upstream error | bounded retry or alternate path | explicit opt-in |
| cancelled | stop | never automatic retry |
| unsupported | negotiate or defer | no identical retry |
| internal or unknown | escalate | fail closed |

An explicit retry veto in either the manifest or response wins over a positive signal. Missing signals do not imply permission.

## Read-select-mutate-verify

1. read bounded candidates;
2. select using stable identifiers and user constraints;
3. describe the exact mutation and obtain required confirmation;
4. invoke once with idempotency or precondition data;
5. verify by an independent read or observable state;
6. report uncertainty when the invocation timed out after the server may have committed.

## Partial batch execution

A batch result is normalized into per-item states. Retry only failed items whose effects are known not to have completed. Items with uncertain outcome require verification before replay. Do not collapse partial success into a generic failure.

## Compensation

Compensation is not an automatic rollback assumption. Determine whether a compensating capability exists, whether it is safe, whether it restores semantics rather than merely values, and whether confirmation is required. Report irreversible effects clearly.

## Cross-server workflow

At every boundary, minimize transferred data, re-check trust and authorization, and preserve provenance. One server's success does not prove another server received or applied the same state.

## Verification

Use deterministic scenarios for timeout-after-commit, rate limit, stale version, partial batch, uncertain item, failed compensation, and cross-server verification mismatch.

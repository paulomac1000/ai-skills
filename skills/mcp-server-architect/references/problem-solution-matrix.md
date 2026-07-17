---
description: Diagnostic matrix mapping common MCP server failures to corrective architecture and evidence.
doc_id: reference.mcp-problem-solution-matrix
type: reference
status: active
rigor: informative
owners: [repository-maintainers]
---

# MCP problem-solution matrix

| Symptom | Likely cause | Corrective control | Evidence |
| --- | --- | --- | --- |
| server connected but unusable | readiness conflated with process liveness | separate startup, readiness, liveness, capability health | health and dependency-failure tests |
| one optional integration prevents startup | composition has hard global dependency | isolate registration and degrade capability | startup with dependency absent |
| client receives prose-only errors | wrapper lacks stable error contract | typed error category, message, retry and correlation | schema and client tests |
| duplicate mutation after timeout | retry without idempotency | idempotency key or no automatic retry | timeout replay test |
| conflict loop | retry without refreshed state | re-read version or precondition | optimistic concurrency test |
| cancellation does not stop work | token not propagated or swallowed | pass cancellation to every I/O and cleanup | in-flight cancellation test |
| logs corrupt stdio | diagnostics written to stdout | reserve stdout for protocol, use stderr | protocol capture test |
| tool list consumes excessive context | eager full-schema discovery | bounded categories and on-demand detail | token and discovery test |
| remote annotation bypasses confirmation | consumer trusts server metadata | server enforces auth; consumer retains local policy | malicious-metadata test |
| arbitrary shell execution | model text enters shell | fixed executable, args, allowlist, sandbox | injection tests |
| tests pass but client fails | only domain layer tested | public registration and real-client workflow | inspector/client test |
| source tests pass but container fails | deployment artifact not tested | build once and smoke-test artifact | container smoke |
| request IDs cross-contaminate | global mutable correlation | request scope or async context with reset | concurrent invocation test |
| memory grows after disconnects | orphaned tasks or sessions | cancellation, bounded session state, cleanup | disconnect soak test |
| multi-server tool collision | unqualified identity | namespace by server and stable capability ID | aggregation test |

---
description: Layered deterministic race, crash-window, replay, recovery, security, and exact-artifact testing strategy for MCP Stewards.
doc_id: reference.mcp-steward-testing-strategy
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Execute schema, state-machine, port, adapter, persistence, concurrency, fault-injection, replay, official-client, exact-artifact, and explicitly scoped live-provider lanes with a controllable clock and named fault points.
---

# Steward testing strategy

Stewards are state machines under failure, not CRUD APIs. The highest-value tests force interleavings and crash windows deterministically.

## Layers

1. schema/contract validation;
2. pure state-machine and policy tests;
3. property-based invariants;
4. semantic port contract tests;
5. adapter tests against observed controlled fixtures;
6. transactional persistence/restart tests;
7. deterministic concurrency/linearizability races;
8. fault injection at durable checkpoints;
9. security/secret/fallback tests;
10. historical sanitized replay tests;
11. official MCP client transport tests;
12. exact packaged-artifact smoke;
13. explicit live/provider acceptance lanes.

## Required failure windows

At minimum exercise failure before and after durable reservation, after dispatch but before acknowledgement, after acknowledgement but before remote-handle persistence, after result observation but before local persistence, during verification, and immediately before terminal publication. Also cover cancellation versus completion, stale generation versus new publication, two workers claiming the same work, lost wakeups, provider late response, retry exhaustion, and credential health racing fallback.

Use a controllable clock, barriers, latches/events, and named fault points. Timing sleeps are not synchronization evidence.

## Invariants worth property testing

- terminal state never becomes active;
- stale generation/attempt never changes current canonical state;
- cancelled work starts no new external side effects;
- delivery-unknown never becomes replay merely because another credential exists;
- completed work has no active lease;
- lower-authority evidence cannot satisfy a higher-authority obligation;
- subject revision mismatch never produces current evidence;
- required work is never silently dropped;
- credential fallback cannot increase privilege.

A test file existing in source is not proof it executed. Acceptance evidence should identify the executed case/result and exact candidate artifact/revision.

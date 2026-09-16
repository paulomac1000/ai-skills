---
description: Layered deterministic race, crash-window, replay, recovery, security, canonical-retry, and exact-artifact testing strategy for MCP Stewards.
doc_id: reference.mcp-steward-testing-strategy
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Execute schema, state-machine, port, adapter, persistence, concurrency, fault-injection, canonical-retry, disclosure, replay, official-client, exact-artifact, and explicitly scoped live-provider lanes with a controllable clock and named fault points.
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
9. disclosure/security/secret/fallback tests;
10. historical sanitized replay tests;
11. official MCP client transport tests;
12. exact packaged-artifact smoke;
13. explicit live/provider acceptance lanes.

## Required failure windows

At minimum exercise failure before and after durable reservation, after generation capture but before successor enqueue, after dispatch but before acknowledgement, after remote handle observation but before local handle binding, after acknowledgement but before normal receipt persistence, after canonical artifact persistence but before successor scheduling, after result observation but before local persistence, during verification, and immediately before terminal publication.

Also cover cancellation/invalidation versus successor scheduling, cancellation versus completion, stale generation versus new publication, two workers claiming the same work, lost wakeups, provider late response, retry exhaustion, and credential health racing fallback.

Use a controllable clock, barriers, latches/events, and named fault points. Timing sleeps are not synchronization evidence.

## Mandatory regression shapes

### Torn-read decision barrier

Barrier deterministically between the reads composing one decision and supersede the lineage
across it: parent at N plus child at N+1 is never one valid decision state; restart revalidates
the same read-set.

### Stale-controller completion

Admit under epoch E1, advance to E3, deliver the E1 completion: history only, no current
capability/readiness/mutation authority, and current-probe acceptance stays epoch-bound.

### Stale generation cannot adopt the new epoch

1. worker captures generation N;
2. another operation withdraws/replans and advances to N+1;
3. old worker attempts to enqueue successor/projection/publication;
4. assert the operation is fenced/stale and never gets tagged N+1 by a store-side latest-generation lookup.

### Canonical-first retry

1. attempt 1 computes artifact A and persists it under stable stage/artifact identity;
2. crash before downstream scheduling;
3. retry computes different artifact B;
4. insert/dedupe/CAS says A already owns the identity;
5. assert returned canonical result is A and every downstream gate/job/evidence/handoff binds A, not B.

### Remote dispatch succeeds, local bind fails

1. durable start intent exists;
2. fake provider starts a remote job and returns handle H;
3. inject failure in the local binding transition;
4. assert durable state is reconcile-required/binding-uncertain, H or a recoverable lookup identity is preserved, and replacement dispatch is blocked;
5. restart and prove recovery resumes H rather than starting another remote job.

### Disclosure boundary

Put unique private/unknown/mixed sentinel values in raw caller/domain fields. Exercise the primary workflow plus maintenance/recheck/recovery paths. Capture the fake outbound provider request and assert no blocked sentinel crosses the boundary. Prompt-injection tests are separate and do not satisfy this regression.

### No-progress polling

Return the same remote/non-terminal state repeatedly. Assert heartbeat may advance while semantic progress revision and `progressAt` remain unchanged. If the public contract advertises server-side wait or next-poll guidance, verify the hint is bounded and repeated unchanged observations preserve the same state/progress revision.

### Transition preconditions and authority

For verification/completion/update flows, assert known required revision/generation, lease/assignment, verification profile, authority class, and evidence axes are discoverable before mutation. Submit stale/wrong revision and caller-declared `peer`/`independent` metadata from an implementer principal; assert typed rejection and no authority escalation.

## Invariants worth property testing

- terminal state never becomes active;
- stale generation/attempt never changes current canonical state;
- stale work cannot enqueue successors under a newer semantic generation;
- retry after dedupe/CAS loss cannot continue with a non-canonical attempt-local artifact;
- cancelled work starts no new external side effects;
- delivery-unknown never becomes replay merely because another credential exists;
- observed remote handle plus failed local bind never regresses to a replayable not-dispatched state;
- completed work has no active lease;
- lower-authority evidence cannot satisfy a higher-authority obligation;
- caller-declared authority cannot override effective producer/principal authority;
- subject revision mismatch never produces current evidence;
- required work is never silently dropped;
- credential fallback cannot increase privilege;
- blocked private/unknown data never reaches disclosure-bearing adapters;
- repeated identical observations cannot advance semantic progress.

## Acceptance evidence

A test file existing in source is not proof it executed. Acceptance evidence should identify the executed case/result and exact candidate artifact/revision. Canonical gates must distinguish product failure from harness/infrastructure failure, not-executed, stale, partial, and unknown outcomes.

Every advertised MCP transport still requires official-client exercise, and the exact packaged/deployed artifact must be smoke-tested under the inherited `mcp-server-architect` rules. Live/provider acceptance remains a separate lane and must not be inferred from fakes when real credentials/targets/provider behavior are required.

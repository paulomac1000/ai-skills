---
description: Normative cross-skill application contracts for layered action outcomes, runtime identity, tool-result provenance, deployment leases, and durable audit events.
doc_id: reference.agentic-action-contracts
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Validate the referenced schemas and run focused regressions for ambiguous outcomes, exact runtime identity, provenance separation, lease admission/replay, and append-only audit history.
---

# Agentic action contracts

These are application and repository contracts. Runtime-agent orchestration, mutable intent/session state, delegation lifecycle, and agent diagnostic reasoning are owned by `opencode-stack-guides` under OSG #140 rather than by this repository.

## Layered outcomes

`action-outcome.schema.json` is the canonical generic result model. Preserve transport, execution, side effect, artifact publication, verification, disposition, and retry safety as separate axes. A terminal wrapper label or model statement such as `done` is not a substitute for authoritative evidence on those axes.

A client timeout after dispatch may coexist with a confirmed external mutation. A worker process may exit successfully while its required artifact is missing. A published artifact may coexist with failed verification. `verification=stale` means the evidence was valid for an older revision/runtime and cannot prove the current target. When `side_effect=unknown`, disposition remains `pending` or `reconcile_required`; do not collapse an unresolved external effect into terminal `failed` before reconciliation establishes what happened.

Retry policy consumes side-effect state plus an independently reviewed idempotency contract. Transport failure alone never proves replay safety.

## Runtime identity chain

`runtime-identity.schema.json` describes a running application instance. `runtime_identity.py` verifies the generic acceptance identity chain:

`source revision -> built artifact digest -> candidate runtime self-report -> deployed runtime self-report`.

Candidate and deployed runtime identity are queried from the running artifacts; they are not inferred from checkout, tag, deployment request, or image label alone. Acceptance fails if source revision or artifact digest differs from the expected candidate.

Artifact identity is stable across a restart of the same artifact. `instance_generation` is instance-scoped and changes when policy requires a new process/deployment generation. Evidence bound to a previous generation is stale for generation-sensitive claims even when the artifact digest is unchanged.

## Tool-result provenance

`tool-result-envelope.schema.json` keeps provider/tool source material and runtime-authored annotations in separate structural domains. `tool_result_envelope.py` hashes exact source bytes before annotation and adds runtime guidance without rewriting source data.

Single-part responses bind `data` to explicit provenance. Multipart or streamed material is represented as source parts, each with its own provenance and optional source-byte digest. Runtime annotations may exist at the envelope or part level but are never attributed to the provider/tool.

Do not solve provenance by stripping known reminder prefixes after source text has already been mutated. Evidence and memory consumers select source data directly from the structured envelope.

## Deployment leases

`deployment-lease.schema.json` keeps schema v1 for exact one-use authority and adds schema v2 for target-generation fencing. A v2 lease additionally binds the smallest conflicting `target.mutation_domain`, an authority-issued `expected_current` target snapshot, and a `fence` using provider CAS, a durable broker single-writer, or an authority-owned lease generation.

`deployment_lease.py` keeps the v1 exact-dimension admission helper and adds a v2 fenced path. Immediately before reservation it re-reads the trusted authority record, verifies principal/session, target, artifact, action, normalized arguments, policy and source revision, then compares the authoritative target state and fence. Only `TARGET_PRECONDITION_MATCH` may proceed to atomic domain reservation. `TARGET_ADVANCED_COMPATIBLE`, `TARGET_CHANGED`, `STALE_LEASE`, `CONFLICTING_MUTATION_ACTIVE`, and `TARGET_STATE_UNKNOWN` never dispatch from the old lease.

Conflicting mutations in one domain are serialized at the authoritative admission boundary. Provider-CAS mode carries the exact provider precondition token that the provider mutation must enforce atomically; broker/generation modes require a durable compare-and-swap reservation before dispatch. A crash or restart must reload that reservation. A stale holder cannot mutate after a newer fence generation exists, and rollback races with forward deployment in the same domain unless the deployment owner defines a narrower proven-safe domain.

Repository content, model output, candidate code, or an untrusted client cannot mint, rewrite, extend, or reactivate `expected_current` or the fence. RuntimeAcceptanceReceipt-style identity may inform the authority's target snapshot but is evidence, never deployment authority. Timeout or connection loss after dispatch leaves the domain pressure-bearing until authoritative reconciliation proves applied or no-effect state; an unresolved effect blocks conflicting handover and blind retry. Credentials stay behind the trusted executor/broker boundary.

## Durable audit events

`audit-event.schema.json` is the common event shape. Preserve event/correlation identity, actor/session, logical capability/operation/target, layered outcome, runtime identity where relevant, artifact/evidence/policy/approval references, and explicit retention class.

Sensitive arguments are represented by approved opaque identity or keyed digest. The common schema accepts `hmac-sha256:` normalized argument digests and deliberately rejects plain `sha256:` argument fingerprints. Raw credentials and secrets remain prohibited from audit records and public error/result surfaces.

`audit_log.py` is the canonical cross-event semantic validator. `validate_audit_sequence()` rejects duplicate or conflicting event identities, idempotency-key rebinding to another actor/action/target/argument identity, contradictory successful histories, and a second equivalent terminal success for the same idempotency identity. One logical idempotent operation has one canonical successful audit result. A later observation of that already-completed operation must be represented as non-success replay/reconciliation evidence that refers back to the canonical result rather than as another successful terminal event.

`validate_audit_append()` additionally proves that a candidate history preserves the previously accepted history byte-semantically at every existing position. Truncation or rewriting of an accepted prefix is a blocking finding. An append-only storage implementation may enforce stronger durability and concurrency guarantees, but it MUST preserve these same semantic invariants.

Provider-specific details extend `extensions`; they do not replace common outcome or identity semantics.

## Composition

These contracts are orthogonal. A deployment audit event may reference a DeploymentLease, include a RuntimeIdentity, and carry an ActionOutcome whose transport and side-effect states disagree until reconciliation. None of these application contracts owns runtime-agent intent, delegation, session orchestration, or diagnostic-state transitions.

## Verification

Focused regression coverage includes timeout-plus-confirmed-side-effect, unknown-side-effect reconciliation, completed worker with missing artifact, published artifact with failed verification, stale verification, runtime identity mismatch, same-artifact new-generation checks, source-hash stability under runtime annotations, per-part provenance, expired/revoked/replayed or mismatched deployment leases, principal denial, rejection of plain secret fingerprints in audit events, duplicate/rebound/conflicting audit histories, and duplicate equivalent terminal success.

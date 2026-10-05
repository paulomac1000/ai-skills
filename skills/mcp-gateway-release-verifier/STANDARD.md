---
afds_schema_version: 2
description: Normative composition contract for bounded MCP exact-candidate release verification.
doc_id: reference.mcp-gateway-release-verifier-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification:
  kind: command
  value: Run the release-verifier regressions and the repository exact-head gate against the candidate artifact.
---

# MCP gateway release verifier standard

## Composition boundary

This verifier MUST consume, not redefine, the canonical evidence for source/artifact/runtime identity, exact-candidate schema acceptance, real MCP transport dogfood, execution-integrity warnings, bootstrap, and isolation. A change in an owning contract must flow into the verifier through its phase result rather than a forked local rule.

## Required phases

The baseline order is preflight, bootstrap, exact-artifact launch, schema acceptance, lifecycle chain, degraded-health probe, runtime identity, execution integrity, and cleanup. Every required phase is `pass`, `fail`, or `not_run`; any value other than `pass` makes the release verdict fail closed.

Exact-artifact-launch and schema phases may only be `pass` when a canonical probe client receipt is provided: it must name the pinned official client, carry a well-formed initialize payload, and include a session receipt that matches the recorded payload and artifact digest. Evidence derived without the pinned official MCP client cannot satisfy the composition.

Public lifecycle evidence must exercise an identifier produced by one operation as input to its documented status/read consumer. Degraded-health evidence must come from an injected downstream failure, not process liveness alone.

## Local candidate lane

Local acceptance MUST begin from a clean candidate and disposable state, ports, HOME/XDG roots, and config. It composes build and migration preflight, isolated launch, exact-candidate acceptance, real-transport dogfood, this release verifier, durable async polling, migration invariants, and ownership-scoped cleanup. A port conflict or failed phase is non-green. Cleanup may delete only resources carrying the current run's ownership marker beneath its sandbox root.

The local candidate lane MUST derive migration scope from trusted policy/admission evidence, not an implementer- or caller-controlled boolean. Positive non-migration authority requires an identity-bound trusted binding: immutable policy/admission source digest + exact candidate revision + validated immutable `qa-change-verifier` change-acceptance contract digest. A class name or caller-authored string is not provenance. Missing, malformed, stale, unbound, or digest-mismatched scope is non-green. A candidate is exempt from migration-matrix evaluation only when that exact trusted binding admits a contract with no required obligation with `kind=migration`; a caller cannot self-declare the exemption.

When the admitted contract contains a required persistent schema/storage migration obligation, the lane MUST pass raw migration evidence through the canonical `qa-change-verifier` evaluator and accept only the receipt issued by that in-process evaluation, bound to the same candidate revision. Caller-authored receipt dictionaries and caller-authored policy switches are not acceptance evidence. Interrupted-recovery proof is mandatory in this lane; current-schema rerun applicability comes only from the trusted candidate-scope policy binding. The issued receipt must prove the declared predecessor/unsupported matrix, expose each exercised input ref/kind/schema identity, pre-current legacy state, exact production migration entrypoint/revision, representative data invariants, and required interrupted-recovery behavior. The bounded lane receipt preserves the exact production entrypoint and revision so downstream consumers can detect migrator drift. Supplying migration evidence when the trusted admitted scope declares no required migration is a scope contradiction and is non-green.

## Bounded receipt

Receipts contain only candidate references, phase status, a short summary, and bounded evidence references. Raw logs, unbounded tool output, and provider payloads remain external evidence. Extension phases are allowed only within the declared phase-count and receipt-byte bounds and cannot replace required phases.

## Definition of done

The exact artifact was launched in isolation; pinned schema/client evidence, real transport, lifecycle, degraded health, runtime identity, execution integrity, and cleanup are phase-attributable; every required phase passed; output stayed within bounds; and the receipt points to immutable evidence rather than embedding it.

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

Public lifecycle evidence must exercise an identifier produced by one operation as input to its documented status/read consumer. Degraded-health evidence must come from an injected downstream failure, not process liveness alone.

## Local candidate lane

Local acceptance MUST begin from a clean candidate and disposable state, ports, HOME/XDG roots, and config. It composes build and migration preflight, isolated launch, exact-candidate acceptance, real-transport dogfood, this release verifier, durable async polling, migration invariants, and ownership-scoped cleanup. A port conflict or failed phase is non-green. Cleanup may delete only resources carrying the current run's ownership marker beneath its sandbox root.

## Bounded receipt

Receipts contain only candidate references, phase status, a short summary, and bounded evidence references. Raw logs, unbounded tool output, and provider payloads remain external evidence. Extension phases are allowed only within the declared phase-count and receipt-byte bounds and cannot replace required phases.

## Definition of done

The exact artifact was launched in isolation; pinned schema/client evidence, real transport, lifecycle, degraded health, runtime identity, execution integrity, and cleanup are phase-attributable; every required phase passed; output stayed within bounds; and the receipt points to immutable evidence rather than embedding it.

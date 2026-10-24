---
name: mcp-gateway-release-verifier
description: Compose exact-artifact identity, schema, real-transport, execution-integrity, health, lifecycle, and cleanup evidence into one bounded MCP release verdict.
---

# MCP Gateway Release Verifier

Use this skill when a candidate MCP gateway or server needs release acceptance against the exact built artifact.

Read `STANDARD.md`, then collect phase evidence from the owning contracts instead of reimplementing them. Use `tools/compose_release_verdict.py` to build the bounded receipt.

The verifier composes candidate identity (#49), exact-candidate schema acceptance (#60), real-transport dogfood (#66), execution integrity (#67), bootstrap, isolation, and cleanup evidence. Local candidate acceptance also consumes identity-bound, exact-candidate trusted admission scope so migration and rerun requirements cannot be suppressed by caller input. A missing or failed required phase or missing trusted scope is never release confidence.

## Diagnostic composition versus authoritative acceptance

`compose_release_receipt` performs **diagnostic** composition: its `pass` verdict means the caller-supplied phase aggregate is well formed and bounded, never that release authority was proven. `compose_release_acceptance` performs **authoritative** release acceptance: every accepted phase must carry a typed evidence binding whose provider-backed execution record an injected authority independently resolves against the exact candidate revision. Missing, unknown, stale, cross-candidate, or unresolvable provenance is non-green. A PASS receipt grants no merge, publication, or deployment authority.

## Execution surface

`tools/compose_release_verdict.py` and `tools/local_candidate_lane.py` are library helpers reached through the owning workflow, not agent-invokable CLIs; no command-line entry point is advertised. The canonical probe client receipt is validated through the owning `mcp-server-architect` exact-candidate acceptance contract.

Feature-specific checks may be appended as bounded extension phases; they do not replace the baseline phases.

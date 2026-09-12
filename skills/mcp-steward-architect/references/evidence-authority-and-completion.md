---
description: Evidence classes, proof authority, subject binding, completion obligations, and bounded authority for MCP Stewards.
doc_id: reference.mcp-steward-evidence-completion
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Test exact-subject and freshness mismatches, lower-authority evidence, advisory model findings, unresolved ambiguities, completion waivers, and parent-authority boundaries against the configured proof recipes.
---

# Evidence, authority, and completion

A Steward must be able to answer two different questions: `what happened?` and `who/what is allowed to prove that claim?`.

## Evidence classes

Do not conflate intended/configured, observed, observed-effective, validated, and independently verified state. A configuration file is not proof that a live process loaded it. A green generic check is not proof of an arbitrary criterion. A worker saying `done` is not independent read-back.

Evidence should bind exact subject/revision or runtime generation, producer identity, observation method, authority class, timestamp/freshness, and digest. Where a proof recipe/policy controls semantics, evidence must also bind the recipe identity or provide producer attestation of it.

## Proof recipes

A proof recipe maps a claim/criterion to approved producers/probes, required subject dimensions, freshness, and sufficiency. The Steward should not accept a generic successful probe for an unrelated free-text criterion.

Model findings are advisory by default. For irreversible negative decisions, require reproduction through a stronger approved producer unless the profile explicitly grants the model a higher class.

## Completion obligations

Model completion as obligations, not narrative confidence. Each required obligation has status such as pending, satisfied, blocked, deferred/waived with authority, or not-applicable. `Completed` is legal only when the profile's required obligations are resolved, required evidence is current for the active subject/generation, no unresolved mandatory ambiguity remains, and the current lineage still owns publication.

The Steward's completion authority ends at its declared boundary. A verification Steward can finish a verification job without owning project task closure; a diagnostic Steward can finish a diagnosis without gaining apply authority.

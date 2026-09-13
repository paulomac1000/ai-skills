---
description: Evidence classes, proof authority, subject binding, completion obligations, transition preconditions, and bounded authority for MCP Stewards.
doc_id: reference.mcp-steward-evidence-completion
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Test exact-subject and freshness mismatches, lower-authority evidence, false caller-declared authority, advisory model findings, unresolved ambiguities, completion waivers, discoverable transition preconditions, and parent-authority boundaries against the configured proof recipes.
---

# Evidence, authority, and completion

A Steward must be able to answer two different questions: `what happened?` and `who/what is allowed to prove that claim?`.

## Evidence classes

Do not conflate intended/configured, observed, observed-effective, validated, and independently verified state. A configuration file is not proof that a live process loaded it. A green generic check is not proof of an arbitrary criterion. A worker saying `done` is not independent read-back.

Evidence should bind exact subject/revision or runtime generation, producer identity, observation method, authority class, timestamp/freshness, and digest. Where a proof recipe/policy controls semantics, evidence must also bind the recipe identity or provide producer attestation of it.

## Authority is effective identity, not a label

Caller-supplied metadata such as `evidenceAuthority=peer`, `verified=true`, a provider display name, or prose claiming independent review does not create authority. The Steward derives authority from authenticated/effective principal, producer identity, configured trust/policy, and the evidence channel that actually produced the observation.

If the same principal/session/attempt performed the implementation and the profile requires independent verification, relabeling its evidence as `peer` must fail. An independently produced artifact may be admissible only when its producer identity/provenance can be bound and the completion/verification policy explicitly accepts that authority class.

## Proof recipes

A proof recipe maps a claim/criterion to approved producers/probes, required subject dimensions, freshness, and sufficiency. The Steward should not accept a generic successful probe for an unrelated free-text criterion.

Model findings are advisory by default. For irreversible negative decisions, require reproduction through a stronger approved producer unless the profile explicitly grants the model a higher class.

## Discoverable transition preconditions

If a verification/completion/update transition requires facts that the Steward already knows, expose those requirements before the caller attempts the mutation. Typical preconditions include:

- exact subject/repository/runtime revision or semantic generation;
- current task/job/lease/assignment identity;
- verification or completion profile/recipe;
- required authority class and whether the current principal satisfies it;
- required evidence axes/fields and freshness;
- unresolved ambiguity or blocking gaps;
- safe next semantic action when a prerequisite is missing.

A consumer should not need to guess commit SHAs, drain unrelated queue items, repeatedly submit updates, or parse changing prose errors merely to discover a deterministic contract already present in durable state.

Rejected transitions should return a typed unmet-precondition result with the expected authoritative identity/reference when disclosure policy allows it. Errors remain fail-closed, but fail-closed is not an excuse for hiding known prerequisites.

## Completion obligations

Model completion as obligations, not narrative confidence. Each required obligation has status such as pending, satisfied, blocked, deferred/waived with authority, or not-applicable. `Completed` is legal only when the profile's required obligations are resolved, required evidence is current for the active subject/generation, no unresolved mandatory ambiguity remains, and the current lineage still owns publication.

A `superseded`, `waived`, or `deferred` obligation is not self-authorizing. The transition must bind the replacement/waiver/defer reason and the authority allowed to make that change. Caller-controlled status fields alone must not open the completion gate.

The Steward's completion authority ends at its declared boundary. A verification Steward can finish a verification job without owning project task closure; a diagnostic Steward can finish a diagnosis without gaining apply authority.

## Completion/publication check

Immediately before sealing an actionable terminal handoff, re-read mutable publication inputs that can invalidate the decision: current lineage/generation, exact subject/revision, required evidence freshness, unresolved external-operation ambiguity, and required effective authority. A result that became stale while work was running may be retained as historical evidence but cannot publish as the current decision.

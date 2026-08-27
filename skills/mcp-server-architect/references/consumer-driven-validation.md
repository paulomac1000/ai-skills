---
description: Consumer-driven validation model that turns real downstream migrations into permanent ai-skills regression canaries.
doc_id: reference.mcp-consumer-driven-validation
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Validate contracts/consumer-feedback.yaml, run the consumer-canary CI job against every immutable revision in contracts/consumer-canaries.yaml, and review drift before changing normative migration guidance.
---

# Consumer-driven validation

## Why canaries exist

Synthetic generators prove a baseline, but they do not prove that an existing repository can be discovered and migrated without false assumptions. Reusable findings from real migrations therefore become one of three artifacts: a standard invariant, an executable validator, or an immutable external consumer canary. New prose without one of those enforcement paths is incomplete remediation.

`contracts/consumer-feedback.yaml` is the lesson ledger. Every accepted field incident records the observed failure mode, the generalized invariant, one canonical owner, and exact `tests/file.py::test_name` regression selectors. `contracts/validate_consumer_feedback.py` rejects stale anchors, missing tests, duplicate incidents, and unknown consumer-canary references. This keeps “lessons learned” from becoming an unaudited prose backlog.

## Cheap source canary

`check_consumer_canaries.py` fetches exact public commit SHAs, never executes consumer code, and runs the bounded read-only inspector plus the executable adoption planner. Every catalog entry declares `proof_level: source-inspection`. The catalog records only facts that discovery must continue to identify correctly. This lane is safe for every pull request and catches regressions in SDK routing, upstream discovery, packaging, external-test discovery, applicability projection, and progressive planning.

A source canary does **not** prove that the consumer starts, that a hook reaches the effective prompt, that an MCP tool executes, or that an integration activates. Those are behavior claims and require a behavior canary.

The canary catalog is intentionally the only repository file allowed to contain the concrete consumer repository names. Those names are regression evidence, not normative examples or domain-specific guidance.

## Behavior canaries

A compatibility or shape probe proves only the property it actually exercised. Field presence, importability, schema compatibility, or a discovered configuration key must never be reported as proof that the runtime uses that field.

A behavior canary exercises the public path in a fresh process/session and records the exact subject/build version, exact argv or public operation, and observed sentinel/result. For durable instruction claims, store that observation in the runtime-probe format consumed by `contracts/validate_operational_claims.py`. A stale version, changed argv, non-fresh context, or mismatched observed value invalidates the claim.

External prerequisites may make a behavior canary unavailable. Record `not executed` or keep the claim unresolved; never promote a source-only or shape-only pass into runtime support.

## Required validation ladder

Consumer feedback is promoted in this order:

1. reproduce the downstream failure on an immutable consumer revision or preserve an operator field report with concrete evidence;
2. reduce it to the smallest reusable fact or boundary;
3. record it in `contracts/consumer-feedback.yaml` with a canonical owner;
4. encode that boundary in a schema, validator, planner rule, contract-diff rule, or other executable control;
5. add an exact regression selector that fails for the historical mistake;
6. when consumer discovery is involved, run source-only discovery and planning against the pinned real consumer canary;
7. require the normal exact-head repository gate before the remediation is accepted.

A new normative paragraph without steps 3-5 is incomplete. A synthetic test without an immutable real-consumer canary is useful but does not close a consumer-discovery regression by itself. Conversely, incidents about local-gate environment isolation or runtime instruction drift do not need an artificial MCP consumer canary when the reusable failure can be reproduced directly.

## Public-contract and SemVer gate

For an existing MCP server, capture a baseline contract before intentional public changes and a candidate contract from the exact built artifact afterward. `capture_mcp_contract.py` executes an exact no-shell probe, strips provider approval credentials from the probe environment, requires the observed source SHA and artifact digest to match caller-supplied identities, and canonicalizes the snapshot under `contracts/mcp-public-contract.schema.json`.

`compare_mcp_contracts.py --check` classifies removed tools/transports, new required inputs, changed field schemas, authentication/target selection, error contract, pagination, and retry semantics as breaking. Additive tools, transports, optional inputs, and output guarantees require at least a minor version. The gate fails when the candidate server SemVer is too small for the observed change.

This gate does not replace upstream-contract discovery. Public MCP inputs remain canonical; backend-only date, money, enum, field-name, and identifier dialects are converted inside the adapter and must have negative boundary tests proving that upstream-only forms do not leak back into the public contract.

The read-only adoption planner also exposes the declared Python MCP SDK requirement. A range wider than one exact pin is reported as `requires-compatibility-evidence`; the project must either narrow the claim or provide compatibility lanes that actually cover the range.

## Full consumer exercise

A heavier consumer exercise may run on a reviewed immutable consumer revision when it executes without protected credentials. It should build the consumer artifact, prove imports come from the installed artifact, use the public MCP composition and official client, and validate generated assessment/evidence records. Live backend prerequisites remain `external prerequisite unavailable / not executed`; absence of credentials is never converted into a pass.

Never give assessed consumer code provider credentials used to approve its own evidence. Provider correlation and acceptance remain separate trusted steps.

## Live and deployment observations

Hosted artifact tests and live upstream observations prove different facts. A real environment check is recorded with `contracts/deployment-observation.schema.json` and validated by `contracts/validate_deployment_observation.py`. The record binds the exact source revision, artifact digest, deployment identity, environment class, exact argv, actor, and result digest. When the required live environment or credential is unavailable, the result is `not-executed` with a reason; it is never promoted to `passed`.

Deployment observations are supplementary execution evidence. They do not grant candidate code provider credentials and do not replace provider-backed exact-SHA acceptance for the artifact itself.

## Promotion rule

A consumer incident is generalized only after reproducing the actual failure or preserving a concrete field observation. The preferred loop is `consumer failure -> minimal fact discovery -> feedback ledger -> generic invariant -> executable check -> consumer canary when applicable -> exact-head repository gate`. A bot suggestion or theoretical edge case without a reproduced contract violation does not outrank this loop.

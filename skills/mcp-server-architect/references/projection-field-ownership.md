---
description: Field-level ownership, automation capability admission, drift classification, and external-work fencing for writable projections.
doc_id: reference.mcp-projection-field-ownership
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Exercise advisory, canonical, shared-region, external-execution, unknown-field, high-confidence, and duplicate-work scenarios.
---

# Projection field ownership and external automation

Use this profile when a canonical control plane projects state into a writable
provider object that humans, bots, or external agents can also mutate. Resource
ownership alone is insufficient: every semantic field or namespace has an
explicit revisioned ownership rule.

## Ownership classes

- `canonical_owned`: external mutation is drift and canonical state wins through reconciliation.
- `external_advisory`: external mutation is preserved as UI/evidence metadata but never becomes domain authority.
- `shared_managed_regions`: one provider field has named canonical-managed regions; admitted external regions survive reprojection.
- `external_execution`: mutating the field/action starts real external work and is governed as a side effect.
- `unknown`: newly observed semantics fail conservative until classified.

Provider confidence, rationale, suggestion status, or provider approval
threshold are bounded evidence only:

`confidence/rationale != authorization != canonical ownership != side-effect admission`.

A coarse repository/global auto-approval threshold therefore cannot protect
canonical fields by itself.

## Capability-scoped external automation

Automation authority is granted by trusted local policy as exact
`field -> action set` capabilities plus admitted side-effect classes. Do not
derive an implicit fields×actions cross-product. Shared fields additionally
scope automation to named external regions; a whole-field grant cannot overwrite
a canonical-managed region. Prefer provider field/tool allowlists where
available; prompt-only instructions do not widen authority.

A triage capability may allow advisory labels, human-facing assignment metadata,
or suggestions while denying canonical lifecycle/priority, close/resolve,
protected managed regions, and work-starting agent assignment.

## Work-starting metadata

An agent assignment, deployment-bot selector, fulfillment field, or equivalent
work-start signal is `external_execution`, not ordinary metadata. Its capability
names both executor and execution environment. External assignment is not a
canonical lease/claim.

On observation, canonical scheduling either prohibits/reverts the external
execution, blocks until reconciliation, or explicitly adopts it through a
separately authorized lifecycle. An unreconciled/adopted external worker blocks
a second canonical worker; only no external work or terminal reconciliation
permits a fresh canonical claim. Qualification from an unrelated execution
environment is not inherited.

## Shared fields and drift health

Shared-field reconciliation updates only declared managed regions and preserves
admitted external enrichment; whole-field last-writer-wins is not the ownership
model. Drift is classified separately as
`canonical_field_drift`, `advisory_metadata_change`,
`external_execution_conflict`, `shared_region_conflict`, or
`unknown_field_policy`. Advisory changes may remain healthy while canonical,
execution, shared-region, and unknown-policy conflicts are actionable according
to policy.

Audit evidence may retain bounded actor/automation identity, provider
confidence/rationale, changed field, safe old/new digests, policy revision, and
reconciliation outcome. Evidence cannot self-promote authority.

## Provider-neutral example

For a GitHub issue projection, advisory labels and human assignee can remain
external advisory metadata; lifecycle and managed priority remain canonical;
a description can preserve human notes outside a managed status region; and
assignment to a coding agent is an external-execution side effect with an
explicit executor/environment boundary. The same model applies to Jira,
Linear, Trello, ServiceNow, and equivalent writable projections.

The concrete consumer/evidence case is `project-steward-mcp#123`; its provider
implementation remains there rather than being duplicated here. Strict OpenCode
execution-environment admission remains owned by `opencode-stack-guides#195`.

---
description: Source-qualified identity, collision handling, resource re-export, subprocess isolation, and schema preservation for MCP gateways.
doc_id: reference.mcp-gateway-aggregation
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Exercise duplicate names and URIs, case/truncation collisions, stale source generations, prompt composition, schema passthrough, and minimized stdio child environments.
---

# Source-qualified gateway aggregation

Use this reference when one MCP surface aggregates tools, prompts, resources,
resource templates, or extension-owned references from multiple upstream
servers. The gateway owns its exported namespace; upstream source/name/URI
remain provenance and routing inputs. Delimiter, digest algorithm, and rewritten
URI syntax are implementation-owned; determinism, boundedness, exact routing,
provenance, and collision handling are normative.

## Canonical identity and surfaces

Derive one gateway identity from stable upstream source identity, component kind,
and exact upstream identity. Keep source namespace, manifest revision,
registration generation, and original name/URI/template with the mapping.
List/search/detail and invoke/task/subscription use that same identity.

Normalization is display-only. Case folding, punctuation cleanup, truncation,
registration/discovery order, or source health cannot merge components or pick a
winner. An unrepresentable or duplicate canonical identity is a controlled
collision, never first-wins or silent dropping.

## Resources, prompts, and schemas

Upstream resource URI spaces are source-local. Re-export with a gateway-owned
reference that validates to exactly one current source and original URI/template;
rewriting is routing projection, not semantic identity or transferred authority.
Reads, completions, notifications, subscriptions, and extension metadata use the
same mapping.

Same-named upstream prompts remain separate. Composite prompts are explicit
gateway-owned components with source-qualified inputs; implicit prompt merging is
forbidden. Preserve valid upstream schema shapes unless a reviewed adapter owns
a documented transformation; do not coerce arrays, scalars, unions, or boolean
schemas to objects.

## Authority and stale mappings

Resolve a canonical identity to one current registration and component before
I/O, then apply current policy using preserved provenance. Source removal,
manifest replacement, or registration-generation change makes the old mapping
stale. Unhealthy or removed sources never fall back to a same-named source.
Re-registration may preserve the canonical identity only after explicit refresh
against the new generation.

## Stdio and subprocess sources

Child processes start from an explicit minimized environment. Ambient host tokens,
cloud credentials, and unrelated source secrets are absent unless explicitly
allowed; source-specific credentials do not become ambient credentials for other
children. Protocol stdout remains MCP-only; stderr diagnostics use the existing
safe diagnostic-egress policy.

## Verification matrix

Exercise equal/normalized names; case and truncation collisions; reversed order
and degraded health; forced collision; source removal/re-add; overlapping
resource URIs and tampered references; same-named/composite prompts; non-object
schema shapes; minimized child environments; and provenance continuity across
discovery, invocation, task, and resource resolution.

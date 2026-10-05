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
servers. The gateway owns its exported identity namespace; upstream names and
URIs remain provenance and routing inputs rather than global authority.

Delimiter, digest algorithm, and rewritten URI syntax are implementation-owned;
only determinism, boundedness, exact routability, provenance, and collision
handling are normative.

## Canonical identity and surfaces

For every exported component, derive one bounded deterministic gateway identity
from the stable upstream source identity, component kind, and exact upstream
identity. Keep the raw source namespace, manifest revision, registration
generation, and original name/URI/template alongside the mapping.

The same canonical identity is returned by list/search/detail and accepted by
invoke, task, subscription, completion, and extension paths for that component.
Display normalization is not identity. Case folding, punctuation cleanup,
truncation, registration order, source health, or discovery order MUST NOT merge
components or choose a winner.

If two distinct components would produce the same canonical gateway identity,
fail with a controlled collision/conflict. Never silently drop one, use
first-wins, or redirect to a healthy same-named source.

## Resources and templates

Upstream resource URI spaces are source-local. Two sources may legitimately use
the same URI. Re-export through a gateway-owned reference that resolves to
exactly one current source and the original URI/template. Validate the gateway
reference before routing; it cannot escape or select another source namespace.

A rewritten URI/reference is a routing projection only. It does not change the
upstream semantic identity, transfer authorization, or make the upstream URI
globally unique. Reads, completions, notifications, subscriptions, and
extension metadata use the same mapping.

## Prompts and schemas

Same-named prompts from separate sources remain separate components. A prompt
that combines upstream prompts is an explicit gateway-owned component with its
own identity and explicit source-qualified upstream references; implicit prompt
merging is forbidden.

Preserve the upstream public schema unless a reviewed adapter owns a documented
transformation. Do not coerce valid array, scalar, union, boolean-schema, or
other protocol-valid shapes into object-only output merely to fit a gateway
implementation.

## Authority, stale mappings, and source health

Before invocation/read, resolve the canonical identity to exactly one current
source registration and original component, then apply current policy and
authorization using the preserved manifest/source provenance. Source removal,
manifest replacement, or registration-generation change makes old mappings
stale until explicitly refreshed. An unhealthy or removed source cannot cause
fallback to another source with the same normalized name.

Stable source re-registration may retain the same deterministic canonical
component identity, but the old generation is not current authority. Refresh
the mapping against the new registration before use.

## Stdio and subprocess sources

Gateway-owned child processes start from an explicit minimized environment.
Only allowlisted host variables and source-specific configured values are
forwarded. Ambient host tokens, cloud credentials, or unrelated source secrets
are not inherited by default and source-specific credentials do not become
ambient credentials for every child.

Protocol stdout remains reserved for MCP traffic. Diagnostics go to stderr and
follow the existing diagnostic-egress/sanitization policy before they become
operator- or model-visible.

## Verification matrix

At minimum exercise:

- equal and normalization-equivalent tool names from independent sources;
- length/truncation and case collisions in both source and component identity;
- reversed registration/discovery order and degraded source health;
- forced canonical-ID collision with a controlled conflict outcome;
- source removal and re-add with a changed registration/manifest generation;
- overlapping resource URIs/templates and tampered gateway references;
- same-named prompts plus explicit composite-prompt construction;
- arbitrary valid output-schema shapes without object coercion;
- subprocess environment minimization with host secrets and per-source credentials;
- provenance continuity across list/search/detail/invoke/task/resource resolution.
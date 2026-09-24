---
description: Preserve an Agent Skills-compatible discovery core while projecting ai-skills governance and host-specific capabilities without creating a second policy owner.
doc_id: reference.skill-architect-upstream-compatibility
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Confirm that SKILL.md remains usable as the discovery/router entrypoint without host-specific metadata and that any package projection preserves relative resource routes and STANDARD.md authority.
---

# Upstream Agent Skills compatibility

Read this reference when a skill will be consumed outside this repository or
projected into a host that implements the Agent Skills convention.

## Portable discovery core

Keep the portable discovery surface centered on a skill directory containing
SKILL.md with name and description metadata. The ai-skills repository adds
STANDARD.md, manifest.yaml, and governed resource categories as stronger
engineering contracts, but a generic host must not be assumed to understand
those extensions automatically.

SKILL.md therefore remains a usable router: it names STANDARD.md when normative
decisions are required and uses relative resource paths rather than depending on
repository-global hidden state.

## Resource projection

Upstream hosts may recognize conventional resource directories such as
references, scripts, or assets. This repository currently owns different
runtime categories where they better express its governance model, including
tools and templates.

Do not rename the canonical ai-skills package opportunistically for one host.
When a host requires a different layout, use a thin packaging projection that
maps equivalent resources while preserving their content identity and routes.
The projection does not become a new policy owner.

Do not add a new ai-skills resource category merely because an upstream format
permits it. Add a category when a real reusable task needs that resource type
and repository contracts can validate it.

## Host-specific invocation

A host may support explicit-only invocation, implicit discovery, UI metadata,
dependency installation, or additional permission controls. Express those
capabilities in a host adapter or generated projection. Do not place
host-specific fields into the portable SKILL.md frontmatter when doing so would
break the repository's portable contract.

High-impact skills should use the narrowest host invocation policy that matches
their intended workflow, but the canonical semantic activation boundary remains
the skill description and standard rather than a vendor UI setting.

## Compatibility evidence

Separate semantic portability from tested host compatibility. A skill can have
a portable core without claiming that every host, model, packaging adapter, or
tool runtime has been exercised.

Host compatibility claims identify the exact projected package, host/runtime
version, model or routing context when material, and the evidence that was
actually executed. Unknown host behavior remains unverified rather than being
inferred from format similarity.

---
description: Reusable template for all documentation files — copy and populate for new documents
doc_id: ref.docs-template
type: ref
status: active
rigor_tier: L2
ttl_days: 365
stability: frozen
ai_scope: editable
source_of_truth: true
upstream:
  - ref.documentation-standard
last_verified: 2026-05-08
owners: ["docs-maintainers"]
---

# Document Template

> [!NOTE]
> This is the ONLY template for creating new documentation files. Do NOT use any other template.
>
> 1. Copy this file to the target directory
> 2. Replace all `<placeholder>` values
> 3. Remove sections that do not apply (but keep the header with `N/A`)
> 4. Delete this callout block

> [!TIP]
> **Before filling this template**, read [ref.documentation-standard](../skills/afds-doc-writer/docs_standards.md). Quick syntax rules: Canonical Language (English as canonical source; translations allowed as derived documents). Active voice. Prefer bulleted lists for complex conditions. RFC 2119 modals (`MUST`, `SHOULD`, `MAY`). Banned ambiguity words: `might`, `maybe`, `probably`, `simply`, `just`. No emoji, no HTML (comments allowed). Filename = `doc_id` in kebab-case. CHANGELOG is append-only format; required only for `contract.*` and `decision.*` documents.

---

## PURPOSE

<1-3 sentences. Active voice. No filler. What does this document cover?>

## SCOPE

- INCLUDED: <what this document covers>
- EXCLUDED: <what this document intentionally does not cover>

## DEFINITIONS

- `<term>`: <precise, non-circular definition>

## RULES

1. System MUST <required behavior>
2. System MUST NOT <prohibited behavior>
3. IF <condition> THEN <action>

## INTERFACES

**INPUT:**
- `<param>`: `<type>` | `<constraints>`

**OUTPUT:**
- `<param>`: `<type>` | `<guarantees>`

**SIDE_EFFECTS:** <list or N/A>

## STATE

**Assumptions:**
- <assumption 1>

**Constraints:**
- <constraint 1>

**Known Limitations:**
- <limitation 1>

## EDGE_CASES

- CASE: <condition> → EXPECTED: <deterministic behavior>

## EXAMPLES

**EXAMPLE 1 — Valid Input:**
- INPUT: `<value>`
- OUTPUT: `<value>`
- RATIONALE: <why this matches RULES>

**EXAMPLE 2 — Invalid Input:**
- INPUT: `<value>`
- OUTPUT: `<error or fallback>`
- RATIONALE: <which rule this violates>

## NON_GOALS

- <what this document intentionally does not cover>

---

## Frontmatter Template

Copy the matching frontmatter below based on document type:

### Workflow (`workflow.*`)

```yaml
---
description: <one sentence, no period>
doc_id: workflow.<name>
type: workflow
status: active
rigor_tier: L2
ttl_days: 90
stability: stable
ai_scope: editable
trigger:
  user: ["<trigger phrase 1>", "<trigger phrase 2>"]
  event: <event type>
timeout: 60
upstream:
  - <doc_id this depends on>
last_verified: <YYYY-MM-DD>
owners: ["<team-name>"]
---
```

### Reference (`ref.*`)

```yaml
---
description: <one sentence, no period>
doc_id: ref.<name>
type: ref
status: active
rigor_tier: L2
ttl_days: 180
stability: stable
ai_scope: editable
domain: <domain>
tags: ["<tag1>", "<tag2>"]
upstream:
  - <doc_id this depends on>
last_verified: <YYYY-MM-DD>
owners: ["<team-name>"]
---
```

### System (`sys.*`)

```yaml
---
description: <one sentence, no period>
doc_id: sys.<name>
type: system
status: active
rigor_tier: L2
ttl_days: 90
stability: stable
ai_scope: editable
domain: <domain>
tags: ["<tag1>", "<tag2>"]
upstream:
  - <doc_id this depends on>
last_verified: <YYYY-MM-DD>
owners: ["<team-name>"]
---
```

### Guide (`guide.*`)

```yaml
---
description: <one sentence, no period>
doc_id: guide.<name>
type: guide
status: active
rigor_tier: L1
ttl_days: 180
stability: stable
ai_scope: editable
tags: ["<tag1>", "<tag2>"]
upstream:
  - <doc_id this depends on>
last_verified: <YYYY-MM-DD>
owners: ["<team-name>"]
---
```

### Decision (`decision.*`)

```yaml
---
description: <one sentence, no period>
doc_id: decision.<NNN>-<slug>
type: decision
status: accepted
rigor_tier: L3
ttl_days: 0
stability: frozen
ai_scope: review_only
source_of_truth: true
upstream:
  - <ref.* doc this decision relates to>
last_verified: <YYYY-MM-DD>
owners: ["<team-name>"]
---
```

### Contract (`contract.*`)

```yaml
---
description: <one sentence, no period>
doc_id: contract.<service>-v<version>
type: contract
status: active
rigor_tier: L3
ttl_days: 0
stability: stable
ai_scope: editable
source_of_truth: true
upstream:
  - <sys.* or ref.* this contract implements>
last_verified: <YYYY-MM-DD>
owners: ["<team-name>"]
version: 1.0.0
---
```

### Integration (`int.*`)

```yaml
---
description: <one sentence, no period>
doc_id: int.<name>
type: integration
status: active
rigor_tier: L2
ttl_days: 180
stability: stable
ai_scope: editable
source_of_truth: true
upstream: []
last_verified: <YYYY-MM-DD>
owners: ["<team-name>"]
---
```

---

## Frontmatter Quick Reference

### Required Fields (all types)

| Field | Type | Valid Values |
| ----- | ---- | ------------ |
| `description` | string | One sentence, no trailing period |
| `doc_id` | string | `<type>.<name>` — lowercase, dots |
| `type` | enum | `workflow` \| `ref` \| `system` \| `guide` \| `decision` \| `contract` \| `integration` |
| `status` | enum | `active` \| `draft` \| `deprecated` \| `evolving` \| `archived` |
| `rigor_tier` | enum | `L0` \| `L1` \| `L2` \| `L3` |
| `ttl_days` | integer | `0`–`365`; `0` for permanent or deprecated |

### Optional Fields

| Field | Type | Default | Notes |
| ----- | ---- | ------- | ----- |
| `stability` | enum | `stable` | `experimental` \| `stable` \| `frozen` |
| `ai_scope` | enum | `editable` | `editable` \| `review_only` \| `restricted` |
| `domain` | string | — | Lowercase identifier for discovery |
| `tags` | list | `[]` | Lowercase strings |
| `upstream` | list | `[]` | Valid `doc_id` values this doc depends on |
| `supersedes` | string | `null` | `doc_id` this document replaces |
| `superseded_by` | string | `null` | `doc_id` that replaces this document |
| `source_of_truth` | boolean | `true` | Whether this file defines authoritative facts |
| `owners` | list | `[]` | Team or role identifiers for maintenance |
| `doc_kind` | enum | `atomic` | `atomic` \| `composite` \| `translation` |
| `ttl_policy` | enum | `standard` | `standard` \| `extended` \| `permanent` \| `event_driven` |
| `version` | string | — | SemVer; contract.* only |

### Workflow-Only Fields

| Field | Type | Required | Notes |
| ----- | ---- | -------- | ----- |
| `trigger` | object | Required | User commands and event |
| `timeout` | integer | Optional | Seconds, default 120 |
| `scope` | string | Optional | `read-only` or `read-write` |

---

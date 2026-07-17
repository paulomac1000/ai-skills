---
description: Normative rules for evidence-based, retrievable, maintainable technical documentation.
doc_id: reference.afds-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Run `python skills/afds-doc-writer/validate.py README.md skills` and `python -m pytest`.
---

# AFDS documentation standard

## Purpose

This standard defines how technical documentation is selected, structured, verified, and maintained. It optimizes for two readers at once: humans who need clear decisions and procedures, and agents that need reliable retrieval and bounded context.

## Core rules

1. **Evidence before prose.** Factual claims come from implementation, configuration, tests, runtime evidence, authoritative specifications, or an explicitly accepted decision.
2. **One canonical owner.** Every durable fact has one authoritative location. Other documents link to it rather than restating it.
3. **Answer first.** Put the operational answer, contract, decision, or procedure before background.
4. **Retrieval is designed.** Titles, identifiers, summaries, aliases, and headings use terms that readers are likely to search for.
5. **Statement kinds remain distinct.** Requirements, observations, examples, assumptions, and hypotheses are never presented as equivalent.
6. **Volatile facts belong to automation.** Dependency versions, generated inventories, timestamps, hashes, and measured results come from executable sources.
7. **Human readability remains mandatory.** Metadata supports retrieval and validation but never replaces clear prose.
8. **Historical material earns its place.** Keep it only when it changes current operation, compatibility, migration, or auditability.

## Document selection

Choose one primary type based on the question being answered.

| Type | Primary question | Required content |
| --- | --- | --- |
| `workflow` | How is an operation performed safely? | Preconditions, ordered steps, validation, recovery or safe stop |
| `reference` | What facts or rules must be looked up? | Scope, definitions, constraints, examples, non-goals |
| `system` | How does a system behave and fail? | Responsibility, boundaries, interfaces, state, failure modes, observability |
| `guide` | How can a reader learn or adopt something? | Audience, outcome, explanation, walkthrough, trade-offs, pitfalls |
| `decision` | Why was one option selected? | Context, decision, alternatives, consequences, review trigger |
| `contract` | What must producers and consumers exchange? | Inputs, outputs, errors, compatibility, security, examples |

Do not combine multiple document types merely to avoid creating a clear canonical owner. Split content when the readers, lifecycle, or verification method differs.

## Required metadata

Governed Markdown files use YAML frontmatter:

```yaml
description: One sentence stating the question answered
doc_id: <type>.<stable-slug>
type: workflow | reference | system | guide | decision | contract
status: draft | active | evolving | deprecated | archived
rigor: informative | operational | normative
owners: [team-or-role]
verification: Concrete command, check, or review method
```

Rules:

- `doc_id` is stable and starts with the selected document type.
- `description` contains searchable domain terms and the intended outcome.
- `owners` names a role or team, not an unavailable individual by default.
- Operational and normative documents include a non-empty `verification` field or a dedicated `## Verification` section.
- Optional fields such as `aliases`, `entities`, `upstream`, and `supersedes` are used only when they carry real information.
- Automation-owned fields such as timestamps, semantic hashes, generated backlinks, dependency inventories, and fitness scores are not handwritten.
- Internal schema or standard version numbers are not required. Repository releases and Git history provide change tracking.

## Structure

Every governed document has exactly one H1. Use H2 sections to separate independently retrievable answers. Avoid duplicate or cosmetic headings.

Recommended order:

1. purpose or direct answer;
2. scope and boundaries;
3. required behavior or procedure;
4. failure, recovery, or exceptions;
5. verification;
6. references needed to operate the result.

The order may change when the document type has a clearer natural sequence. Do not force empty sections into a universal template.

## Evidence and uncertainty

- Cite repository paths, commands, test names, logs, or authoritative external sources when a claim depends on them.
- Mark assumptions explicitly and state what would verify them.
- Record unresolved questions separately from accepted behavior.
- Do not convert a plausible inference into a fact.
- When sources disagree, present the conflict and name the authority used for the current decision.

## Canonical ownership

Before adding content, search for an existing owner. Update that owner when possible.

Acceptable duplication is limited to:

- a short summary that links to the owner;
- an example that is clearly labeled as non-authoritative;
- generated output whose source is identified;
- a migration note that compares old and new behavior.

Do not maintain parallel standards, quick-reference copies, matrices, or agent-specific rewrites that can drift independently.

## Links and examples

- Relative links resolve from the containing document.
- Link titles and angle-bracket destinations are valid Markdown and must not be treated as part of the filesystem path.
- Code fences may contain example headings and links; structural validation ignores them.
- Examples are realistic but project-independent unless the document explicitly governs one project.
- Secrets, private endpoints, personal infrastructure, and proprietary data never appear in reusable examples.

## Lifecycle

- `draft`: incomplete and not authoritative;
- `active`: current canonical guidance;
- `evolving`: usable but intentionally changing;
- `deprecated`: retained only for migration and linked to the replacement;
- `archived`: historical, not part of current operation.

A first stable release should exclude development laboratories, duplicated drafts, discarded alternatives, temporary reports, and generated review artifacts. Preserve history in Git and the root changelog instead of shipping process debris.

## Quality gates

A governed document is acceptable when:

- metadata is valid and complete;
- exactly one H1 exists outside fenced examples;
- headings are unique after normalization;
- relative links resolve;
- operational and normative content names a concrete verification method;
- claims are supported by implementation evidence or clearly labeled uncertainty;
- the document has one canonical purpose and no obsolete duplicate.

## Verification

Run the validator against the repository and execute the test suite. Reviewers additionally compare normative claims with the implementation or authoritative source they govern. Structural checks can prove consistency, but they cannot prove factual truth by themselves.

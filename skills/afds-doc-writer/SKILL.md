---
name: afds-doc-writer
description: Create, refactor, retrieve, or audit engineering documentation using AFDS. Use for architecture, runbooks, references, guides, decisions, contracts, documentation cleanup, and agent-facing knowledge bases.
---

# AFDS documentation engineer

Use `docs_standards.md` as the normative core. Do not load every reference by default.

## Route the task

| Task | Load |
|---|---|
| Choose a document type or write a document | `references/document-types.md` |
| Improve search, chunking, metadata, or agent retrieval | `references/retrieval-design.md` |
| Audit a repository or migrate old docs | `references/migration.md` |
| Change AFDS itself | `references/standard-evolution.md` and the benchmark suite |

## Operating procedure

1. Identify the user's concrete outcome and the evidence available in code, configuration, tests, issues, or runtime output.
2. Search for an existing canonical document before creating one.
3. Choose one document type. Split content only when two independent retrieval intents would otherwise compete.
4. Put the answer, contract, or procedure before background explanation.
5. Separate facts, decisions, assumptions, examples, and unresolved questions.
6. Use stable identifiers for entities, commands, settings, errors, and interfaces.
7. Link to canonical facts instead of copying them. Copy a short local invariant only when the document must remain usable during an incident.
8. Validate the result with `docs_validate.py` and repair blocking findings.
9. For repository-wide work, report documents created, merged, superseded, or deleted and list unresolved conflicts.

## Non-negotiable behavior

- Do not invent facts, versions, commands, paths, owners, dates, or system behavior.
- Do not force every document into the same long template.
- Do not ban ordinary uncertainty words globally. Mark uncertainty with evidence and impact.
- Do not update automation-owned metadata by hand.
- Do not duplicate normative rules in `SKILL.md` and references.
- Do not declare documentation complete without a validation method.

## Output contract

A completed documentation task includes:

- the changed document or patch,
- its type and canonical ID,
- evidence used,
- validation performed,
- conflicts or missing evidence that remain.

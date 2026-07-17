---
name: afds-doc-writer
description: Create, repair, validate, and maintain evidence-based technical documentation with explicit ownership and verification.
---

# AFDS document writer

Use this skill when documentation must become a durable operational asset rather than a narrative snapshot.

## Workflow

1. Identify the decision, contract, procedure, system behavior, reference question, or adoption outcome the document must own.
2. Locate existing canonical owners and upstream evidence before writing.
3. Choose one primary document type and one accountable owner role.
4. Put the answer or required behavior before background.
5. Separate verified facts, requirements, examples, assumptions, and unresolved questions.
6. Record failure, rollback, conflict, and downstream-review behavior when they affect safe operation.
7. Link rather than duplicate upstream facts.
8. Run the validator and the repository-specific verification named by the document.
9. Report affected downstream documents when a contract or decision changes.

Read `STANDARD.md` first. Use `references/type-playbooks.md` for document-specific structure and `references/lifecycle-and-impact.md` for ownership, conflict, review, and change propagation. Start from `templates/governed-document.md.template` only when no existing owner should be updated.

## Constraints

- Do not invent evidence or convert inference into fact.
- Do not hand-maintain volatile timestamps, hashes, dependency inventories, backlinks, or scoring metrics.
- Do not create a second source of truth to avoid editing the canonical owner.
- Do not force every document into an identical section list.
- Do not treat a structurally valid document as factually verified.

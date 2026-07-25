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

## Adoption and migration evidence

Before claiming that this skill has been adopted or a migration is complete:

1. Read the repository-root `contracts/adoption-assessment.yaml.template`, `contracts/rule-catalog.yaml`, compatibility matrix, and the selected skill manifest.
2. Create one assessment bound to the exact SHA and classify every stable rule as applicable, not applicable, or deferred with an owned waiver.
3. Bind each passed claim to a machine result file and passed test-case identity; a green job, badge, screenshot, or hand-written `passed` value is not evidence.
4. Use `verification_mode: provider-backed` only with the currently supported GitHub.com and GitHub Actions verifier. Other CI providers remain structural attestations until a reviewed adapter exists and cannot satisfy an approval gate.
5. Run `python contracts/validate_adoption.py <assessment> --require-approval` with read-only provider credentials before approval.
6. Require an independent review bound to the exact SHA. The reviewer must not be the PR author, a commit author or committer, or an actor that produced the referenced evidence.

Generated templates and examples are architecture seeds, not production acceptance. Apply the relevant CI/CD profile, verify the exact deployment artifact, record rollback and residual risk, and retain provider evidence long enough for the stated decision lifetime.

## Constraints

- Do not invent evidence or convert inference into fact.
- Do not hand-maintain volatile timestamps, hashes, dependency inventories, backlinks, or scoring metrics.
- Do not create a second source of truth to avoid editing the canonical owner.
- Do not force every document into an identical section list.
- Do not treat a structurally valid document as factually verified.

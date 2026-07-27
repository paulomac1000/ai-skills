---
description: Operational playbook for documentation ownership, conflicts, freshness, review triggers, and downstream impact.
doc_id: workflow.documentation-lifecycle-and-impact
type: workflow
status: active
rigor: operational
owners: [repository-maintainers]
verification: Exercise the change-impact checklist on a contract or decision change and run the AFDS validator.
---

# Documentation lifecycle and impact

## Purpose

This playbook governs what happens before, during, and after a durable document changes. It restores the useful lifecycle and dependency behavior from the earlier AFDS standard without requiring manually maintained scores or timestamps.

## Read protocol

1. Start with the document that directly owns the question.
2. Follow `upstream` only when the answer depends on a contract, decision, or source outside the document.
3. Stop when the required evidence is sufficient; do not load an entire documentation graph by default.
4. Treat `draft` content as non-authoritative and `deprecated` content as migration-only.
5. When two active sources disagree, do not silently combine them. Apply the conflict protocol.

## Write protocol

1. Search by domain terms, identifiers, aliases, and file paths.
2. Prefer updating the canonical owner over adding a new file.
3. Name the owner role and verification method.
4. Add upstream links only for actual dependencies.
5. Add downstream-review markers when consumers may need changes.
6. Preserve old behavior only when needed for migration, auditability, or compatibility.
7. Run structural and domain-specific verification.

## Conflict protocol

When sources disagree:

1. identify the conflicting statements and their provenance;
2. classify each as implementation evidence, configuration, test evidence, runtime observation, specification, accepted decision, or prose;
3. select the current authority according to the governed system;
4. update or deprecate the losing source rather than leaving parallel truth;
5. record uncertainty when authority cannot be resolved;
6. block unsafe operational changes until the conflict is resolved.

A conflict is not resolved by choosing the newest file timestamp. Git modification time is only a discovery hint.

## Change-impact protocol

A change requires downstream review when it modifies:

- a public input, output, error, or compatibility promise;
- a security or authorization boundary;
- an operational sequence, rollback path, or failure mode;
- a default that consumers rely on;
- an architecture decision or its review trigger;
- a reusable template or generated artifact contract.

For each affected consumer, choose one result:

- no change required, with reason;
- documentation update required;
- implementation update required;
- migration required;
- compatibility shim required;
- unresolved and blocked.

Use an explicit `NEEDS_DOWNSTREAM_REVIEW` marker only while the review is outstanding. Do not leave it as permanent metadata.

## Review triggers

Review a document when its implementation, specification, security boundary, supported runtime, public contract, or operational evidence changes. A fixed calendar review may be added for regulated or high-risk material, but a handwritten `last_verified` date is not proof of review.

## Deprecation and archive

A deprecated document names its replacement and migration effect. An archived document is historical and cannot be cited as current authority. Delete temporary agent reports and generated review artifacts after their durable findings are integrated.

## Safe stop

Stop the documentation change when ownership is unclear, sources materially conflict, the claimed behavior cannot be verified, or a contract change has unreviewed downstream impact. Report the blocker and the evidence needed to continue.

## Verification

Select one changed contract or decision, enumerate its downstream consumers, and confirm every consumer has an explicit review result. Then run the validator.

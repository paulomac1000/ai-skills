---
name: afds-doc-writer
description: Create, refactor, retrieve, or review technical documentation using evidence, canonical ownership, explicit verification, and compact structures that work for humans and AI agents.
---

# AFDS documentation writer

Read `STANDARD.md` before changing governed documentation.

## Workflow

1. Identify the exact question the document must answer and its intended reader.
2. Inspect implementation evidence: code, configuration, tests, runtime output, authoritative specifications, and accepted decisions.
3. Find the canonical owner of every factual claim before writing.
4. Select one document type: workflow, reference, system, guide, decision, or contract.
5. Put the answer, procedure, contract, or decision before history and rationale.
6. Separate verified facts, requirements, examples, assumptions, and unresolved questions.
7. Add only metadata that improves retrieval, ownership, or validation.
8. State a concrete verification method for operational or normative documents.
9. Run `validate.py` and the repository test suite.
10. Report evidence used and any claim that could not be verified.

## Constraints

- Do not invent commands, versions, paths, owners, dates, or behavior.
- Do not duplicate a canonical fact across multiple documents.
- Do not preserve historical scaffolding merely because it already exists.
- Do not use generated metrics, hashes, timestamps, or dependency versions as handwritten prose.
- Do not call a document complete without an observable verification method.
- Keep headings and retrieval terms specific enough to distinguish neighboring documents.

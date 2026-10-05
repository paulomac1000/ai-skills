---
afds_schema_version: 2
description: Negative AFDS decision fixture with an unexplained mandatory not-applicable consequence.
doc_id: decision.not-applicable-without-reason-fixture
type: decision
status: active
rigor: normative
owners: [repository-maintainers]
verification:
  kind: command
  value: Run the AFDS change-contract regression tests.
---

# Decision not-applicable reason fixture

## Decision

The decision is accepted and current.

Implementation claim: **complete**.

## Implementation consequences

| Kind | Consequence | Required | Resolution | Evidence |
| --- | --- | --- | --- | --- |
| implementation | Update the canonical implementation | yes | satisfied | `source:example@abc123` |
| rollback | Retain or explicitly waive the rollback path | yes | not_applicable | - |

## Verification

This fixture is intentionally invalid for implementation-completion semantics because the mandatory not-applicable consequence has no reason.

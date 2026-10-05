---
afds_schema_version: 2
description: Representative complete AFDS decision implementation fixture.
doc_id: decision.complete-implementation-fixture
type: decision
status: active
rigor: normative
owners: [repository-maintainers]
verification:
  kind: command
  value: Run the AFDS change-contract regression tests.
---

# Decision implementation fixture

## Decision

Adopt the selected design. Decision authority is accepted and current.

Implementation claim: **complete**.

## Implementation consequences

| Kind | Consequence | Required | Resolution | Evidence |
| --- | --- | --- | --- | --- |
| implementation | Update the canonical implementation | yes | satisfied | `source:example@abc123` |
| migration | Preserve the compatibility path | yes | satisfied | `migration:test-1` |
| verification | Prove the required acceptance criterion | yes | satisfied | `evidence:criterion/CRIT-1@run-1` |
| rollback | Retain a rollback path | no | not_applicable | Not required for this fixture |

## Downstream review

No additional consumer is affected.

## Verification

All declared mandatory consequences are resolved and required verification points to evidence.

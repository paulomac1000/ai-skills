---
afds_schema_version: 2
description: Representative incomplete AFDS decision implementation fixture.
doc_id: decision.incomplete-implementation-fixture
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

## Affected obligations and consumers

- `OBL-1` remains mandatory.
- The public caller and migration path are affected consumers.

## Implementation consequences

| Kind | Consequence | Required | Resolution | Evidence |
| --- | --- | --- | --- | --- |
| implementation | Update the canonical implementation | yes | satisfied | `source:example@abc123` |
| migration | Preserve the compatibility path | yes | satisfied | `migration:test-1` |
| rollout | Enable the new path after migration proof | yes | satisfied | `rollout:plan-1` |
| rollback | Retain the previous safe path until rollout acceptance | yes | satisfied | `rollback:plan-1` |
| cleanup | Remove the superseded path after acceptance | yes | satisfied | `cleanup:task-1` |
| verification | Prove the required acceptance criterion | yes | pending | - |

## Downstream review

No additional consumer is affected.

## Verification

This fixture is intentionally inconsistent: it claims implementation completion while required verification remains pending.

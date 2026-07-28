---
description: Maintain AGENTS.md instructions as a verified operational contract across repository changes.
doc_id: workflow.agents-md-lifecycle
type: workflow
status: active
rigor: operational
owners: [repository-maintainers]
verification: Complete the lifecycle gate on the exact revision and retain validator, test, and review results.
---

# AGENTS.md lifecycle and evidence

## Preconditions

Identify the affected instruction files, their scope, the canonical owner of each changed rule, the selected profile, and the exact repository revision.

## Change workflow

1. Reproduce the problem through a failed route, stale command, conflicting rule, missed safety boundary, or unnecessary context load.
2. Change the canonical implementation, standard, workflow, or documentation owner first when the instruction only reflects that source.
3. Update the smallest applicable root or nested instruction file.
4. Add or update an executable regression when the failure can be checked mechanically.
5. Validate every relative link and all profile requirements.
6. Run focused checks for changed behavior and the full repository gate.
7. Review the final diff for duplicated policy, generated files, secrets, private data, temporary names, and unrelated edits.
8. Bind the completion report to the exact revision and list skipped checks and residual risk.

## Evidence levels

| Claim | Minimum evidence |
| --- | --- |
| Link and structure are valid | Strict validator output |
| Command is current | Command exists and representative execution result |
| Local change is complete | Focused tests plus full local gate |
| Hosted compatibility is proven | Provider-backed job on the exact revision |
| Published artifact is accepted | Exact artifact identity and execution evidence |
| High-impact policy is adopted | Independent review bound to the exact revision |

## Rollback

Revert the instruction change when it routes agents to a missing owner, weakens a safety boundary, contradicts executable policy, or causes repeated task failures. Restore the last known valid instruction tree and open a focused correction rather than adding a competing file.

## Review cadence

Do not add hand-maintained timestamps merely to appear current. Trigger review from material repository changes and verify factual claims against current sources. Automation may record generated review metadata outside the authored contract.

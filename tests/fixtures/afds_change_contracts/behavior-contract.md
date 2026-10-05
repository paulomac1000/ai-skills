---
afds_schema_version: 2
description: Representative AFDS executable behavior contract fixture.
doc_id: contract.change-behavior-fixture
type: contract
status: active
rigor: normative
owners: [repository-maintainers]
verification:
  kind: command
  value: Run the AFDS change-contract regression tests.
---

# Executable behavior contract fixture

## Scope

This fixture owns observable behavior for one bounded change and excludes implementation design.

## Obligations

- `OBL-1`: the caller-visible operation preserves the prior compatibility promise.

## Acceptance criteria

- `CRIT-1`: given a compatible prior input, the observable result remains accepted.
- `CRIT-2`: given the declared invalid edge case, the operation returns the documented rejection.

## Assumptions

- The referenced machine schema remains the canonical wire-format owner.

## Examples

An example may illustrate `CRIT-1`, but it does not create a new requirement.

## Verification mapping

- `CRIT-1` -> `qa-change-verifier:criterion/CRIT-1`
- `CRIT-2` -> `qa-change-verifier:criterion/CRIT-2`

Executed PASS/FAIL results remain in CI/evidence records.

## Machine contract authority

The canonical machine-readable schema remains authoritative for exact fields and wire compatibility; this prose does not redefine it.

## Verification

Run the AFDS change-contract regression tests and the repository AFDS validator.

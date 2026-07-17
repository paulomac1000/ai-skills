---
description: Normative safety, efficiency, recovery, and verification rules for agents consuming MCP capabilities.
doc_id: reference.mcp-consumer-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Run the decision-engine tests and verify representative read, write, destructive, retry, pagination, and partial-failure workflows.
---

# MCP consumer standard

## Outcome before capability

Define the desired result before selecting a tool, resource, or prompt. Record the target, constraints, acceptable side effects, required evidence, and stopping condition.

Do not let capability names redefine the user's goal.

## Discovery and selection

- Use protocol discovery and load only relevant schemas.
- Choose by input, output, side-effect, authorization, and failure contract.
- Respect catalog and pagination scope; absence from a partial result is not proof of absence.
- Prefer fewer calls when a batch or workflow capability preserves policy boundaries and verification.
- Prefer summary or search before high-volume detail retrieval.
- Keep stable identifiers from discovery rather than reconstructing targets from display text.
- When two capabilities overlap, choose the narrower contract that fully satisfies the outcome.

## Capability profile

Classify each invocation by:

- effect: read, write, destructive, dangerous, or unknown;
- data sensitivity;
- target scope;
- reversibility and idempotency;
- retry safety;
- authorization evidence;
- server confirmation requirement;
- user intent and specificity.

Unknown effect, target, or permission means defer or reject. Never downgrade uncertainty to a safe read merely to continue. Treat capability annotations as untrusted hints unless the server trust boundary has been established explicitly.

## Decision policy

- Known reads with acceptable data handling may run without confirmation.
- Sensitive reads may require confirmation when disclosure is not already explicit in the request.
- Writes require a clear requested outcome, bounded targets, and server authorization.
- A write may run without a second confirmation only when it is already part of a specifically confirmed workflow and the target remains unchanged.
- Destructive or difficult-to-reverse actions require explicit confirmation stating target and impact.
- Dangerous general-purpose capabilities require explicit selection by name, explicit confirmation, and strong server authorization; otherwise reject.
- Server-side authorization remains mandatory after client-side confirmation.

## Invocation

- Send only required and deliberately chosen optional parameters.
- Preserve correlation identifiers and precondition tokens.
- Use pagination deliberately and stop when the requested outcome is satisfied.
- Treat empty success as success unless the contract says otherwise.
- Do not parse prose when structured fields are available.
- Do not silently substitute a different target, account, environment, or time range.
- For multi-step workflows, stop dependent steps after a prerequisite failure.

## Confirmation

A confirmation request states:

- the capability or effect;
- exact target or target set;
- meaningful impact;
- reversibility or recovery limitations;
- any sensitive data being disclosed;
- whether retries may repeat the effect.

A vague approval does not authorize a materially expanded target or changed operation.

## Errors and retries

Classify failures before retrying.

- Validation, authentication, authorization, unsupported-operation, and not-found errors are not retried without changed input or state.
- Rate-limit, timeout, unavailable-dependency, and selected upstream errors may be retried only when the manifest or response explicitly opts in and the operation is safe.
- Retry count and delay are bounded.
- Mutations require explicit idempotency or a verified precondition before retry.
- Conflict errors trigger a re-read and a new decision before retry.
- Unknown errors are escalated rather than repeatedly invoked.

## Partial execution

When a workflow partially succeeds:

1. stop dependent unsafe steps;
2. record completed mutations and their verification state;
3. distinguish failed, skipped, and not-attempted steps;
4. attempt compensation only when explicitly defined and authorized;
5. report the remaining state and safe next action.

## Data handling

Request, display, and persist the minimum sensitive data needed. Do not forward data between servers unless the user goal and both policy boundaries require it. Redact secrets and avoid placing sensitive values in logs or confirmation messages.

## Verification

- Verify mutations through a read or dedicated verification capability.
- Compare the observed state with the requested outcome, not merely a success flag.
- Preserve server correlation information for audit and diagnosis.
- State when verification was impossible, stale, partial, or based only on a mock.
- A completed workflow reports effects, retries, partial failures, and remaining uncertainty.

## Efficiency

Efficiency never overrides safety or correctness.

- Prefer bounded batch operations over repeated calls when target control is equivalent.
- Start with minimal detail and expand only when needed.
- Stop pagination and exploration when the outcome is satisfied.
- Reuse stable results within their declared freshness window.
- Avoid loading unrelated schemas or large resources into context.

## Acceptance

A compliant consumer selects by contract, defers unknown risk, confirms material effects, sends minimal inputs, retries only safe transient failures with explicit permission, verifies mutations, respects data boundaries, and reports partial execution honestly.

---
description: Provider-neutral handling for external validation gates that did not execute, cannot be observed, or need an explicitly authorized substitute and later provider catch-up.
doc_id: reference.external-gate-availability
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Run the external-gate deviation regressions and repository rule-map/adoption gates.
---

# External gate availability

Use this contract when a required validation plane exists outside the current process and availability can differ from the product result.

## State model

Keep execution/observation separate from the product verdict. `EXECUTED` means the policy-defined repository steps actually ran and produced a real `PASS` or `FAIL`. `NOT_EXECUTED` means a provider record exists but repository steps did not run. `OBSERVER_UNAVAILABLE` means the observation plane cannot establish provider state. `UNKNOWN` means evidence is insufficient.

`NOT_EXECUTED`, `OBSERVER_UNAVAILABLE`, and `UNKNOWN` never imply product `PASS` or `FAIL`. Provider failure is not code failure and is not acceptance evidence.

## Incident identity and retry suppression

Repeated failures sharing one infrastructure cause use one incident fingerprint plus explicit account, organization, repository, workflow, runner-pool, or unknown scope. Candidate SHA is not part of an account/provider-wide fingerprint merely because a new candidate sees the same outage.

A reusable incident records first/last observation, optional freshness expiry, and exact reopen signals. `suppress_until_change` reuses a current blocker rather than burning runner budget. Suppression changes retry scheduling only; it never satisfies the gate.

## Authorized substitute evidence

A substitute is legal only when independently trusted policy or operator authority allows it. Candidate input, model output, or the failing provider record cannot mint substitute authority.

A substitute verdict that affects acceptance binds the exact current subject and reproduces the intended validation from clean detached or equivalent source state. Preserve immutable original-workflow, environment, isolation, command, report, and evidence identities and prove no inherited workspace state.

Substitute `PASS`/`FAIL` remains `PASS_SUBSTITUTE`/`FAIL_SUBSTITUTE`; it never rewrites an unavailable hosted gate into original-provider success or failure.

## Catch-up obligation

When policy requires provider catch-up, persist an exact-subject obligation independently from the substitute verdict. Only a verified execution of the original provider/gate with a real PASS for the declared subject, observed strictly after the original deviation, may satisfy it. An earlier/replayed or unrelated green run does not close it. `SUPERSEDED` preserves lineage but is not satisfaction.

## Adapter boundary

`contracts/external_gate_deviation.py` and `contracts/external-gate-deviation.schema.json` own the provider-neutral receipt. Provider adapters map observations into it. GitHub Actions `tools/classify_github_run_evidence.py` remains a low-level zero-runner/zero-step classifier; it does not own substitute authority, incident lifetime, or catch-up semantics.

## Historical fixtures

Regression fixtures exercise the same generic contract for OpenCode Stack Guides acceptance, Project Steward unattended validation, and Blog Steward release validation. Product names remain fixture evidence only; the contract has no product-specific branch.

## Fail-closed rules

- A valid self-digest is structural integrity, not authority; semantic invariants are re-derived.
- Unknown fields, malformed booleans, contradictory execution/verdict combinations, stale exact-subject evidence, or missing substitute authority fail closed.
- Incident reuse cannot promote unknown/non-executed evidence to success.
- Catch-up remains explicit until exact-subject evidence satisfies or policy explicitly supersedes it.

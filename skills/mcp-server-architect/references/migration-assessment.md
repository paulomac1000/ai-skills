---
description: Required machine-readable assessment contract for MCP server migrations and production-readiness adoption.
doc_id: reference.mcp-migration-assessment
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Complete the template against an immutable repository revision, map every applicable rule to implementation and executable evidence, smoke the exact artifact with an official client, and obtain an independent decision.
---

# MCP migration assessment

## Purpose

A migration is not complete merely because the new transport starts or a generated project compiles. Every adoption or migration at L2 and above produces `migration-assessment.yaml` from `templates/migration-assessment.yaml.template`. The template is an MCP extension of the generic repository contract in `contracts/adoption-assessment.yaml.template`. The assessment is committed with the implementation or retained as an immutable release artifact.

The file makes scope, applicability, evidence, behavioral change, waivers, rollback, and residual risk comparable across agents and repositories. It is not a narrative status report and must not contain unverified claims.

## Implementation and assurance are independent

Repository integration state and formal ai-skills assurance state are independent axes. Do not reinterpret one as the other.

A useful implementation lifecycle is `planned -> implemented -> merged -> released`. The assurance lifecycle is separately `discovered -> locally-verified -> provider-verified -> independent-review-pending -> adopted`, with blocked or failed evidence represented explicitly rather than by moving the implementation backwards.

A repository MAY merge or release a technically verified implementation before formal provider-backed adoption when its own repository policy permits that action. Such a merge or release MUST NOT be represented as `adopted`. Conversely, a pending provider control or independent review MUST NOT be converted into a durable instruction such as "keep PR N draft" unless that instruction belongs to the transient pull-request process itself.

The assessment records assurance. Repository and release state come from their canonical repository or provider sources. Durable documentation summarizes the distinction and links here rather than mirroring temporary PR state.

## Normative precedence

When repository resources disagree, apply this order:

1. `STANDARD.md` and active normative decisions;
2. the applicable implementation profile;
3. `SKILL.md` workflow instructions;
4. generators and templates;
5. examples;
6. migration simulations.

A lower-ranked resource cannot weaken a higher-ranked requirement. Examples demonstrate a pattern but do not establish policy. A generator is a reviewed baseline, not an exception mechanism. When a conflict cannot be resolved from the higher-ranked owner, stop the migration, record the conflict as a residual risk, and request a standard decision before implementation continues.

## Applicability matrix

Record every stable rule identifier assigned to `mcp-server-architect` in `contracts/rule-catalog.yaml`; completeness is mandatory, including rules judged not applicable or deferred. Each entry has exactly one status:

- `applicable`: implementation and executable verification are required;
- `not-applicable`: provide a concrete architectural reason, not merely “unused”;
- `deferred`: requires a waiver with owner, compensating controls, and expiry.

Do not mark a rule not applicable because the current implementation lacks the feature that would satisfy it. If production scope needs the behavior, the rule remains applicable.

## Evidence contract

Evidence names an immutable revision, relative code path, symbol or configuration owner, executable command, and observed result. `structural-attestation` validates those local declarations but cannot approve a migration. `provider-backed` additionally verifies the GitHub Actions run, job, artifact, digest, and pull-request review against the same SHA. Screenshots, prose, generated comments, free-form evidence URIs, or a green aggregate check are supplementary only. The assessment must identify the exact wheel, package, DLL, image digest, or equivalent deployment artifact tested through an official MCP client.

For each advertised transport, capture listing, representative read, representative failure, and every applicable write or approval boundary. Preserve target identity, principal, manifest, error, artifact, and task evidence where relevant.

Evidence is revision-scoped. Review, CI, provider control, or artifact evidence for revision A does not review or approve revision B. Any implementation-changing push invalidates stale exact-revision claims and requires the affected evidence to be re-established.

## Behavioral accounting

List behavior that remains compatible, behavior deliberately changed, and legacy behavior removed. Explicitly cover transport endpoints, capability names, schemas, identifiers, error categories, authentication, target selection, retry behavior, artifacts, background tasks, and operator controls. An undocumented behavioral difference is a migration defect.

## Waivers

A waiver is exceptional and temporary. It names one rule, one accountable owner, concrete compensating controls, an expiry date, and the condition for removal. A waiver cannot permit model-controlled authorization, fail-open risk classification, target substitution, unbounded privileged execution, or a new deprecated HTTP+SSE implementation.

## Rollback and residual risk

Define observable rollback triggers, executable rollback steps, and data or artifact recovery before enabling production traffic. Residual risks remain specific, owned, and visible in the final decision. “Monitor after release” is not a rollback plan.

## Machine validation

Before review, run `python contracts/validate_adoption.py migration-assessment.yaml` in structural-attestation mode. Before claiming acceptance, set `verification_mode: provider-backed` and run the same command with `--require-approval` and a read-only `GITHUB_TOKEN`. The validator rejects missing or unknown catalog rules, inconsistent revisions, placeholder evidence, failed commands, expired waivers, unsupported compatibility claims, incomplete MCP transport evidence, blocking residual risks, self-approval, provider records that do not exist, evidence from another revision, artifact digest mismatch, or a review not bound to the assessed commit. A green aggregate CI status cannot replace the completed assessment.

## Acceptance

A reviewer identified by canonical provider, login, and numeric ID may set `decision.status: approve` only when the provider-backed review record is `APPROVED` for the exact assessed commit and:

- the assessed revision is immutable and matches the reviewed implementation;
- all applicable rules have implementation and executable evidence;
- every deferred rule has a valid waiver;
- the exact deployment artifact passes official-client smoke on every advertised transport;
- preserved and intentionally changed behavior are accounted for;
- rollback is executable;
- no unresolved conflict exists between normative resources and implementation.

Zero unresolved bot threads is thread hygiene, not acceptance evidence. For security-sensitive parsers, trust validators, provenance analyzers, and authorization logic, perform a focused adversarial/manual pass after the final implementation-changing revision and bind that review to the exact assessed SHA.

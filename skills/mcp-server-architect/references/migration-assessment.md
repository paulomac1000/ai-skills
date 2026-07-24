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

Evidence names an immutable revision, relative code path, symbol or configuration owner, executable command, and observed result. Screenshots, prose, generated comments, or a green aggregate check are supplementary only. The assessment must identify the exact wheel, package, DLL, image digest, or equivalent deployment artifact tested through an official MCP client.

For each advertised transport, capture listing, representative read, representative failure, and every applicable write or approval boundary. Preserve target identity, principal, manifest, error, artifact, and task evidence where relevant.

## Behavioral accounting

List behavior that remains compatible, behavior deliberately changed, and legacy behavior removed. Explicitly cover transport endpoints, capability names, schemas, identifiers, error categories, authentication, target selection, retry behavior, artifacts, background tasks, and operator controls. An undocumented behavioral difference is a migration defect.

## Waivers

A waiver is exceptional and temporary. It names one rule, one accountable owner, concrete compensating controls, an expiry date, and the condition for removal. A waiver cannot permit model-controlled authorization, fail-open risk classification, target substitution, unbounded privileged execution, or a new deprecated HTTP+SSE implementation.

## Rollback and residual risk

Define observable rollback triggers, executable rollback steps, and data or artifact recovery before enabling production traffic. Residual risks remain specific, owned, and visible in the final decision. “Monitor after release” is not a rollback plan.

## Machine validation

Before review, run `python contracts/validate_adoption.py migration-assessment.yaml`. Before claiming acceptance, run the same command with `--require-approval`. The validator rejects missing or unknown catalog rules, inconsistent revisions, placeholder evidence, failed commands, expired waivers, unsupported compatibility claims, incomplete MCP transport evidence, blocking residual risks, and self-approval. A green aggregate CI status cannot replace the completed assessment.

## Acceptance

An independent reviewer may set `decision.status: approve` only when:

- the assessed revision is immutable and matches the reviewed implementation;
- all applicable rules have implementation and executable evidence;
- every deferred rule has a valid waiver;
- the exact deployment artifact passes official-client smoke on every advertised transport;
- preserved and intentionally changed behavior are accounted for;
- rollback is executable;
- no unresolved conflict exists between normative resources and implementation.

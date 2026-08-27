---
afds_schema_version: 2
description: Operational trust-bootstrap recipe, provider-control preflight, migration states, and administration boundary for provider-backed CI/CD adoption.
doc_id: reference.ci-cd-provider-trust-bootstrap
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification:
  kind: command
  value: Run the authority-owned consumer-acceptance dispatcher from a protected ref, validate authority binding and provider-control preflight with focused contract tests, then run the repository quality gate.
---

# Provider trust bootstrap and adoption states

Read this reference before calling a CI/CD migration provider-backed or adopted.

## Two independent trust dimensions

Provider-backed approval requires both:

1. **Trusted executable provenance**: which immutable verifier and collector bytes execute.
2. **Trusted orchestration authority**: who selects the candidate repository/SHA, verifier identity, provider credentials, required checks, and acceptance timing.

A candidate-owned workflow that checks out `ai-skills@<full-sha>` proves executable provenance only. Candidate control of orchestration keeps the result structural or diagnostic.

## Canonical GitHub authority flow

For GitHub.com, provider-backed acceptance is authority-owned end to end:

1. dispatch `.github/workflows/consumer-acceptance-dispatch.yml` in the authority repository from a provider-protected ref;
2. the dispatcher calls local `.github/workflows/consumer-acceptance.yml`, so GitHub loads it from the same authority commit;
3. the called job compares caller `github.repository`/`github.sha` with `job.workflow_repository`/`job.workflow_sha` and requires `github.ref_protected`; a direct cross-repository candidate caller therefore fails closed;
4. an authority-owned read token checks out the exact candidate repository/SHA, while the workflow checks out its exact authority SHA;
5. `validate_external_trust_lock.py` proves the candidate lock names that same external authority and the required trusted entrypoints;
6. provider-control preflight verifies real branch, environment, and authority-selected required-check state;
7. exact-SHA provider evidence and independent review are correlated with the candidate before the assessment may become `adopted`.

GitHub's `github` context belongs to the caller workflow, while `job.workflow_*` identifies the workflow file defining the reusable job on GitHub.com. This distinction is the authority-binding mechanism. The current provider-backed implementation is GitHub.com-specific; do not claim the same job-context contract for GitHub Enterprise Server.

The candidate trust lock is a declaration to compare with the authority. It never chooses or bootstraps that authority by itself.

## Trusted executable inventory scope

| Execution surface | Trust inventory required? | Reason |
| --- | --- | --- |
| local developer check without provider credentials | no, unless promoted as acceptance evidence | diagnostics do not establish provider approval |
| candidate-owned structural CI | only for immutable external executables whose provenance is asserted | candidate still owns orchestration |
| authority-owned acceptance | yes for credential/evidence-boundary entrypoints declared by the candidate | the external authority SHA binds the checkout |
| provider evidence collector using read credentials | yes | it influences provider-backed evidence |
| privileged publisher | separate release trust controls apply | assessment trust is not publication authority |

Do not inventory every transitive helper mechanically. Keep trusted entrypoints and their implementation in the same immutable authority revision. Generate lock digests from that verified checkout with `tools/generate_trusted_executable_sources.py`, never from mutable branch bytes.

## Provider controls are not repository YAML

`environment: release` proves only that a workflow names an environment. Repository files likewise cannot prove branch protection, rulesets, reviewers, or deployment restrictions.

Run `tools/check_github_provider_controls.py` from the trusted authority checkout. Its states are deliberately different:

- `MISCONFIGURED`: the provider control was observable and insufficient;
- `UNVERIFIABLE`: credentials, visibility, plan support, or provider response prevented a reliable decision.

Both block `adopted`. Do not convert permission failure into either a pass or proof that a control is absent. The preflight checks default-branch protection and literal protected-release environments. An optional `required_check` must come from authority policy or the authority operator, not candidate-controlled workflow input.

## Provider administration boundary

Repository changes and provider administration are separate workstreams. When the agent cannot administer provider controls, it must implement safe repository changes, keep provider checks fail closed, report `provider-preflight-blocked`, emit an external-admin checklist, and re-run preflight after the provider configuration changes.

The authority dispatcher expects `AI_SKILLS_CONSUMER_READ_TOKEN`. Scope it only to approved candidate repositories and read operations needed for candidate contents, Actions evidence, pull-request/review evidence, environments, and branch-protection inspection. A `403` or ambiguous protection `404` remains `UNVERIFIABLE` unless an independent observable listing proves absence.

## Migration state model

Use one state:

- `structurally-conformant`: repository and structural checks are aligned, provider-backed acceptance incomplete;
- `provider-preflight-blocked`: provider controls are misconfigured or unverifiable;
- `provider-validation-pending`: provider controls pass, exact-SHA hosted evidence is incomplete;
- `independent-review-pending`: provider evidence passes, independent review is missing or invalid;
- `adopted`: external authority binding, provider preflight, exact-SHA evidence, and independent review all pass.

A new candidate SHA invalidates candidate-bound evidence and review. A new authority SHA requires a new authority-bound acceptance run.

## No-runner evidence classification

Use `tools/classify_github_run_evidence.py` when GitHub run records are ambiguous. `provider-no-runner` means a failed run/job record was created without runner assignment or executed steps. It is infrastructure evidence only, never a code failure or pass.

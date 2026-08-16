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
  value: Run the materialized consumer-acceptance reusable workflow from an immutable SHA, validate its authority binding and provider-control preflight with focused contract tests, then run the repository quality gate.
---

# Provider trust bootstrap and adoption states

Read this reference before calling a CI/CD migration provider-backed or adopted.

## Two independent trust dimensions

Provider-backed approval requires both dimensions below. Possessing only one is structural evidence, not approval authority.

1. **Trusted executable provenance** proves which immutable verifier and evidence-collector bytes are executed.
2. **Trusted orchestration authority** proves who selected the candidate SHA, verifier repository/SHA, claim catalog, provider credentials, acceptance workflow, and decision timing.

A candidate-owned workflow that checks out `ai-skills@<full-sha>` satisfies executable provenance only. The candidate still controls orchestration and therefore cannot approve itself. Label that result `structural` or `diagnostic`.

The canonical GitHub.com flow is:

1. a caller pins `.github/workflows/consumer-acceptance.yml` from the authority repository by full commit SHA;
2. the called workflow obtains its own immutable identity from GitHub's reusable-workflow job context, rejects a branch/tag-based caller reference, and checks out that exact authority repository/SHA;
3. it checks out the candidate by an explicit full SHA;
4. it verifies that the candidate trust lock declares exactly the externally supplied authority coordinates and required trusted entrypoints;
5. it runs provider-control preflight against the real GitHub repository, not only repository YAML;
6. it validates provider evidence and independent review against the exact candidate SHA;
7. only then may the assessment reach `adopted`.

The authority workflow revision is established by the caller's immutable `uses: owner/repo/.github/workflows/consumer-acceptance.yml@<full-sha>` reference, not by a field chosen inside the candidate repository. The candidate trust lock is a declaration to compare with that anchor; it is never the root of trust by itself.

## Trusted executable inventory scope

Use this decision matrix when deciding what belongs in `trusted-executable-sources.lock.yaml`.

| Execution surface | Trust inventory required? | Reason |
| --- | --- | --- |
| local developer check with no provider credentials | no, unless promoted as acceptance evidence | local diagnostics do not establish provider-backed approval |
| candidate-owned structural CI | only for immutable external executables whose provenance is being asserted | the candidate still owns orchestration, so the result remains diagnostic |
| externally pinned acceptance workflow | yes for provider evidence collectors and verifier entrypoints whose identity the candidate declares | authority SHA is external; the lock proves the candidate expected the same executable source |
| provider evidence collector using read credentials | yes | it can influence provider-backed acceptance evidence |
| privileged publisher | separate protected-release trust and artifact-promotion controls apply | publication authority must not be inferred from an assessment lock |

Do not mechanically inventory every helper imported by an immutable authority checkout. The external authority SHA binds the complete checkout. Inventory the executable entrypoints that cross the evidence or credential boundary, and keep their transitive implementation inside the same immutable authority revision.

Generate digest entries from the authority checkout with `tools/generate_trusted_executable_sources.py`; do not calculate or copy hashes from mutable branch bytes.

## Provider controls are not repository YAML

`environment: release` in workflow YAML proves only that the workflow names an environment. It does not prove that the provider environment exists or has protection rules. Likewise, a checked-in branch-policy description does not prove the default branch is protected.

Run `tools/check_github_provider_controls.py` from the trusted authority checkout. The preflight distinguishes:

- `MISCONFIGURED`: the provider was observable and the required control is absent or weaker than declared;
- `UNVERIFIABLE`: the control could not be observed because credentials, repository visibility, plan support, or provider response were insufficient.

Both block `adopted`. `UNVERIFIABLE` is not evidence that the control is absent and is not evidence that it exists.

The preflight checks default-branch provider protection and every literal environment referenced by a workflow governed as `protected-release`. When an authority invocation supplies `--required-check`, it also checks that status-check identity. Security-sensitive required-check inputs must come from the authority configuration, never from candidate-controlled workflow inputs.

## Provider administration boundary

Repository changes and provider-administration changes are separate workstreams. A file in the repository cannot create or simulate GitHub branch protection, a ruleset, environment reviewers, or a deployment branch policy.

When the agent cannot administer provider controls, it must:

1. implement all safe repository-side changes;
2. add fail-closed preflight where a real provider control is required;
3. report `provider-preflight-blocked` rather than `adopted`;
4. emit an external-admin checklist naming the exact repository, branch, environment, required check, and expected protection state;
5. rerun provider preflight after the administrator changes the provider configuration.

For GitHub fine-grained tokens, the read surfaces are intentionally separate: repository branch metadata uses `Contents: read`; branch-protection detail uses `Administration: read`; environments and workflow-run/job evidence use `Actions: read`. A `403` or ambiguous `404` from a protection endpoint is `UNVERIFIABLE` unless a preceding observable list proves the resource is absent. Do not reinterpret permission failure as a policy result.

## Migration state model

Use exactly one state in migration reporting:

- `structurally-conformant`: repository content, local validators, and structural CI are aligned, but provider-backed acceptance has not completed;
- `provider-preflight-blocked`: provider controls are misconfigured or unverifiable;
- `provider-validation-pending`: provider controls are observable and acceptable, but exact-SHA hosted evidence is incomplete, queued, or unavailable;
- `independent-review-pending`: provider evidence passed on the exact SHA, but the independent reviewer decision is missing or invalid;
- `adopted`: provider preflight, exact-SHA evidence, external authority binding, and independent review all pass.

A new commit invalidates provider-validation and review evidence tied to an earlier candidate SHA.

## No-runner evidence classification

Use `tools/classify_github_run_evidence.py` with the provider run JSON and jobs JSON when diagnosing ambiguous Actions failures. Supported classes are `executed-pass`, `executed-fail`, `provider-no-runner`, `cancelled`, `queued`, and `missing-evidence`.

`provider-no-runner` means the provider created a failed run/job record but assigned no runner and executed no steps. It is infrastructure evidence only. It must never become a code failure or a pass.

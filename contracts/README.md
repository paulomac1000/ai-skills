---
description: Repository-wide adoption, compatibility, versioning, and evidence contracts for every published skill.
doc_id: reference.repository-adoption-contracts
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Run JSON Schema validation, semantic adoption validation, rule-map coverage tests, exact-target compatibility lanes, and provider-backed evidence checks for an approving assessment.
---

# Repository adoption contracts

## Purpose

The files in this directory make adoption evidence comparable across every skill. They are repository-level contracts and therefore must not be copied into one skill as a private variant. The routing/behavior eval schema is owned by `skills/skill-architect/schemas/skill-eval.schema.json` so the bundled validator remains self-contained when the skill package is distributed.

- `rule-catalog.yaml` assigns stable identifiers to the complete adoption rule set for each skill.
- `standard-rule-map.yaml` maps every normative `STANDARD.md` H2 heading to a stable rule or an explicit, reviewed exclusion.
- `change-acceptance.schema.json` defines immutable software-change obligations and falsifiable acceptance criteria without mutable satisfaction state.
- `semantic-review-plan.schema.json` binds candidate/base-specific semantic-review flows, focus areas, and invariant matrices to stable criteria.
- `artifact-evidence.schema.json` and `artifact_evidence.py` define collision-safe, bounded exact artifact construction while preserving requested and observed identity separately.
- `release-deliverable-manifest.schema.json`, `artifact-closure-receipt.schema.json`, and `artifact_closure.py` define policy-owned required release deliverables and exact-artifact presence/identity/smoke closure before publication or deployment. Executed smoke results carry the concrete smoke profile ref plus immutable SHA-256 identity, and required smoke must match both manifest-owned values. Nested claims implicitly bind the single root artifact digest, carry immutable evidence digests, and are committed by the root artifact-evidence digest. Unexpected-component disposition is manifest/policy-owned; component observations are keyed by component ref so duplicate claims are structurally impossible, and components without an explicit disposition remain unresolved and blocking. Schema text identities/refs require at least one non-whitespace character, matching Python admission. Derived identity/smoke failures are keyed by deliverable ID, preventing conflicting duplicate claims in schema-only consumers. Receipt self-digests provide structural integrity only; admission/currentness re-derives policy blockers and requires trusted current artifact ref/digest plus evidence identity before a receipt can be `CURRENT`.
- `diagnostic-egress.schema.json` and `diagnostic_egress.py` define bounded protected-sink diagnostics built from trusted typed classification and allowlisted fields, with fail-closed fallback instead of copied source/provider text.
- `adoption-assessment.schema.json` is the canonical structural contract for assessment documents.
- `adoption-assessment.yaml.template` is the generic assessment used by AFDS, AGENTS.md, CI/CD, MCP server, and MCP consumer adoptions.
- `validate_adoption.py` runs schema validation first, then validates semantics, immutable revisions, symlink-free local implementation paths and artifact trees, waivers, exact compatibility tuples, extensions, rollback, risks, and approval independence.
- `write_evidence_report.py` writes the canonical machine-readable claim report uploaded by an evidence-producing job.
- `evidence.py` binds an assessment claim to the exact GitHub Actions workflow, event, job, lane, artifact, report bytes, revision, and pull-request review.
- `compatibility-matrix.yaml` maps each declared operating-system, architecture, runtime, version, and evidence-lane tuple to executable CI.
- `semver.py` is the single strict SemVer 2.0.0 implementation used by repository validators.

## Verification modes

`structural-attestation` validates the document shape, rule completeness, local code references, local artifact digest, compatibility declarations, and semantic consistency. It is an auditable declaration, not proof that a remote CI run or review exists. This mode cannot produce an accepted decision.

`provider-backed` additionally requires a canonical report artifact. The verifier checks the workflow path and name, event, exact job name, evidence lane, run and job IDs, immutable revision, artifact ID and name, provider digest, report path and digest, and the exact rule, compatibility, transport, or artifact claim encoded in that report. An unrelated green job on the same revision is not valid evidence.

The artifact download follows GitHub's signed redirect without forwarding the GitHub API token. Every HTTP response is closed deterministically. ZIP paths, duplicate entries, symlinks, entry counts, and declared sizes are validated before reading, and the report is decompressed incrementally under a limit based on the bytes actually consumed.

The validator never treats a free-form URI, screenshot, aggregate badge, or self-declared `passed` value as verified remote evidence.

## Consumer runtime evidence

A skill manifest may opt into provider-backed adoption evidence from consumer runtimes through `adoption.consumer_runtime_evidence.provider_backed_runtimes`. This is intentionally separate from `compatibility.tested_combinations`: the latter describes combinations executed by this `ai-skills` repository, while the former allows an adopting repository to prove its own runtime-specific compatibility tuple through the external provider-backed evidence chain.

An opted-in consumer tuple is admissible only when the assessment uses a provider verifier, the runtime is explicitly listed by the skill, and its operating-system and architecture pair is already supported by the skill. The provider report must still bind the exact runtime/version/lane combination, command, result bytes, immutable revision, and passed testcase identity. Structural attestation alone cannot manufacture support for an unlisted tuple.

Python pytest node IDs retain their canonical JUnit translation. Other runtimes, including Node/TypeScript test stacks such as Vitest, use the exact JUnit `classname::name` identity emitted by the evidence-producing execution. This keeps the assessment schema runtime-neutral without guessing framework-specific test naming conventions.

## Acceptance root of trust

Candidate-produced reports and `contracts/validate_adoption.py` are diagnostic. The assessed revision MUST NOT supply the authoritative verifier, claim catalog, or acceptance workflow used to approve itself. Final acceptance MUST run through a protected reusable workflow or separately published verifier pinned by full commit SHA, with a claim catalog pinned independently from the assessed repository. The external verifier executes exact argv, records the working directory and exit status, binds every selected testcase to one result path and digest, and emits the final provider-backed decision.

A candidate-local verifier MUST fail closed for an approval decision when no matching external `acceptance_authority` is supplied. It may still validate structure and produce diagnostic evidence for development and red-team review.

## Evidence report production

Every evidence-producing job checks out the assessed source HEAD explicitly and writes the canonical current evidence report. The writer resolves the canonical run, workflow, job, check-run, and producer identities from the GitHub Actions API. It rejects a tested checkout that differs from the assessed source SHA.

Claims are not accepted from a free-form `passed` JSON value. Each claim must name an execution record, select one or more test cases, and bind to the SHA-256 digest of the uploaded JUnit file that contains those passed cases. Test-case identities are verified only inside the result digests cited by that claim. The report records `source_head_sha`, `tested_checkout_sha`, provider `head_sha`, producer identity, result summaries, result digests, exact argv digests, working directories, test-case identities, and exit status. The current report format reserves `merge_sha` as `null` until a provider adapter can independently prove the synthetic merge commit.

```bash
GITHUB_TOKEN=<read-token> python contracts/write_evidence_report.py \
  --repository "$GITHUB_REPOSITORY" \
  --source-head-sha "$SOURCE_HEAD_SHA" \
  --tested-checkout-sha "$(git rev-parse HEAD)" \
  --run-id "$GITHUB_RUN_ID" \
  --workflow-path .github/workflows/ci.yml \
  --workflow-name CI \
  --event pull_request \
  --job-name "Python compatibility (ubuntu-24.04, 3.12)" \
  --lane python-compatibility \
  --dynamic-kind compatibility \
  --dynamic-subject "linux|x64|python|3.12|python-compatibility" \
  --dynamic-execution-id compatibility \
  --execution-record evidence/executions/compatibility.json \
  --output evidence/report.json
```

The job uploads the report and every referenced result file in one artifact. The provider verifier downloads those exact bytes, re-parses JUnit, checks that selected test cases passed, verifies the producer against the workflow actor, and rejects report, result, command, checkout, or provider identity drift.

## Provider scope and evidence lifetime

The current provider-backed adapter supports public GitHub.com, GitHub Actions, and GitHub pull-request reviews only. GitHub Enterprise Server, GHE.com data-residency hosts, GitLab, Jenkins, and Azure DevOps remain structural-attestation-only until a separately reviewed adapter defines trusted API origins and equivalent provenance. The generic architecture rules remain domain-neutral; the current remote evidence implementation is intentionally not advertised as provider-neutral.

Repository evidence artifacts are retained for 90 days and represent a point-in-time decision. Longer-lived releases must preserve a signed report, attestation, or release asset outside ephemeral Actions retention.

## Extension model

The base assessment is domain-neutral, but the extension namespace is a closed current registry rather than an arbitrary object bag. Currently, `mcp` is the only registered key under `extensions`; unknown keys are rejected. Registering another extension requires a versioned schema definition, semantic validator support, templates, and regression tests. The MCP server extension records maturity level, implementation profiles, advertised transports, official-client commands, and transport-specific listing, read, failure, and write-boundary results.

## Validation

A migrated repository vendors or pins these contracts and first runs structural validation:

```bash
python contracts/validate_adoption.py path/to/adoption-assessment.yaml
```

An approval gate uses provider-backed evidence and a token able to read the referenced repository, workflow, artifact, and review:

```bash
GITHUB_TOKEN=<read-token> python contracts/validate_adoption.py \
  path/to/adoption-assessment.yaml --require-approval
```

The validator fails when schema and semantic contracts disagree, catalog rules are missing or duplicated, a normative heading is unmapped, revisions disagree, implementation paths or artifact trees contain symlinks, local artifact digests differ, a waiver is missing or expired, exact compatibility tuples lack passed results, evidence names the wrong workflow, job, lane, combination, or claim, an MCP transport lacks official-client evidence, a blocking risk remains, provider records do not exist or do not match the SHA, or the approving reviewer is not independent.

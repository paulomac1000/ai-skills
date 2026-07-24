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

The files in this directory make adoption evidence comparable across every skill. They are repository-level contracts and therefore must not be copied into one skill as a private variant.

- `rule-catalog.yaml` assigns stable identifiers to the complete adoption rule set for each skill.
- `standard-rule-map.yaml` maps every normative `STANDARD.md` H2 heading to a stable rule or an explicit, reviewed exclusion.
- `adoption-assessment.schema.json` is the canonical structural contract for assessment documents.
- `adoption-assessment.yaml.template` is the generic assessment used by AFDS, CI/CD, MCP server, and MCP consumer adoptions.
- `validate_adoption.py` runs schema validation first, then validates semantics, immutable revisions, symlink-free local implementation paths and artifact trees, waivers, exact compatibility tuples, extensions, rollback, risks, and approval independence.
- `write_evidence_report.py` writes the canonical machine-readable claim report uploaded by an evidence-producing job.
- `evidence.py` binds an assessment claim to the exact GitHub Actions workflow, event, job, lane, artifact, report bytes, revision, and pull-request review.
- `compatibility-matrix.yaml` maps each declared operating-system, architecture, runtime, version, and evidence-lane tuple to executable CI.
- `semver.py` is the single strict SemVer 2.0.0 implementation used by repository validators.

## Verification modes

`structural-attestation` validates the document shape, rule completeness, local code references, local artifact digest, compatibility declarations, and semantic consistency. It is an auditable declaration, not proof that a remote CI run or review exists. This mode cannot produce an accepted decision.

`provider-backed` additionally requires a canonical report artifact. The verifier checks the workflow path and name, event, exact job name, evidence lane, run and job IDs, immutable revision, artifact ID and name, provider digest, report path and digest, and the exact rule, compatibility, transport, or artifact claim encoded in that report. An unrelated green job on the same revision is not valid evidence.

The artifact download follows GitHub's signed redirect without forwarding the GitHub API token. ZIP paths, duplicate entries, symlinks, entry counts, and compressed and uncompressed sizes are validated before the report is read.

The validator never treats a free-form URI, screenshot, aggregate badge, or self-declared `passed` value as verified remote evidence.

## Evidence report production

Each evidence job writes a JSON array of exact claims, then creates a canonical report:

```bash
python contracts/write_evidence_report.py \
  --repository "$GITHUB_REPOSITORY" \
  --revision "$GITHUB_SHA" \
  --run-id "$GITHUB_RUN_ID" \
  --check-run-id "${{ job.check_run_id }}" \
  --workflow-path .github/workflows/ci.yml \
  --workflow-name CI \
  --event pull_request \
  --job-name "Python compatibility (ubuntu-24.04, 3.12)" \
  --lane python-compatibility \
  --claims-file evidence/claims.json \
  --output evidence/report.json
```

The job uploads `evidence/report.json` with the JUnit, package, image metadata, or other immutable outputs it claims. The completed assessment records the resulting artifact and report digests.

## Extension model

The base assessment is domain-neutral. Skill-specific evidence belongs under `extensions.<extension-name>` and may only strengthen the generic acceptance rules. The MCP server extension records maturity level, implementation profiles, advertised transports, official-client commands, and transport-specific listing, read, failure, and write-boundary results.

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

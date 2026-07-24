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
- `validate_adoption.py` runs schema validation first, then validates semantics, immutable revisions, local implementation paths and symbols, local artifact digests, waivers, exact compatibility tuples, extensions, rollback, risks, and approval independence.
- `evidence.py` verifies GitHub Actions runs, jobs, artifacts, digests, and pull-request reviews against the same immutable revision when provider-backed verification is selected.
- `compatibility-matrix.yaml` maps each declared operating-system, architecture, runtime, version, and evidence-lane tuple to executable CI.
- `semver.py` is the single strict SemVer 2.0.0 implementation used by repository validators.

## Verification modes

`structural-attestation` validates the document shape, rule completeness, local code references, local artifact digest, compatibility declarations, and semantic consistency. It is an auditable declaration, not proof that a remote CI run or review exists. This mode cannot produce an accepted decision.

`provider-backed` additionally verifies the referenced GitHub Actions run, job, artifact, provider digest, and pull-request review through the canonical GitHub API. An approval gate requires this mode, a successful run and job on the assessed SHA, a non-expired artifact bound to that SHA, and an independent `APPROVED` review whose canonical GitHub identity and `commit_id` match the assessment.

The validator never treats a free-form URI, screenshot, aggregate badge, or self-declared `passed` value as verified remote evidence.

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

The validator fails when schema and semantic contracts disagree, catalog rules are missing or duplicated, a normative heading is unmapped, revisions disagree, implementation paths or symbols do not exist, local artifact digests differ, a waiver is missing or expired, exact compatibility tuples lack passed results, an MCP transport lacks official-client evidence, a blocking risk remains, provider records do not exist or do not match the SHA, or the approving reviewer is not independent.

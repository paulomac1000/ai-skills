---
description: Repository-wide adoption, compatibility, versioning, and evidence contracts for every published skill.
doc_id: reference.repository-adoption-contracts
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Run the adoption validator and repository contract tests against the committed catalog, manifests, templates, and completed assessments.
---

# Repository adoption contracts

## Purpose

The files in this directory make adoption evidence comparable across every skill. They are repository-level contracts and therefore must not be copied into one skill as a private variant.

- `rule-catalog.yaml` assigns stable identifiers to the complete adoption rule set for each skill.
- `adoption-assessment.yaml.template` is the generic assessment used by AFDS, CI/CD, MCP server, and MCP consumer adoptions.
- `validate_adoption.py` validates structure, completeness, immutable revisions, evidence, waivers, compatibility claims, extensions, rollback, and approval independence.
- `compatibility-matrix.yaml` maps every declared compatibility claim to executable CI lanes.
- `semver.py` is the single strict SemVer 2.0.0 implementation used by repository validators.

## Extension model

The base assessment is domain-neutral. Skill-specific evidence belongs under `extensions.<extension-name>` and may only strengthen the generic acceptance rules. The MCP server extension records maturity level, implementation profiles, advertised transports, official-client commands, and transport-specific listing, read, failure, and write-boundary results.

## Validation

A migrated repository vendors or pins these contracts and executes:

```bash
python contracts/validate_adoption.py path/to/adoption-assessment.yaml --require-approval
```

The validator fails when catalog rules are missing or duplicated, revisions disagree, evidence is placeholder or not passed, a waiver is missing or expired, compatibility claims lack passed results, a blocking residual risk remains, an MCP transport lacks official-client evidence, or the approving reviewer also prepared the assessment.

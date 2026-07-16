---
description: Results of the deterministic AFDS v3 retrieval and mutation benchmark
doc_id: reference.afds-benchmark-2026-07
type: reference
status: active
rigor: operational
owners: [docs-maintainers]
schema_version: 3
---

# AFDS v3 benchmark report

## Outcome

AFDS v3 was accepted after the alias/entity retrieval iteration. Two later proposals were rejected because they added context or ceremony without improving retrieval.

## Scope

This benchmark evaluates documentation retrieval shape and structural defect detection. It does not evaluate factual truth or full model reasoning.

## Dataset

- Generated documents: 2160 across 360 targets per iteration.
- Queries: 1800 across 5 deterministic agent-query personas.
- Mutation cases: 120 across 6 defect classes.

## Retrieval results

| Variant | Recall@1 | Recall@3 | MRR | nDCG@5 | Avg top-3 chars |
|---|---:|---:|---:|---:|---:|
| `prose` | 0.405 | 0.415 | 0.425 | 0.415 | 3706 |
| `afds2` | 0.405 | 0.415 | 0.425 | 0.415 | 8970 |
| `afds3_core` | 0.405 | 0.415 | 0.425 | 0.415 | 1849 |
| `afds3` | 0.967 | 1.000 | 0.983 | 0.988 | 2347 |
| `afds3_more_sections` | 0.967 | 1.000 | 0.983 | 0.988 | 5252 |
| `afds3_more_metadata` | 0.967 | 1.000 | 0.983 | 0.988 | 2701 |

## Iterations

| Iteration | Change | Accepted | MRR gain | Reason |
|---:|---|---|---:|---|
| 0 | unstructured baseline | no | 0.000 | baseline or retained design step |
| 1 | fixed comprehensive schema | no | 0.000 | baseline or retained design step |
| 2 | answer-first concise core | yes | 0.000 | baseline or retained design step |
| 3 | aliases, entities, weighted retrieval | yes | 0.558 | baseline or retained design step |
| 4 | mandatory background and related sections | no | 0.000 | no retrieval gain and larger context |
| 5 | mandatory audience, review cycle, and related-topic metadata | no | 0.000 | no material retrieval gain and more authoring ceremony |

## Validator mutation test

The validator detected 120 of 120 injected blocking defects (100.0%). The covered mutations were missing frontmatter, missing required metadata, invalid IDs, duplicate headings, broken links, and manually authored automation fields.

## Interpretation

- Answer-first structure reduced context compared with AFDS v2, but structure alone did not improve synonym retrieval in this lexical benchmark.
- Small, factual `aliases` and `entities` fields plus field-aware retrieval produced the material gain.
- Mandatory background sections more than doubled top-three context without improving ranking and were rejected.
- Extra generic metadata did not improve ranking and was rejected.

## Limits

- The benchmark isolates retrieval behavior and does not claim to reproduce a named LLM.
- The corpus is synthetic and controlled. Repository-specific task evaluations remain required.
- Perfect mutation detection applies only to the six injected structural defects, not semantic truth.

## Validation

Run `python3 benchmarks/afds/benchmark.py --check --output benchmarks/afds/latest-results.json`. The benchmark is deterministic and fails when the committed snapshot or quality thresholds drift.

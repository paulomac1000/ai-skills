---
description: Build routing, behavioral, baseline, and regression evidence for skills without confusing stochastic observations with deterministic validation.
doc_id: reference.skill-architect-evaluation
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Validate eval corpus structure locally and bind any model-backed result to the exact skill, corpus, provider/model, prompt, and observed output.
---

# Behavioral evaluation

Read this reference when creating or materially changing a skill's behavior or
routing contract.

## Two evidence layers

Deterministic validation checks package structure, schemas, paths, resources,
tool behavior, and corpus integrity. It can run on every pull request.

Model-backed evaluation observes actual selection and task behavior. It should
run for material skill changes, release acceptance when required, scheduled
compatibility checks, or supported-model upgrades. Do not make a stochastic
model judge the only gate for deterministic properties.

This repository currently standardizes the corpus and evidence contract but does
not ship a provider-specific model runner. Until such an adapter is reviewed,
model-backed runs are external evidence; never report the local corpus validator
as proof that routing or task behavior was executed.

## Routing suites

Store routing cases under evals/skills/<skill>/. Cover:

- representative positives;
- near-miss negatives where similar language belongs elsewhere;
- collisions with the nearest installed skills.

Keep the expected semantic owner explicit. When descriptions or routing rules are
optimized automatically against an eval corpus, preserve a held-out routing set
so the final measurement is not the same sample used to tune the description.

## Behavioral suites

Assertions describe properties of a good result, not exact wording. Examples
include preserving read-only scope, selecting the canonical owner before
editing, using exact revision evidence, or refusing to promote an unverified
claim.

Capability-uplift skills should compare the same representative task with and
without the skill. Workflow-policy skills primarily measure contract fidelity;
a baseline remains useful for diagnosing unnecessary context or regressions.
For qualitative outputs, a blinded comparator can reduce presentation bias, but
its judgment remains model-backed evidence rather than deterministic truth.

## Result binding

A meaningful model-backed result records the skill revision, eval corpus
revision, provider and model configuration, prompt fixture, resources exposed,
output or durable output digest, assertion results, token usage when available,
and elapsed time when useful.

Keep dimensions separate. Do not hide routing errors, correctness, latency, or
context cost inside one aggregate quality score.

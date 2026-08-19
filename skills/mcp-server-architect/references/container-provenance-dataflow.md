---
description: Conservative stage-local dataflow rules for proving container artifact source provenance.
doc_id: reference.mcp-container-provenance-dataflow
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Run the Docker source-revision adversarial corpus and require fail-closed results for overwrite, cross-stage reuse, shadowing, dynamic copy, opaque shell effects, and self-comparison cases.
---

# Container artifact source provenance

## Invariant

Artifact provenance is a conservative stage-local dataflow property, not a textual Dockerfile pattern. A comparison proves provenance only while the origins and identities of both compared values remain intact.

A proof is valid only when all of the following hold:

- the actual revision originates from the exact artifact whose provenance is being proved, not from an arbitrary copied file with a familiar basename;
- the expected revision remains an external, independently supplied input and is never overwritten, shadowed, or populated from artifact-owned bytes;
- actual and expected values are compared in the same proof context, for the same artifact and Docker stage, by a condition whose failure gates the build;
- later `COPY`, `ADD`, generated-file writes, shell assignment, `ARG` or `ENV` shadowing, `WORKDIR` changes, and stage transitions cannot replace the artifact, its source-revision evidence, or the expected value while retaining an earlier proof;
- a proof from one stage or artifact cannot be reused for another stage or artifact merely because names or paths coincide.

Reading artifact-owned `SOURCE_REVISION` bytes into the variable representing the externally expected revision creates self-comparison, not provenance verification.

## Conservative parsing

Multi-source copies, dynamic destinations, opaque shell control flow, pipes, background execution, negation, or other effects whose dataflow cannot be established conservatively invalidate the proof unless the analyzer has an explicit safe semantic model for them. Unknown shell effects fail closed; syntactic similarity to an accepted command is not evidence.

The analyzer tracks provenance and invalidation across the stage rather than remembering that a matching comparison string occurred once. A later write or shadowing event invalidates earlier proof when it can affect either side of the comparison or the artifact whose identity is being asserted.

## Adversarial corpus

Maintain one shared adversarial corpus for the dataflow property. It covers at least:

- later artifact overwrite after an earlier valid comparison;
- proof reuse across Docker stages;
- arbitrary-file substitution under a trusted revision filename;
- multi-source `COPY` or `ADD`;
- dynamic destinations and `WORKDIR` changes;
- `ARG` and `ENV` shadowing;
- shell assignments and artifact-owned reads into expected-revision variables;
- `;`, `||`, pipes, background execution, negation, and other control operators;
- opaque commands whose write effects are not modeled.

Positive cases prove only the explicitly modeled safe forms. They do not authorize adjacent unknown forms.

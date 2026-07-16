# Retrieval design

## Retrieval fields

Use `description`, `aliases`, and `entities` for terms likely to appear in questions. Keep them factual and small. Do not add keyword spam.

## Chunk boundaries

A useful chunk answers one question without hidden prerequisites. Keep the relevant heading, local definitions, and safety condition in the same chunk as the answer.

## Answer density

Prefer one precise operational statement over several paragraphs of history. Move rationale after the answer. Put large inventories in generated indexes.

## Query diversity

Evaluate at least these query styles:

- exact identifiers,
- paraphrased domain language,
- incomplete or noisy phrasing,
- incident symptoms,
- cross-document questions.

Use `benchmarks/afds/benchmark.py` before adding mandatory metadata or structural rules. Compare Recall@k, MRR, nDCG, context size, and defect detection. Reject a rule that increases ceremony without a repeatable gain.

# AFDS benchmark

The benchmark generates 360 target documents for each of six format iterations (2,160 generated documents total) across six document types and sixty domains. It runs 1,800 queries in five deterministic agent-query personas:

- exact identifiers,
- paraphrased terminology,
- terse queries,
- incident symptoms,
- weak vocabulary.

It reports Recall@1/3/5, MRR, nDCG@5, and average characters loaded for the top three results. A separate mutation suite creates 120 malformed documents across six defect classes and measures validator detection.

The benchmark is intentionally API-free so CI can reproduce it. It does not pretend that lexical perturbations are full LLM simulations. Live model evaluations should use the same target/query dataset and report model, prompt, temperature, tool access, and repeated-trial variance.

Run:

```bash
python3 benchmarks/afds/benchmark.py --output benchmarks/afds/latest-results.json
python3 benchmarks/afds/benchmark.py --check --output benchmarks/afds/latest-results.json
```

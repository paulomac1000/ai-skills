---
description: Select the AGENTS.md document language and use stable contract identifiers when lexical analysis is insufficient.
doc_id: reference.agents-md-language-contracts
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Validate one representative document with the selected language and prove that required contract markers and cross-file conflicts behave as documented.
---

# Language and contract markers

The validator performs bounded lexical analysis, not general natural-language understanding.

## Supported language modes

- `--language en` enables the English concept and directive vocabulary.
- `--language pl` enables the Polish concept and directive vocabulary.
- `--language other` disables semantic keyword assumptions. Required contracts must use stable markers; missing markers produce `language.semantic-unverified`, which blocks `--strict`.

A repository may write prose in any language. It must not claim semantic conflict detection for a language that was not selected and tested.

## Stable contract markers

Place a marker next to the section that owns the contract:

```markdown
<!-- agents-md: contract scope -->
<!-- agents-md: contract commands -->
<!-- agents-md: contract completion -->
```

Available identifiers are `scope`, `precedence`, `routing`, `commands`, `completion`, `safety`, `data`, `nested`, `risk`, and `local`.

Markers state that the section exists; they do not prove that its prose is correct. A reviewer still verifies repository intent, platform behavior, and implementation parity.

## Cross-file conflict limits

English and Polish modes normalize a bounded set of high-impact directives covering generated files, test integrity, protected data, and direct edits. Other languages do not receive lexical conflict claims. Use executable policy, canonical ownership, and manual review for broader semantics.

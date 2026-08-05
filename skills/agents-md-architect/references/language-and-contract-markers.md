---
description: Select the AGENTS.md document language and use stable contract identifiers when lexical analysis is insufficient.
doc_id: reference.agents-md-language-contracts
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Validate representative English, Polish, and other-language documents; prove that markers cannot replace EN/PL prose and that only markers bound to non-empty H2 sections satisfy other-language contracts.
---

# Language and contract markers

The validator performs bounded lexical analysis, not general natural-language understanding.

## Supported language modes

- `--language en` validates required concepts from active English prose. Contract markers do not satisfy these checks.
- `--language pl` validates required concepts from active Polish prose. Contract markers do not satisfy these checks.
- `--language other` disables semantic keyword assumptions. Required contracts must use stable markers; missing valid markers produce `language.semantic-unverified`, which blocks `--strict`.

A repository may write prose in any language. It must not claim semantic conflict detection for a language that was not selected and tested.

## Stable contract markers

Markers are an explicit fallback for `--language other`, not self-certification for English or Polish. Add only identifiers required by the selected profile and layout. Place each marker inside the H2 section that owns the contract, and give that section real, non-comment content:

```markdown
## Verification commands

<!-- agents-md: contract commands -->

- Full gate: `make quality`
```

A marker before an H2 or in an otherwise empty H2 is invalid and cannot satisfy a contract. Available identifiers are `scope`, `precedence`, `routing`, `commands`, `completion`, `safety`, `data`, `nested`, `risk`, and `local`.

Markers state that a concrete section owns the named contract; they do not prove that its prose is correct. A reviewer still verifies repository intent, platform behavior, and implementation parity.

## Cross-file conflict limits

English and Polish modes normalize a bounded set of high-impact directives covering generated files, test integrity, protected data, and direct edits. Other languages do not receive lexical conflict claims. Use executable policy, canonical ownership, and manual review for broader semantics.

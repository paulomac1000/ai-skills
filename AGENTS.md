# Agent instructions

1. Read the target skill's `SKILL.md`.
2. Load its core standard.
3. Load only references selected by the skill's routing table.
4. Search before creating a new rule or document.
5. Do not copy versions from prose. Read manifests or `docs/generated/dependency-catalog.md`.
6. Run the smallest relevant validation, then the full suite before publishing.
7. Report evidence: files changed, commands run, results, and unresolved limits.

## Change policy

- Keep `SKILL.md` under 250 lines unless a benchmark proves a longer prompt performs better.
- Keep normative and explanatory content separate.
- Do not add a universal MUST for a framework-specific workaround.
- New AFDS rules require corpus benchmark and mutation-validator evidence.
- New MCP rules require a protocol citation or evidence from at least two independent implementations.

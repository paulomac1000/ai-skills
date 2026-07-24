# AI Skills

A production-oriented collection of reusable skills, standards, implementation playbooks, executable policy helpers, and tested workflow templates for AI-assisted software engineering.

## Included skills

| Skill | Purpose | Reusable resources |
| --- | --- | --- |
| `afds-doc-writer` | Create, validate, and maintain evidence-based technical documentation. | Validator, lifecycle and impact playbooks, governed-document template |
| `ci-cd-architect` | Design secure and reproducible local and hosted quality gates. | Python, .NET, MCP, documentation, security, packaging, dependency, and container workflows |
| `mcp-server-architect` | Design secure, observable, and agent-friendly MCP servers. | Language-neutral core, Python/FastMCP and .NET profiles, testing, security, operations, examples |
| `mcp-server-consumer` | Select and invoke MCP capabilities safely and efficiently. | Deterministic decision engine and workflow, retry, pagination, and trust playbooks |

Local pre-commit and pre-push design is part of `ci-cd-architect`. It is not a separate architectural domain.

## Repository model

Every skill contains:

- `SKILL.md` — concise agent workflow and routing instructions;
- `STANDARD.md` — stable cross-project invariants and acceptance criteria;
- `manifest.yaml` — versioned compatibility, maturity, dependency, deprecation, resource-category, and required-entry-point contract.

A skill may also contain `references/`, `templates/`, `examples/`, or `tools/`. Those directories hold reusable operational knowledge, not temporary analysis artifacts. The repository deliberately has no global file-count budget and does not forbid examples or architectural decisions merely to keep the tree small.

## Contract and precedence

Consumers pin the repository revision and the skill version recorded in `manifest.yaml`. A release-candidate skill is suitable for controlled pilots and independent review; a stable skill requires completed compatibility evidence and a documented migration path for breaking changes.

When resources disagree, use this order:

1. `STANDARD.md` and active normative decisions;
2. the applicable implementation profile;
3. `SKILL.md` workflow instructions;
4. generators and templates;
5. examples;
6. migration simulations.

A lower-ranked resource cannot weaken a higher-ranked requirement. Generators are verified baselines rather than policy owners, and examples do not create exceptions. Stop and request a standard decision when a conflict remains unresolved.

## Local validation

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python scripts/ci.py
```

The command compiles Python sources, runs lint, formatting, typing, static security and dependency-vulnerability gates, validates governed Markdown and skill manifests, executes exact-artifact generator tests, enforces critical-module branch coverage, and runs the complete test suite.

## Design principles

- Keep one canonical owner for each rule, but preserve implementation detail in focused playbooks.
- Separate language-neutral invariants from SDK-specific patterns.
- Prefer executable templates and regression tests over aspirational prose.
- Treat tool metadata from remote systems as untrusted unless a trust boundary is explicit.
- Build and test the artifact that is actually published.
- Record failure patterns and the corrective rule when practical incidents reveal a reusable lesson.
- Preserve valuable history by integrating it into current guidance, not by shipping duplicate or obsolete standards.

## Recovery audit

[`RECOVERY_AUDIT.md`](RECOVERY_AUDIT.md) maps the knowledge removed by the cleanup commit to its new canonical location and records which unsafe legacy defaults were intentionally rejected.

## License

MIT. See [LICENSE](LICENSE).

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
- `manifest.yaml` — declared resource categories and required entry points.

A skill may also contain `references/`, `templates/`, `examples/`, or `tools/`. Those directories hold reusable operational knowledge, not temporary analysis artifacts. The repository deliberately has no global file-count budget and does not forbid examples or architectural decisions merely to keep the tree small.

## Local validation

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python scripts/ci.py
```

The command compiles Python sources, validates governed Markdown, validates skill manifests and workflow templates, and runs the complete test suite.

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

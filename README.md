# AI Skills

A production-oriented collection of reusable standards, agent workflows, implementation playbooks, executable policy helpers, and tested templates for AI-assisted software engineering.

The current repository release is `1.4.0`. All bundled skills are published with `maturity: stable` and are intended for production adoption. Each skill declares its compatibility, dependencies, evidence lanes, and required entry points in `manifest.yaml`.

## Included skills

| Skill | Purpose | Reusable resources |
| --- | --- | --- |
| `afds-doc-writer` | Create, validate, and maintain evidence-based technical documentation. | Validator, lifecycle and impact playbooks, governed-document template |
| `agents-md-architect` | Create, audit, split, and validate concise repository instruction systems for coding agents. | Root and nested templates, profile and routing playbooks, drift guidance, executable validator |
| `changelog-release-architect` | Curate human-facing changelogs and choose one evidence-based repository SemVer transition per release boundary. | Release-boundary standard and history-aware validator |
| `ci-cd-architect` | Design secure and reproducible local and hosted quality gates. | Python, .NET, MCP, documentation, security, packaging, dependency, and container workflows |
| `mcp-server-architect` | Design secure, observable, and agent-friendly MCP servers. | Language-neutral core, Python/FastMCP and .NET profiles, testing, security, operations, examples |
| `mcp-server-consumer` | Select and invoke MCP capabilities safely and efficiently. | Deterministic decision engine and workflow, retry, pagination, and trust playbooks |
| `readme-architect` | Create and audit evidence-backed, user-facing repository READMEs without duplicating volatile project truth. | Evidence source map, structure profiles, visual guidance, templates, collector, and auditor |

Local pre-commit and pre-push design belongs to `ci-cd-architect`; it is not a separate architectural domain.

## Start here

For a human reader:

1. Select the relevant skill from the table above.
2. Read its `manifest.yaml` to confirm maturity, compatibility, dependencies, and required entry points.
3. Read `SKILL.md` for the operating workflow.
4. Treat `STANDARD.md` as the normative source of acceptance criteria.
5. Use references, templates, examples, and generators only within those constraints.

For an implementation or migration agent, read [`AGENTS.md`](AGENTS.md) before changing the repository.

## Repository model

Every skill contains:

- `SKILL.md` — concise routing and operating instructions;
- `STANDARD.md` — stable cross-project invariants and acceptance criteria;
- `manifest.yaml` — version, maturity, compatibility, dependency, deprecation, resource-category, and required-entry-point contract.

A skill may also contain `references/`, `templates/`, `examples/`, `tools/`, or reviewed dependency `locks/`. These directories contain reusable operational knowledge, not temporary analysis artifacts.

## Authority and precedence

Consumers pin both the repository revision and the skill version recorded in `manifest.yaml`. When resources disagree, use this order:

1. `STANDARD.md` and active normative decisions;
2. the applicable implementation profile;
3. `SKILL.md` workflow instructions;
4. generators and templates;
5. examples;
6. migration simulations.

A lower-ranked resource cannot weaken a higher-ranked requirement. Generators are verified baselines rather than policy owners, and examples do not create exceptions. Stop and request a standard decision when a conflict remains unresolved.

## Local validation

POSIX:

```bash
python3 -m venv .venv
.venv/bin/python scripts/install_locked.py
.venv/bin/python scripts/ci.py
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe scripts\install_locked.py
.venv\Scripts\python.exe scripts/ci.py
```

The installer selects the committed platform lock, installs the complete transitive graph with hashes, and runs `pip check`. The validation command compiles sources, runs linting, formatting, typing, security and dependency checks, validates documentation and contracts, executes generator and exact-artifact tests, enforces critical-module branch coverage, and runs the complete non-container suite.

## Adoption and evidence

Repository-wide adoption contracts live in [`contracts/`](contracts/README.md). A completed assessment is accepted only when:

- every catalog rule appears exactly once;
- immutable repository and artifact revisions agree;
- every declared OS, architecture, runtime, version, and lane result passed;
- approving assessments use provider-backed run, job, artifact, digest, and review evidence on the same SHA;
- deferred rules have live, owned waivers;
- rollback and residual risks are explicit;
- a canonical independent reviewer approves the immutable revision.

Run `python contracts/validate_adoption.py <assessment.yaml> --require-approval` in each adopting repository. Local evidence generation and validation are diagnostic; final adoption approval depends on the external provider-backed authority declared by the adoption contract.

## Design principles

- Keep one canonical owner for each rule.
- Separate language-neutral invariants from SDK-specific patterns.
- Prefer executable templates and regression tests over aspirational prose.
- Treat remote tool metadata as untrusted unless a trust boundary is explicit.
- Build and test the artifact that is actually published.
- Record reusable lessons from real failures as a canonical invariant plus an executable validator, regression, or immutable consumer canary.
- Preserve valuable history by integrating it into current guidance, not by shipping duplicate or numbered variants.

## Recovery and change history

[`RECOVERY_AUDIT.md`](RECOVERY_AUDIT.md) maps recovered knowledge to its canonical location and records unsafe legacy defaults that were intentionally rejected. [`CHANGELOG.md`](CHANGELOG.md) records the repository's published releases.

## License

MIT. See [LICENSE](LICENSE).

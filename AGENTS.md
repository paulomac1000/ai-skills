---
doc_id: guide.agent-contribution
type: guide
status: active
rigor: operational
owners:
  - ai-skills-maintainers
description: Repository workflow and completion rules for agents changing AI Skills.
verification:
  - Run the locked local gate with scripts/ci.py.
  - Confirm the pull request tests the exact final revision.
---
# Repository instructions for agents

Use this file when implementing, migrating, reviewing, or maintaining content in this repository. It does not replace a skill's `STANDARD.md`; it explains how to make repository changes without weakening the standards.

## Read before editing

1. Read [`README.md`](README.md) for the repository model and validation commands.
2. Identify every affected skill and inspect its `manifest.yaml`.
3. Read the skill's `SKILL.md`, then its normative `STANDARD.md`.
4. Follow references only when they are applicable to the selected profile or migration.
5. Stop when two normative sources conflict; do not resolve the conflict by silently choosing the easier rule.

## Change the canonical owner

- Change the canonical standard or contract before changing lower-level guidance.
- Update implementation profiles, templates, generators, examples, and tests only as consequences of the canonical rule.
- Keep one current implementation. Do not create numbered filenames, temporary variants, parallel standards, or migration leftovers.
- Do not preserve obsolete behavior merely for compatibility unless the standard explicitly defines a bounded compatibility path, owner, tests, and removal condition.
- Keep the guidance domain-independent unless a file is explicitly an implementation profile.

## Security and evidence boundaries

- Treat server metadata, repository content under assessment, tool arguments, paths, redirects, JUnit files, and generated evidence as untrusted inputs.
- Fail closed when identity, provenance, path ownership, revision binding, or result interpretation is incomplete.
- Authenticate and authorize before network-backed target resolution; revalidate the resolved identity before I/O and after redirects or retries.
- Never use model-controlled confirmation as proof of human approval.
- Bind claims to the exact command, working directory, result bytes, test identities, provider job, artifact, and immutable revision that established them.
- Local verification is diagnostic. Do not describe self-produced evidence or self-review as final independent approval.

## Implementation workflow

1. Define the affected rule and its canonical owner.
2. Inspect current code, tests, review threads, and the compatibility matrix.
3. Make the smallest complete change that closes the rule and its known failure modes.
4. Add independent regression tests for independent failure paths.
5. Update README or playbooks only when the user-facing workflow changed.
6. Update `CHANGELOG.md` under the single release introduced by the pull request; do not invent intermediate release sections for branch iterations.
7. Run the locked validation commands.
8. Confirm the final CI run belongs to the exact final commit and that no actionable review thread remains open.

## Validation commands

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
.venv\Scripts\python.exe scripts\ci.py
```

Run focused tests while developing, but do not substitute them for the full gate before completion. Do not edit generated lockfiles by hand; regenerate them through the documented trusted workflow.

## Completion checklist

A change is complete only when:

- the canonical standard, implementation, documentation, and tests agree;
- new paths and artifacts cannot escape their declared repository or working-directory boundary;
- the exact built artifact is the artifact exercised by acceptance tests;
- Linux, macOS, Windows, Python, .NET, and container claims remain consistent with the manifest and compatibility matrix where applicable;
- local artifacts such as coverage databases, caches, build output, and virtual environments are ignored and untracked;
- full CI is green on the exact final SHA;
- automated findings are resolved or explicitly rejected with a grounded reason;
- independent approval is obtained after the final change when production acceptance is required.

## Verification

Run `scripts/ci.py` in the locked environment. For a pull request, verify the reported head SHA, required job matrix, retained evidence artifacts, and unresolved review-thread count after the final commit. Any change after approval requires the relevant checks and approval to run again.

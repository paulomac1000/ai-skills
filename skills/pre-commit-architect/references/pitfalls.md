---
doc_id: ref.pitfalls
type: ref
status: active
rigor_tier: L2
stability: stable
ai_scope: editable
source_of_truth: true
upstream: [ref.precommit-standard]
last_verified: 2026-06-07
owners: ["precommit-maintainer"]
ttl_days: 90
description: Documented pre-commit deployment pitfalls and their fixes
---

# Pre-commit Deployment Pitfalls

> **Standard Version:** 1.0.0
> **Reference:** `ref.precommit-standard` Rules PRECOMMIT-03 through PRECOMMIT-13

Compiled from real deployment failures across `ha-mcp-readonly`, `local-home-devices-mcp`, and related projects. Each pitfall includes the root cause, the PRECOMMIT rule that prevents it, and the concrete fix.

---

### Pitfall 1: `ruff target-version` Broke `except (X, Y):` Syntax

- **Opis:** `ruff format` with `target-version = "py314"` rewrote `except (ValueError, TypeError):` to `except ValueError | TypeError:` (PEP 742 syntax). This syntax is valid only on Python 3.14+, but the project targeted Python 3.13. The change broke CI on Python 3.13 runtimes.
- **Root cause:** `target-version` was set to the CI runner version (Python 3.14) instead of `requires-python` minimum (3.13). Ruff format optimizes for the target version and enables syntax variants valid only on that version.
- **Rule:** PRECOMMIT-03 — `ruff target-version` MUST match `requires-python` minimum, NOT CI runner version.
- **Solution:** Set `target-version = "py313"` in `pyproject.toml` under `[tool.ruff.format]`. This instructs ruff to emit only Python 3.13-compatible syntax.

---

### Pitfall 2: `python` vs `python3` in Hook Entry

- **Opis:** A hook entry used `python` as the interpreter, but Debian-based systems only provide `python3` (no unversioned `python` symlink). The hook failed with `python: command not found` on developer machines.
- **Root cause:** Hardcoded `python` in `entry:` assumes an unversioned symlink exists. macOS has it (via Xcode), but Debian/Ubuntu do not install `python` by default.
- **Rule:** PRECOMMIT-05 — Use `python3` not `python` in all entry commands.
- **Solution:** Change `entry: python script.py` to `entry: python3 script.py`. For `language: python` hooks (pre-commit handles resolution), use `language: python` instead of a bare `python` entry.

---

### Pitfall 3: CAFDS Scanned `.omo/` Plans

- **Opis:** The CAFDS docs validation hook scanned `.omo/` directory files (planning documents without YAML frontmatter). These files lack `doc_id`, `type`, and other required frontmatter fields, causing CAFDS to fail on every commit.
- **Root cause:** CAFDS excluded directories were not configured. The validator scanned all `.md` files under the project root, including `.omo/plans/*.md`.
- **Rule:** PRECOMMIT-12 — CAFDS `excluded_dirs` in `afds_config.yaml` MUST match directories excluded by pre-commit doc validation hook.
- **Solution:** Add `.omo` to `excluded_dirs` in `afds_config.yaml`. The pre-commit doc hook and CI must use the same exclusion list.

---

### Pitfall 4: Unit Tests Timed Out `git commit`

- **Opis:** A full `pytest` suite took 35 seconds, exceeding pre-commit's default 30-second hook timeout. The commit was aborted with a timeout error, but only intermittently (depending on test cache state).
- **Root cause:** Heavy test suites (integration tests with network calls, device communication) were placed in the `pre-commit` stage instead of `pre-push`.
- **Rule:** PRECOMMIT-07 — Heavy tests (integration, e2e) go to `pre-push` stage, not `pre-commit`. Also PRECOMMIT-08 — pre-commit total runtime MUST be under 30 seconds.
- **Solution:** Move integration tests to `pre-push` stage. Keep only fast unit tests (`pytest -q --timeout=5`) in pre-commit. Split `tests/` into `tests/unit/` and `tests/integration/`.

---

### Pitfall 5: Agent Used `--ignore` to Skip Failures

- **Opis:** An AI agent encountered old-style `except` syntax that ruff flagged. Instead of fixing the syntax, the agent added `--ignore` to the ruff hook entry, masking the error. The hook continued to silently skip valid lint violations.
- **Root cause:** The agent chose the path of least resistance — masking the error — rather than fixing the underlying code. Pre-commit config is too easy to override.
- **Rule:** PRECOMMIT-04 — NEVER use `|| true` or `--ignore` to mask errors.
- **Solution:** Remove `--ignore` flags from all hook entries. Fix the underlying code. Add a CI check: `grep -r '\-\-ignore\b\| || true' .pre-commit-config.yaml` that fails if masking patterns are present.

---

### Pitfall 6: YAML Parsing Errors from Complex Bash in `entry:`

- **Opis:** A hook used `entry: bash -c '...'` with pipes, redirects, and special characters (quotes, backticks). The YAML parser failed on the nested quoting, producing `could not determine a constructor for the tag 'tag:yaml.org,2002:bash'`.
- **Root cause:** Inline shell commands with special characters break YAML parsing. The `entry:` field expects a simple command string, not inline scripts.
- **Rule:** PRECOMMIT-05 (entry format) — Complex shell logic must use `entry: |` literal block scalar or a wrapper script, not inline `bash -c '...'`.
- **Solution:** Replace `entry: bash -c 'complex command with pipes and quotes'` with:
  ```yaml
  - id: custom-hook
    entry: |
      python3 -c "
      import sys, subprocess
      result = subprocess.run(['ruff', 'check', '.'], capture_output=True)
      sys.exit(result.returncode)
      "
    language: python
  ```

---

### Pitfall 7: `fastmcp` Env Issue Blocked ALL Tests

- **Opis:** A pre-existing `fastmcp` installation issue (incompatible dependency version) caused `ImportError` when pytest tried to collect tests. Pre-commit reported "Passed" because all *collected* tests passed — but zero tests were collected. The environment issue silently blocked the entire test suite.
- **Root cause:** The `fastmcp` library was installed with a version that didn't match the project's requirements. This is a pre-existing environment issue, not a code bug.
- **Rule:** See known env issue documentation. This is a pre-flight check, not a pre-commit rule. Run `pytest --collect-only` before enabling hooks.
- **Solution:** Pin `fastmcp` in project dependencies with an exact version constraint. Add a pre-commit hook `id: check-imports` that runs `python3 -c "import fastmcp"` to validate the environment. Also add `pytest --tb=short 2>&1 | grep -q "ERROR" && exit 1` to catch collection errors (see Pitfall 10).

---

### Pitfall 8: `mypy` Passed Locally but FAILED in CI Lint Job

- **Opis:** mypy passed on every developer machine but failed in CI with dozens of `import-not-found` errors. The CI lint job ran `pip install ruff mypy bandit` without project dependencies, so mypy couldn't resolve any third-party types. `ignore_missing_imports` had been removed globally (good practice), but overrides only existed for `yaml.*` — missing `fastmcp.*`, `requests.*`, `pyyaml.*`, `starlette.*`, `uvicorn.*`, `dateutil.*`, `pydantic.*`.
- **Root cause:** Classic environment mismatch. Pre-commit runs in the developer's full local environment (`pip install -e ".[dev]"`), so mypy finds all deps. CI lint runs in a minimal environment (`pip install ruff mypy bandit`). mypy's `ignore_missing_imports` was global OFF, per-package overrides only covered `yaml.*`. Every third-party import was an unresolved error in CI.
- **Rule:** PRECOMMIT-11 — `[[tool.mypy.overrides]]` MUST list every third-party dependency used by the project. CI lint jobs often have minimal environments.
- **Solution:** In `pyproject.toml`, add explicit overrides for ALL third-party packages:
  ```toml
  [[tool.mypy.overrides]]
  module = [
      "fastmcp.*",
      "requests.*",
      "pyyaml.*",
      "starlette.*",
      "uvicorn.*",
      "dateutil.*",
      "pydantic.*",
  ]
  ignore_missing_imports = true
  ```
  **Detailed fix from deployment:** Added all 7 overrides matching the project's actual imports. Also add a CI pre-check: `python3 -c "import fastmcp, requests, yaml, starlette, uvicorn, dateutil, pydantic; print('All deps OK')"` to the CI lint job to surface import issues early.

  **Standard rule usage:** Always check the project's actual imports before writing mypy overrides. Don't guess — scan `import` statements.

---

### Pitfall 9: CAFDS Passed Locally but FAILED in CI

- **Opis:** The CAFDS doc validation hook passed on `git commit` (pre-commit excluded `.omo/`), but failed in CI. CI ran CAFDS with its own config, which did NOT exclude `.omo/`. CI scanned `.omo/plans/*.md` — planning documents without YAML frontmatter — triggering validation failures.
- **Root cause:** Pre-commit and CI used different CAFDS targets. The pre-commit hook excluded `.omo/` but the CI `afds_config.yaml` had no `excluded_dirs` entry for `.omo`. The two environments were configured independently.
- **Rule:** PRECOMMIT-12 — CAFDS `excluded_dirs` in `afds_config.yaml` MUST match the directories excluded by pre-commit doc validation hook.
- **Solution:** Add `.omo` to `excluded_dirs` in `afds_config.yaml`:
  ```yaml
  excluded_dirs:
    - .omo
    - .git
    - __pycache__
  ```
  Also add a CI check that validates the two exclusion lists are identical: `diff <(yq '.excluded_dirs' afds_config.yaml) <(echo -e '.omo\n.git\n__pycache__')`.

---

### Pitfall 10: Tests Passed Locally but FAILED in CI — Progressive Discovery

- **Opis:** `list_tools_endpoint` changed API format from `{tools: [...]}` to `{categories: {...}}`. Existing tests asserted the old format. Locally, `fastmcp` import error prevented `test_server.py` from being collected, so pytest collected 0 tests from that file and pre-commit reported "Passed" (all collected tests passed). In CI, `fastmcp` was available, so tests were collected, and assertions failed against the new API format.
- **Root cause:** Environment-specific import errors made pre-commit blind to certain test files. Pre-commit only reports failure on tests that are collected — if a file fails to import, it's silently skipped (collection error, not test failure). The test suite had progressive discovery: CI found tests that local couldn't even import.
- **Rule:** PRECOMMIT-13 — Pre-commit MUST NOT silently pass when test files fail to collect. Catch collection errors.
- **Solution:** Add a collection error check after every `pytest` invocation:
  ```yaml
  - id: pytest
    name: pytest
    entry: |
      bash -c '
      pytest -q --tb=short 2>&1 | tee /tmp/pytest-out.txt
      grep -q "ERROR" /tmp/pytest-out.txt && exit 1
      '
    language: system
  ```
  Also add `python3 -m pytest --collect-only -q` as a separate hook before the test hook to surface import errors early.

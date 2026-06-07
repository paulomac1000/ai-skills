---
description: Single authoritative standard for GitHub Actions CI/CD workflows across Python and .NET projects with Docker — CI pipeline, security scanning, Docker publish, auto-tag, dependency management, action versions, coverage, and documentation validation
doc_id: ref.ci-cd-standard
type: ref
status: active
rigor_tier: L2
ttl_days: 365
stability: stable
ai_scope: editable
domain: ci-cd
tags: ["ci-cd", "github-actions", "workflows", "docker", "python", "dotnet", "testing", "coverage", "security", "dependabot"]
owners: ["backend-team"]
upstream:
  - ref.mcp-server-standards
source_of_truth: true
last_verified: "2026-05-21"
doc_kind: atomic
standard_version: "2.1.0"
---

# CI/CD Standard — Unified Pipelines for Python, .NET, and Polyglot Projects

> [!IMPORTANT]
> This document is the single authoritative source of truth for how GitHub Actions CI/CD workflows are structured, maintained, and validated across all compliant projects. It covers Python + Docker, .NET + NuGet, and polyglot projects with unified security scanning, dependency management, and documentation validation. All CI/CD workflow files in compliant projects MUST conform to these rules.
>
> If any project workflow file contradicts this standard, **this file takes precedence**. Update the project workflow to match.

## PURPOSE

Define a unified, version-locked, and reproducible CI/CD pipeline standard for Python projects using GitHub Actions and Docker. Ensure every project follows the same workflow structure, tool versions, quality gates, and publish process. The standard supports multiple project archetypes (MCP servers, web services, CLI tools, libraries) through a configurable parameter system rather than per-project hardcoding.

## SCOPE

- INCLUDED: GitHub Actions workflow files (`.github/workflows/*.yml`), CI pipeline job structure, linting rules, test execution, coverage reporting, Docker build and smoke testing, Docker publish to GHCR, NuGet publish to GitHub Packages, automatic version tagging, documentation validation (CAFDS), Codecov integration, Semgrep security scanning, Dependabot dependency management, project configuration contract, and PR feedback patterns.
- INCLUDED LANGUAGES: Python (primary), .NET (variant), polyglot (mixed-language projects using language-agnostic workflows).
- EXCLUDED: Deployment infrastructure, production monitoring, secrets management outside `.env` files, project-specific business logic tests, AI-driven PR review agents.

## DEFINITIONS

- **CI**: Continuous Integration — the automated pipeline that runs on every push and pull request.
- **CD**: Continuous Delivery — the automated pipeline that publishes artifacts (Docker images, NuGet packages) and creates GitHub Releases.
- **GHCR**: GitHub Container Registry (`ghcr.io`).
- **CAFDS**: Cortexa AI-First Documentation Standard — the documentation framework defined in `ref.documentation-standard` (formerly AFDS).
- **SSOT**: Single Source of Truth — each configuration value is defined in exactly one location.
- **Project Configuration Contract**: A machine-readable description of project-specific parameters (source directory, package name, language, port numbers, and others) that templates consume to produce workflow files. Defined in `.github/ci-cd-config.yaml` or `pyproject.toml [tool.ci-cd]`.
- **Smoke Test**: A minimal test that verifies the built artifact (Docker image) starts correctly and responds to basic health checks.
- **Source Layout Variant**: One of several supported directory structures for source code. The standard provides templates for each variant.
- **SARIF**: Static Analysis Results Interchange Format — standard format for static analysis results, consumed by GitHub Security tab.
- **Dependabot**: GitHub's automated dependency update tool, configured via `.github/dependabot.yml`.
- **Polyglot Project**: A repository containing code in multiple programming languages. Uses language-agnostic workflows (Semgrep, docs validation) plus language-specific CI as needed.

## RULES

### Rule 1: Standard Workflow Files

Every compliant repository MUST contain exactly three GitHub Actions workflow files:

| File | Purpose | Trigger |
|------|---------|---------|
| `.github/workflows/ci.yml` | Continuous Integration | `push` to main/master, `pull_request` to main/master, `workflow_dispatch` |
| `.github/workflows/publish.yml` | Docker publish + GitHub Release | `workflow_run` (CI success on main), `push tags v*`, `workflow_dispatch` |
| `.github/workflows/auto-tag.yml` | Automatic version tagging | `pull_request closed` (merged to main) |

**[RULE: CI-CDW-1] [L1+]** All three workflow files MUST be present in every compliant repository.

**[RULE: CI-CDW-2] [L1+]** `ci.yml` MUST be named `ci.yml`. `publish.yml` MUST be named `publish.yml`. `auto-tag.yml` MUST be named `auto-tag.yml`.

### Rule 2: Unified Action Versions

All compliant CI/CD workflows MUST use the same pinned versions of GitHub Actions. Version drift across projects is prohibited.

| Action | Version | Purpose |
|--------|---------|---------|
| `actions/checkout` | `v6` | Checkout repository |
| `actions/setup-python` | `v6` | Set up Python runtime |
| `docker/setup-buildx-action` | `v4` | Set up Docker Buildx |
| `docker/login-action` | `v4` | Log in to container registry |
| `docker/metadata-action` | `v6` | Extract Docker tags and labels |
| `docker/build-push-action` | `v7` | Build and push Docker image |
| `actions/attest-build-provenance` | `v2` | Generate artifact attestation |
| `softprops/action-gh-release` | `v3` | Create GitHub Release |
| `codecov/codecov-action` | `v6` | Upload coverage to Codecov |
| `actions/upload-artifact` | `v7` | Upload build artifacts |

**[RULE: CI-CDW-3] [L1+]** All workflow files MUST use the exact action versions listed above. Upgrading an action version requires updating this standard first, then propagating to all projects. For the full version history and upgrade policy, see `references/action-version-matrix.md`.

### Rule 3: Python Version

**[RULE: CI-CDW-4] [L1+]** All CI workflows MUST use the latest available stable Python version. At time of writing, this is `3.14`. The version MUST be set in the `with.python-version` field of `actions/setup-python` and MUST be read from the project's configuration contract (`ci-cd-config.yaml` or `pyproject.toml [tool.ci-cd]`). It MUST NOT be hardcoded differently per project.

### Python Version Policy

| Python Version | Status | GitHub Actions | Notes |
|---------------|--------|---------------|-------|
| 3.14 | **Stable (latest)** | ✅ Available | Default for new projects |
| 3.13 | Supported | ✅ Available | Reliable fallback |
| 3.12 | Supported | ✅ Available | Active maintenance |
| 3.11 | **Minimum Supported** | ✅ Available | Legacy projects |

**[RULE: CI-CDW-4a] [L1+]** Python 3.14 is now the standard target for all projects. Legacy projects SHOULD upgrade to 3.14. Teams MAY maintain 3.11 support for external-facing libraries.

### Rule 4: CI Pipeline Structure (`ci.yml`)

The CI pipeline consists of three sequential jobs. Each job depends on the previous one succeeding.

**[RULE: CI-CDW-5] [L1+]** The `ci.yml` workflow MUST contain exactly three jobs in this order: `lint`, `test`, `docker-smoke`. The `pull_request` trigger MUST NOT have a `branches:` filter — this ensures CI runs on every PR regardless of target branch. The `push` trigger MUST filter to `[main, master]` only.

```yaml
on:
  push:
    branches: [main, master]
  pull_request:
  workflow_dispatch:
```

#### 4.1 Job: `lint`

**[RULE: CI-CDW-6] [L1+]** The `lint` job MUST run the following checks in order:

```yaml
steps:
  - uses: actions/checkout@v6
  - uses: actions/setup-python@v6
    with:
      python-version: "3.14"
  - name: Install dependencies and linting tools
    run: |
      python -m pip install --upgrade pip
      pip install -e ".[dev]"
      pip install ruff mypy bandit
  - name: Ruff check
    run: ruff check .
  - name: Ruff format check
    run: ruff format --check .
  - name: mypy
    run: mypy <SRC_DIR>/ --strict
  - name: bandit
    run: bandit -r <SRC_DIR>/ -ll
```

**[RULE: CI-CDW-7] [L1+]** `ruff check` MUST NOT use `--ignore` flags. All linting rules apply uniformly. Projects configure exemptions in `pyproject.toml [tool.ruff]`, not in CI.

**[RULE: CI-CDW-8] [L1+]** `mypy` MUST use `--strict` mode. `--ignore-missing-imports` is prohibited. Missing type stubs MUST be installed or declared in `pyproject.toml [tool.mypy]` override section.

**[RULE: CI-CDW-9] [L1+]** `bandit` MUST use severity level `-ll` (low, medium). The command MUST NOT use `|| true` — real security issues must fail the pipeline.

#### 4.2 Job: `test`

**[RULE: CI-CDW-10] [L1+]** The `test` job MUST run unit tests with coverage:

```yaml
steps:
  - uses: actions/checkout@v6
  - uses: actions/setup-python@v6
    with:
      python-version: "3.14"
  - name: Install dependencies
    run: |
      python -m pip install --upgrade pip
      pip install -e ".[dev]"
  - name: Run unit tests
    run: |
      pytest tests/unit/ -v --tb=short \
        --cov=<PACKAGE> \
        --cov-report=term-missing \
        --cov-report=xml
  - name: Upload coverage to Codecov
    uses: codecov/codecov-action@v6
    with:
      files: ./coverage.xml
      fail_ci_if_error: false
      token: ${{ secrets.CODECOV_TOKEN }}
```

**[RULE: CI-CDW-11] [L2+]** Dependencies SHOULD be installed via `pip install -e ".[dev]"` (editable install with dev extras). If the project uses `requirements.txt` instead of `pyproject.toml` extras, `pip install -r requirements.txt` is acceptable.

**[RULE: CI-CDW-12] [L2+]** Coverage SHOULD be reported via `--cov=<PACKAGE> --cov-report=term-missing`. The `--cov-fail-under` flag is optional but recommended at 80%.

**[RULE: CI-CDW-13] [L2+]** Integration tests SHOULD run in the `test` job if they do not require external services. If they require Docker services, they SHOULD run in a separate step with the service configured (see Rule 12: Service Integration in CI).

**[RULE: CI-CDW-14] [SHOULD]** Codecov upload SHOULD use `fail_ci_if_error: false` to avoid blocking CI when Codecov is unavailable. For public repositories, Codecov is recommended. For private repositories, it is optional. The `secrets` context is NOT available in `if:` conditions — do not gate the Codecov step on `secrets.CODECOV_TOKEN`.

#### 4.3 Job: `docker-smoke`

**[RULE: CI-CDW-15] [L1+]** The `docker-smoke` job MUST build a Docker image exactly once and verify it via smoke tests. The Docker image MUST NOT be built in a separate job — building and testing share the same job.

**[RULE: CI-CDW-16] [L1+]** The smoke test MUST verify at least one health/readiness check. For MCP-compliant projects, this MUST include an exact tool count assertion and REST API health endpoint verification. For non-MCP projects (see Rule 14), this MUST verify the project's primary health endpoint.

**[RULE: CI-CDW-17] [SHOULD]** If the server exposes a REST API, the smoke test SHOULD verify at least one data endpoint in addition to health.

**[RULE: CI-CDW-18] [L1+]** Placeholder values (`<SRC_DIR>`, `<PACKAGE>`, `<IMAGE_NAME>`, `<HEALTH_PORT>`, `<SMOKE_NAME>`) MUST be substituted from the project's configuration contract. These are documentation markers in this standard, not literal YAML.

### Rule 5: Docker Publish (`publish.yml`)

**[RULE: CI-CDW-19] [L1+]** The `publish.yml` workflow MUST trigger on three events:
1. `workflow_run` — when `ci.yml` completes successfully on the `main` branch
2. `push` — when a tag matching `v*` is pushed
3. `workflow_dispatch` — manual trigger

**[RULE: CI-CDW-20] [L1+]** The publish workflow MUST build multi-architecture images:

```yaml
platforms: linux/amd64,linux/arm64
```

**[RULE: CI-CDW-21] [L1+]** Docker metadata tagging MUST include semver, SHA, and latest:

```yaml
tags: |
  type=semver,pattern={{version}}
  type=semver,pattern={{major}}.{{minor}}
  type=semver,pattern={{major}}
  type=sha,format=short
  type=raw,value=latest,enable=${{ github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/tags/v') }}
```

**[RULE: CI-CDW-22] [L1+]** The publish workflow MUST generate artifact attestation using `actions/attest-build-provenance@v2` with `push-to-registry: true`.

**[RULE: CI-CDW-23] [L1+]** The publish workflow MUST create a GitHub Release when triggered by a tag push:

```yaml
- name: Create GitHub Release
  if: startsWith(github.ref, 'refs/tags/v')
  uses: softprops/action-gh-release@v3
  with:
    generate_release_notes: true
    make_latest: true
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**[RULE: CI-CDW-24] [L1+]** `publish.yml` MUST NOT contain hardcoded version strings (e.g., `type=raw,value=1.2.0`). All tags MUST be derived from the Git reference or metadata action.

**[RULE: CI-CDW-25] [L1+]** The publish job MUST request these permissions:

```yaml
permissions:
  contents: write
  packages: write
  attestations: write
  id-token: write
```

**[RULE: CI-CDW-26] [L1+]** The publish workflow MUST use environment variables for registry and image name:

```yaml
env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}
```

### Rule 6: Auto Tag (`auto-tag.yml`)

**[RULE: CI-CDW-27] [L1+]** Every compliant repository MUST have an `auto-tag.yml` workflow that automatically creates and pushes a Git tag when a PR is merged to the default branch.

```yaml
name: Auto-tag on merge to main

on:
  pull_request:
    branches: [main]
    types: [closed]

jobs:
  tag:
    if: github.event.pull_request.merged == true
    runs-on: ubuntu-latest
    permissions:
      contents: write

    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0

      - name: Extract version from pyproject.toml
        id: version
        run: |
          VERSION=$(grep 'version = ' pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/')
          echo "version=$VERSION" >> "$GITHUB_OUTPUT"
          echo "Found version: $VERSION"

      - name: Create and push tag
        run: |
          git config user.name "<PROJECT>-bot"
          git config user.email "bot@<PROJECT>.local"
          git tag "v${{ steps.version.outputs.version }}"
          git push origin "v${{ steps.version.outputs.version }}"
```

**[RULE: CI-CDW-28] [L1+]** The bot name MUST follow the pattern `<project-name>-bot` with email `bot@<project-name>.local`. The `<PROJECT>` placeholder is substituted from the project's configuration contract.

**[RULE: CI-CDW-76] [L2+]** The `auto-tag.yml` workflow MUST include a `gh workflow run` step after tag creation to trigger the downstream publish workflow. GitHub's default `GITHUB_TOKEN` does not trigger workflow events (push, repository_dispatch) — a `git push` of a tag from a workflow WILL NOT trigger `publish.yml`'s `push: tags: ["v*"]` trigger. Using `gh workflow run` (which calls the GitHub API directly) bypasses this restriction. This step MUST NOT fail the auto-tag workflow if the publish workflow does not exist (non-Docker projects, .NET projects with inline pack-publish).

**[RULE: CI-CDW-76a] [L2+]** The `auto-tag.yml` workflow MUST include `actions: write` permission for the `gh workflow run` step.

**[RULE: CI-CDW-76b] [SHOULD]** The `auto-tag.yml` workflow SHOULD include `workflow_dispatch` trigger to allow manual tag creation from the GitHub Actions UI.

**[RULE: CI-CDW-76c] [L2+]** The `gh workflow run` target MUST use the workflow filename (e.g., `publish.yml`) rather than the workflow display name (e.g., `"Create and publish a Docker image"`). Filenames are immutable references in version control; display names can change independently and would silently break the auto-tag→publish chain.

**[RULE: CI-CDW-76d] [L2+]** The `auto-tag.yml` job condition MUST include `github.event_name == 'workflow_dispatch'` as an alternative entry point. When triggered manually via `workflow_dispatch`, there is no `github.event.pull_request` object — `github.event.pull_request.merged == true` evaluates to `false` and the job is silently skipped. Full condition: `github.event_name == 'workflow_dispatch' || github.event.pull_request.merged == true`.

### Rule 6a: Documentation Validation Tuning (`CI-CDW-77`, `CI-CDW-78`)

**[RULE: CI-CDW-77] [L2+]** The `--strict` flag on documentation validation MUST be configurable per-project (via `ci-cd-config.yaml` or workflow variable) and SHOULD default to off in CI. Warnings such as duplicate section headers or unknown sections in L2-tier validation are advisory and should not fail CI. Strict mode is for projects that want zero-tolerance enforcement.

**[RULE: CI-CDW-78] [L1+]** `CHANGELOG.md` MUST be listed in `afds_config.yaml exempt_files`. Changelogs are version-history documents, not AFDS-compliant structured documents. AFDS §2.2 explicitly lists `CHANGELOG.md` as a root-level non-AFDS file. Without this exemption, AFDS validation fails on CHANGELOG.md because it lacks YAML frontmatter. Projects using the standard SHOULD also exempt `README.md` (already documented in AFDS spec).

### Rule 7: Documentation Validation (AFDS)

**[RULE: CI-CDW-29] [L2+]** Every project that contains documentation files with YAML frontmatter (excluding `README.md`) MUST validate them against the AFDS standard in CI.

**[RULE: CI-CDW-30] [L2+]** The AFDS validation MUST run in the `lint` job after the security scan:

```yaml
- name: Validate documentation (CAFDS)
  if: hashFiles('afds_config.yaml') != ''
  run: |
    curl -sS https://raw.githubusercontent.com/paulomac1000/ai-skills/main/skills/afds-doc-writer/docs_validate.py | python3 - \
      --config afds_config.yaml --strict --baseline .afds-baseline.json ./
```

**[RULE: CI-CDW-31] [L2+]** Every project `README.md` SHOULD link to the project's standards repository or documentation for contributors. The README is a human-first document (not AFDS-governed) per `ref.documentation-standard`.

### Rule 8: Project Configuration Contract

**[RULE: CI-CDW-32] [L1+]** Every compliant project MUST define its CI/CD parameters in a single machine-readable location. Accepted formats (checked in order):
1. `.github/ci-cd-config.yaml` (preferred — dedicated CI/CD config)
2. `pyproject.toml` under `[tool.ci-cd]` section
3. Direct substitution in workflow files (for projects without a config file — requires manual replacement of each `<PLACEHOLDER>`)

The configuration contract defines these parameters:

| Parameter | Required | Description | Example |
|-----------|----------|-------------|---------|
| `src_dir` | Yes | Source code directory for lint/type/bandit scan | `src/my_package/` or `tools/` |
| `package` | Yes | Python package name for `--cov` | `my_package` |
| `project` | Yes | Short project name for Docker tags and bot | `my-project` |
| `language` | Yes | Primary project language: `python`, `dotnet`, or `polyglot` | `python` |
| `python_version` | No | Python version (default: latest stable, currently `3.14`) | `"3.14"` |
| `image_name` | No | Docker image name for local smoke testing (default: `<project>:test`) | `my-project:test` |
| `health_port` | No | Port for health/smoke endpoint verification | `8080` |
| `smoke_name` | No | Docker container name for smoke test (default: `<project>-smoke`) | `my-project-smoke` |
| `use_docker` | No | Whether to run docker-smoke job (default: `true`) | `true` / `false` |
| `is_mcp` | No | Whether the project is an MCP server — controls tool count smoke test (default: `false`) | `true` / `false` |
| `expected_tools` | No | Exact tool count for MCP smoke test (required if `is_mcp: true`) | `24` |
| `rest_port` | No | REST API port for MCP smoke test (required if `is_mcp: true`) | `9096` |
| `services` | No | External services needed for integration tests (see Rule 12) | `{mosquitto: {image: eclipse-mosquitto:latest, ports: ["1883:1883"]}}` |
| `dockerfile_target` | No | Dockerfile build target stage (default: none, builds default target) | `prod` |
| `use_codecov` | No | Whether to upload to Codecov (default: `true` for public repos) | `true` / `false` |
| `use_semgrep` | No | Whether to run Semgrep security scanning (default: `true`) | `true` / `false` |
| `use_dependabot` | No | Whether to generate `.github/dependabot.yml` (default: `true`) | `true` / `false` |
| `package_ecosystems` | No | Additional package ecosystems for Dependabot (default: `["github-actions", "pip"]`) | `["github-actions", "pip", "nuget"]` |
| `use_docs_validation` | No | Whether to validate documentation in CI (default: `false`, auto-enabled when `docs/` exists) | `true` / `false` |
| `docs_paths` | No | Paths to scan for documentation validation | `["docs/", "*.md"]` |
| `docs_validation_script` | No | Path to the documentation validation script | `scripts/validate_docs.py` |
| `dotnet_version` | No | .NET SDK version (required when `language: dotnet`) | `"10.0.x"` |
| `dotnet_solution` | No | Path to .NET solution file (required when `language: dotnet`) | `src/MyApp.sln` |
| `version_source` | No | Source for auto-tag version extraction: `"pyproject"` (default) or `"directory-build-props"` (.NET) | `"pyproject"` |

**[RULE: CI-CDW-37] [L2+]** When `.github/ci-cd-config.yaml` exists, it is the SSOT for all CI/CD parameters. Workflow files SHOULD be regenerated from templates when configuration changes. The SKILL.md describes the regeneration workflow.

### Rule 9: Project-Specific Customizations

**[RULE: CI-CDW-33] [L2+]** Projects MAY add project-specific CI steps, but MUST NOT remove or weaken any step defined in this standard.

**Allowed customizations:**
- Adding a `services` block for integration tests (e.g., Mosquitto for MQTT-based projects)
- Adding integration test execution in the `test` job (after unit tests)
- Adding a manifest verification step in `docker-smoke` (for MCP projects)
- Adding `--cov-fail-under=80` to pytest
- Adding a bandit report upload as an artifact (using `actions/upload-artifact@v7`)
- Adding extra lint steps (e.g., `vulture` for dead code detection) after bandit
- Adding platform-specific test steps (e.g., `pip install nmap` for network scan tests)
- Adding a multi-stage Dockerfile target (`dockerfile_target` parameter)

**Prohibited customizations:**
- Removing `--strict` from mypy
- Adding `--ignore` flags to ruff in the CI step (exemptions go in `pyproject.toml`)
- Adding `|| true` to bandit
- Combining `lint` and `test` into a single job
- Skipping the `docker-smoke` job (unless `use_docker: false`)
- Using different action versions than specified in Rule 2
- Hardcoding version numbers in publish tags
- Building the Docker image twice (once in one job and again in another)
- Downgrading action versions below what the standard specifies
- Removing `needs:` dependencies between sequential jobs

### Rule 10: Source Layout Variants

Projects use different directory layouts. The standard supports three variants. The `src_dir` parameter in the configuration contract determines which variant applies.

**[RULE: CI-CDW-38] [L2+]** Projects MUST use one of these three source layout variants:

| Variant | `src_dir` pattern | Used by | Mypy/Bandit path | `--cov` package |
|---------|-------------------|---------|------------------|-----------------|
| **A: Standard `src/` layout** | `src/<package>/` | New projects | `src/<package>/` | `<package>` |
| **B: Flat `tools/` layout** | `tools/` | Legacy projects | `tools/` | `tools` or `.` |
| **C: Nested `src/<pkg>/tools/` layout** | `src/<package>/tools/` | Hybrid projects | `src/<package>/` | `<package>` |

The `src_dir` field drives three substitutions in `ci.yml`:
1. `mypy <SRC_DIR>/ --strict`
2. `bandit -r <SRC_DIR>/ -ll`
3. `--cov=<PACKAGE>` (via the `package` field)

**[RULE: CI-CDW-39] [L2+]** For Variant B (`tools/`), `ruff check .` and `ruff format --check .` still run on the entire repository. Only mypy and bandit are scoped to `tools/`.

### Rule 11: Docker-less Projects

Not all Python projects require Docker. The standard accommodates this through the `use_docker` configuration parameter.

**[RULE: CI-CDW-35] [L2+]** When `use_docker: false` in the configuration contract:
- The `docker-smoke` job is replaced by a `smoke` job that runs smoke tests directly (without Docker).
- The `docker-smoke` job name becomes `smoke`.
- The `publish.yml` workflow is optional (may be absent).
- `[RULE: CI-CDW-1]` is relaxed: only `ci.yml` and `auto-tag.yml` are required.

**[RULE: CI-CDW-36] [L2+]** When `use_docker: false`, the `smoke` job MUST still verify at least one health check:
```yaml
smoke:
  runs-on: ubuntu-latest
  needs: test
  steps:
    - uses: actions/checkout@v6
    - uses: actions/setup-python@v6
      with:
        python-version: "3.14"
    - name: Install dependencies
      run: pip install -e ".[dev]"
    - name: Run smoke tests
      run: pytest tests/smoke/ -v --tb=short
```

### Rule 12: Service Integration in CI

Projects that require external services (MQTT brokers, databases, caches) for integration tests can declare them in the configuration contract.

**[RULE: CI-CDW-40] [L2+]** When the configuration contract defines a `services` block, the `test` job MUST include a `services:` section with those dependencies:

```yaml
test:
  runs-on: ubuntu-latest
  needs: lint
  services:
    mosquitto:
      image: eclipse-mosquitto:latest
      ports:
        - 1883:1883
  steps:
    ...
    - name: Run integration tests
      run: pytest tests/integration/ -v --tb=short
```

**[RULE: CI-CDW-41] [L2+]** When a `docker-smoke` job requires the same services as the `test` job, the `services:` block SHOULD also be added to `docker-smoke`:

```yaml
docker-smoke:
  runs-on: ubuntu-latest
  needs: test
  services:
    mosquitto:
      image: eclipse-mosquitto:latest
      ports:
        - 1883:1883
  steps:
    ...
```

**[RULE: CI-CDW-42] [SHOULD]** Integration test steps that require services SHOULD use `--network host` when running Docker containers for smoke tests to allow the container to reach the service on localhost.

### Rule 13: Standard Versioning and Compatibility

The CI/CD standard itself is versioned. Each version specifies compatible action versions and the target Python version.

**[RULE: CI-CDW-43] [L2+]** The `standard_version` field in this document's frontmatter is the SSOT for the current standard version. Changes to action versions or Python version require a new standard version.

| Standard Version | actions/checkout | setup-python | buildx | login | metadata | build-push | attest-build-provenance | gh-release | codecov | Python |
|------------------|-----------------|--------------|--------|-------|----------|------------|--------|------------|---------|--------|
| 2.0.0 | v6 | v6 | v4 | v4 | v6 | v7 | v2 | v3 | v6 | 3.14 |
| 1.0.0 (retired) | v6 | v6 | v4 | v4 | v6 | v7 | v4 | v3 | v6 | 3.14 |

**[RULE: CI-CDW-44] [L2+]** When this standard is updated, all compliant projects MUST be updated to match within 30 days. The migration workflow in SKILL.md provides step-by-step guidance.

### Rule 14: Non-MCP Smoke Tests

For projects that are not MCP servers (`is_mcp: false`), the docker-smoke test verifies generic health rather than tool counts.

**[RULE: CI-CDW-45] [L2+]** For non-MCP projects, the `docker-smoke` job MUST include at minimum a basic start-and-health-check verification:

```yaml
- name: Smoke test — health check
  run: |
    docker run -d --rm \
      -p <HEALTH_PORT>:<HEALTH_PORT> \
      --name <SMOKE_NAME> <IMAGE_NAME>:test
    sleep 5
    curl -fsS --retry 10 --retry-delay 2 \
      http://localhost:<HEALTH_PORT>/health || exit 1
    echo "Health check OK"
    docker stop <SMOKE_NAME>
```

**[RULE: CI-CDW-46] [SHOULD]** Non-MCP projects SHOULD add an additional verification step that calls a data endpoint (e.g., `/api/version`, `/api/status`) to confirm the application logic is functional beyond only the health check.

### Rule 16: Semgrep Security Scanning

Every project MUST include automated security scanning via Semgrep. This is a language-agnostic check that catches secrets, OWASP Top Ten vulnerabilities, and common security anti-patterns.

**[RULE: CI-CDW-47] [L1+]** Every compliant repository MUST have a `semgrep.yml` workflow triggered on PR (`opened, synchronize, ready_for_review`) and push to main.

**[RULE: CI-CDW-48] [L1+]** Semgrep MUST use the following rule sets: `p/auto`, `p/secrets`, `p/owasp-top-ten`.

**[RULE: CI-CDW-49] [L1+]** SARIF results MUST be uploaded to GitHub Security tab via `github/codeql-action/upload-sarif@v4`.

**[RULE: CI-CDW-50] [L2+]** A scheduled full scan (`semgrep-scheduled.yml`) MUST run daily at 03:00 UTC to catch issues in newly published rules.

**[RULE: CI-CDW-51] [L2+]** On PR, a status comment MUST be posted or updated using `actions/github-script@v9` with a persistent marker (`<!-- semgrep-bot -->`). The comment updates on subsequent runs instead of creating duplicates.

**[RULE: CI-CDW-52] [L1+]** The `semgrep.yml` workflow MUST include `SEMGREP_BASELINE_REF: ${{ github.event_name == 'pull_request' && github.event.pull_request.base.sha || '' }}` in its `env` block so that Semgrep CI reports only NEW findings on PRs (diff-aware mode). On push to main, the variable evaluates to an empty string and Semgrep performs a full scan of the entire codebase. This prevents green PRs from being silently rejected by a red main-branch scan due to pre-existing findings.

**[RULE: CI-CDW-53] [L2+]** The SARIF upload step in both `semgrep.yml` and `semgrep-scheduled.yml` MUST be guarded with `if: always() && hashFiles('semgrep.sarif') != ''` to prevent spurious failures when `returntocorp/semgrep-action` does not produce a SARIF output file.

**[RULE: CI-CDW-53a] [SHOULD]** Projects SHOULD include a `.semgrep.yml` project-level triage config at the repository root to document accepted findings that are not fixable (e.g., HTTP-only IoT devices on a local LAN, root-required Docker containers). Each entry requires a `rule_id`, `paths`, and `reason`. Without a triage file, unfixable findings MUST be triaged in the GitHub Security tab after each push-to-main scan.

**`semgrep.yml` template:**

```yaml
name: Semgrep Security Scan

on:
  pull_request:
    types: [opened, synchronize, ready_for_review]
  push:
    branches: [main]

concurrency:
  group: semgrep-${{ github.event.pull_request.number || github.sha }}
  cancel-in-progress: true

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true
  SEMGREP_BASELINE_REF: ${{ github.event_name == 'pull_request' && github.event.pull_request.base.sha || '' }}

jobs:
  semgrep:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write
      pull-requests: write
      actions: read

    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0

      - name: Semgrep Scan
        id: semgrep
        uses: returntocorp/semgrep-action@713efdd345f3035192eaa63f56867b88e63e4e5d  # v1
        env:
          SEMGREP_RULES: p/auto p/secrets p/owasp-top-ten
        with:
          config: >-
            p/auto
            p/secrets
            p/owasp-top-ten

      - name: Upload SARIF to GitHub Security
        id: upload-sarif
        if: always() && hashFiles('semgrep.sarif') != ''
        continue-on-error: true
        uses: github/codeql-action/upload-sarif@v4
        with:
          sarif_file: semgrep.sarif
          category: semgrep-full
```

### Rule 17: Dependabot Configuration

Automated dependency updates reduce the maintenance burden and ensure security patches are applied promptly.

**[RULE: CI-CDW-54] [L1+]** Every compliant repository MUST have a `.github/dependabot.yml` file.

**[RULE: CI-CDW-55] [L1+]** The `github-actions` ecosystem MUST be present with `interval: "weekly"` and grouped updates.

**[RULE: CI-CDW-56] [L1+]** Language-specific ecosystems (`pip` for Python, `nuget` for .NET) MUST be declared in the configuration contract's `package_ecosystems` field and included in `dependabot.yml`.

**[RULE: CI-CDW-57] [L1+]** All ecosystems MUST use `groups:` to batch updates and reduce PR noise. Each group uses `patterns: ["*"]` to catch all packages.

**`dependabot.yml` template:**

```yaml
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      github-actions:
        patterns:
          - "*"

  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      pip:
        patterns:
          - "*"

  # Additional ecosystems from config contract
```

### Rule 18: Documentation Validation

Documentation quality is enforced through automated validation in CI. This is a content-focused check, independent of programming language.

**[RULE: CI-CDW-58] [L2+]** Projects with documentation files (`**/*.md` beyond `README.md`) MUST have a `docs-validation.yml` workflow.

**[RULE: CI-CDW-59] [L2+]** The workflow MUST use `paths` filters (`**/*.md`) and `tj-actions/changed-files@v47` for incremental validation — only changed documentation files are validated.

**[RULE: CI-CDW-60] [L2+]** On PR, a status comment MUST be posted or updated via `actions/github-script@v9` with marker `<!-- docs-validation-bot -->`. The comment lists failed files and provides fix instructions.

**`docs-validation.yml` template:**

```yaml
name: Documentation Validation

on:
  push:
    branches: [main, develop]
    paths:
      - "**/*.md"
      - "docs/**"
  pull_request:
    branches: [main]
    paths:
      - "**/*.md"
      - "docs/**"

concurrency:
  group: docs-validation-${{ github.ref }}
  cancel-in-progress: true

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

jobs:
  validate-docs:
    name: Validate Documentation
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write

    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v6
        with:
          python-version: "3.11"
          cache: pip

      - name: Install dependencies
        run: pip install pyyaml

      - name: Get changed markdown files
        id: changed-files
        uses: tj-actions/changed-files@v47
        with:
          files: |
            **/*.md
            docs/**
          files_ignore: |
            **/archive/**

      - name: Validate documentation
        id: validate
        if: steps.changed-files.outputs.any_changed == 'true'
        run: |
          # Project-specific validation script — replace with actual validator
          python <VALIDATION_SCRIPT> --ci
```

### Rule 19: Concurrency and Environment Best Practices

Every workflow must prevent redundant runs and ensure Node compatibility for JavaScript-based actions.

**[RULE: CI-CDW-61] [L1+]** Every workflow file MUST declare a `concurrency:` block with `cancel-in-progress: true` to prevent redundant CI runs on rapid pushes. The concurrency group MUST be scoped to the workflow and Git ref:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

For PR-specific workflows, the group SHOULD include the PR number:
```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.sha }}
  cancel-in-progress: true
```

**[RULE: CI-CDW-62] [L1+]** Every workflow or job that uses JavaScript-based actions (all `actions/github-script`, `tj-actions/*`, `dorny/*`, `marocchino/*`) MUST set `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true` as an environment variable. This forces the GitHub Actions runner to use Node 24, avoiding compatibility issues with older Node versions bundled in the runner image.

```yaml
env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true
```

### Rule 20: .NET CI Pipeline (Language Variant)

For .NET projects (`language: dotnet` in the configuration contract), the CI pipeline follows a different structure optimized for the .NET ecosystem.

**[RULE: CI-CDW-63] [L2+]** For .NET projects, the `ci.yml` MUST include these sequential steps: restore, format check, build, test with coverage, and (on tag) pack.

**[RULE: CI-CDW-64] [L2+]** Coverage MUST be collected via `dotnet test` with `--collect:"XPlat Code Coverage"` and reported via `dotnet-reportgenerator-globaltool`. A minimum coverage gate (`check_aggregate_coverage.py`) SHOULD enforce ≥75% line and ≥60% branch coverage.

**[RULE: CI-CDW-65] [L2+]** NuGet packages MUST be cached via `actions/cache@v5` with a key based on `**/*.csproj` and `Directory.Packages.props` hashes:

```yaml
- uses: actions/cache@v5
  with:
    path: ~/.nuget/packages
    key: nuget-${{ hashFiles('**/*.csproj', 'Directory.Packages.props') }}
    restore-keys: nuget-
```

**[RULE: CI-CDW-66] [SHOULD]** Test results SHOULD be published to PR via `dorny/test-reporter@v3` with `reporter: dotnet-trx`.

**[RULE: CI-CDW-67] [L2+]** On tag push (`v*`), the pipeline MUST pack NuGet packages and publish to GitHub Packages:

```yaml
- name: Pack Packages
  if: startsWith(github.ref, 'refs/tags/v')
  run: dotnet pack <SOLUTION>.sln --no-build -c Release -o ./nupkg -p:PackageVersion=${{ env.VERSION }}

- name: Publish to GitHub Packages
  if: startsWith(github.ref, 'refs/tags/v')
  run: dotnet nuget push ./nupkg/*.nupkg \
    --api-key ${{ secrets.GITHUB_TOKEN }} \
    --source "https://nuget.pkg.github.com/${{ github.repository_owner }}/index.json" \
    --skip-duplicate
```

### Rule 21: PR Feedback Patterns

CI workflows that communicate results back to the PR via comments MUST follow a consistent pattern to avoid comment spam.

**[RULE: CI-CDW-68] [L2+]** Every CI bot that posts PR comments MUST use a hidden HTML marker (`<!-- bot-name -->`) as the first line of the comment body. This marker uniquely identifies the bot and enables the "update, don't duplicate" pattern.

**[RULE: CI-CDW-69] [L2+]** Before posting a new comment, the bot MUST search for an existing comment with the same marker and update it. If no existing comment is found, a new comment is created. If the check passes, the bot SHOULD update the existing failure comment to indicate success rather than leaving stale failure messages.

**Canonical implementation** (JavaScript, via `actions/github-script@v9`):

```javascript
const marker = '<!-- bot-name -->';
const issue_number = context.issue.number;
const body = `${marker}\n## Status message...`;

const comments = await github.rest.issues.listComments({
  owner: context.repo.owner,
  repo: context.repo.repo,
  issue_number,
});
const existing = comments.data.find(
  c => c.user.login === 'github-actions[bot]' && c.body.includes(marker)
);
if (existing) {
  await github.rest.issues.updateComment({
    owner: context.repo.owner,
    repo: context.repo.repo,
    comment_id: existing.id,
    body,
  });
} else {
  await github.rest.issues.createComment({
    owner: context.repo.owner,
    repo: context.repo.repo,
    issue_number,
    body,
  });
}
```

### Rule 15: Integration with Upstream Standards

**[RULE: CI-CDW-34] [L2+]** This CI/CD standard implements the CI requirements from `ref.mcp-server-standards` for projects that use that standard:

| MCP Standard Rule | CI/CD Implementation |
|-------------------|---------------------|
| `[RULE: TEST-CI-1]` — CI MUST run linting before tests | `lint` job runs ruff + mypy + bandit before `test` job |
| `[RULE: TEST-CI-2]` — CI MUST run unit tests | `test` job runs pytest with coverage |
| `[RULE: TEST-CI-3]` — CI MUST build Docker and verify tool count | `docker-smoke` job builds image, verifies tool count (when `is_mcp: true`) |
| `[RULE: TEST-CI-4]` — CI MUST run Docker smoke test (L3+) | `docker-smoke` job runs health + tools endpoint smoke test |
| `[L2+]` — CI SHOULD run ruff check, format, mypy, bandit | `lint` job runs all four tools |
| `[L1+]` — Unit tests MUST run in CI on every commit | `test` job runs `pytest tests/unit/` |

### Rule 22: Python Project Metadata Consistency

**[RULE: CI-CDW-70] [L2+]** The `pyproject.toml` classifiers MUST include the Python version used in CI. When `python_version` is set to `"3.14"` in the configuration contract, classifiers SHALL include `"Programming Language :: Python :: 3.14"` and SHOULD include the two preceding stable versions (`3.13`, `3.12`). Outdated classifiers create confusion between the declared and actual runtime.

**[RULE: CI-CDW-71] [L2+]** The `[tool.mypy]` section MUST include:
- `python_version` set to the same value as the CI Python version (currently `"3.14"`)
- `warn_unused_ignores = true` — stale `# type: ignore` comments are tech debt

**[RULE: CI-CDW-72] [L2+]** The `python-version` in `ci.yml`, the `python_version` in `ci-cd-config.yaml`, `[tool.mypy].python_version`, `[tool.ruff].target-version`, and `pyproject.toml` classifiers MUST all agree on the same Python version. Version drift between these sources causes CI failures or false passes.

**[RULE: CI-CDW-82] [L1+]** All `pip install` commands in CI workflows targeting Python ≥3.14 MUST include `--break-system-packages`. The Python 3.14 environment on GitHub Actions runners (PEP 668 compliant) requires this flag for system-level pip operations. Example: `pip install --break-system-packages -e ".[dev]"`. Projects using virtual environments (venv) are exempt from this requirement.

### Rule 23: Full Commit SHA Pinning (`CI-CDW-73`, `CI-CDW-74`, `CI-CDW-75`)

**[RULE: CI-CDW-73] [L1+]** All GitHub Action references in workflow files MUST use the full immutable commit SHA, not a mutable version tag. Example: `uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v6`

**[RULE: CI-CDW-74] [L1+]** The version tag MUST be appended as a YAML comment after the commit SHA for human readability. Mismatched SHA/comment pairs are a CI-CDW-74 violation.

**[RULE: CI-CDW-75] [L2+]** When updating an action version, both the SHA and the comment MUST be updated together. Dependabot can auto-update SHAs when configured with `github-actions` ecosystem and `enable: true` for version updates.

**Rationale:** Version tags like `@v6` are mutable references. An attacker who compromises an action repository can push malicious code to a version tag. Commit SHAs are cryptographically immutable. The trailing comment preserves human readability for code review.

**How to resolve SHAs:**
```bash
git ls-remote https://github.com/<owner>/<repo>.git refs/tags/v<major> | awk '{print $1}'
```

### Rule 24: Checkout Security (`CI-CDW-79`)

**[RULE: CI-CDW-79] [L1+]** Every `actions/checkout` step in every workflow file MUST include `persist-credentials: false`. This prevents the GITHUB_TOKEN from being persisted to subsequent steps, reducing the risk of credential leaks in third-party actions and build scripts.

### Rule 25: Workflow Run Trigger Guard (`CI-CDW-80`)

**[RULE: CI-CDW-80] [L2+]** Workflows using the `workflow_run` trigger MUST guard with explicit `branches:` filter (`[main, master]`) to prevent execution on pull request CI runs. Additionally, the event type MUST be verified (`types: [completed]`) and the triggering workflow MUST have succeeded (`github.event.workflow_run.conclusion == 'success'`).

### Rule 26: Cache Dependency Validation (`CI-CDW-81`)

**[RULE: CI-CDW-81] [L2+]** When using `cache: pip` in `actions/setup-python`, a dependency file (`requirements.txt` or `pyproject.toml`) MUST exist in the repository. For repositories without pip dependencies (e.g., pure documentation repos, .NET-only repos), omit the `cache: pip` option to prevent CI failures from missing cache sources.

## INTERFACES

- INPUT: GitHub repository with configuration contract (`.github/ci-cd-config.yaml` or `pyproject.toml [tool.ci-cd]`), source code, and test suite.
- OUTPUT: CI status (pass/fail), coverage report, Docker image (on main push in CI), published Docker image to GHCR (on tag/release), GitHub Release (on tag), auto-created Git tag (on PR merge).
- SIDE_EFFECTS: CI failures block PR merges. Publish workflow pushes to GHCR. Auto-tag creates and pushes Git tags.

## STATE

- Assumptions: Repository uses GitHub Actions. Python `3.14` is available via `actions/setup-python`. Docker Buildx is available on `ubuntu-latest` runners. Project has a `pyproject.toml` with `version` field. Documentation follows AFDS standard (when applicable). The health endpoint path for smoke tests defaults to `/api/health` (configurable via `health_port` in the configuration contract). MCP server projects that allow public tool access without authentication must set the `MCP_UNSAFE_PUBLIC_ACCESS_CONFIRMED=1` flag in CI environment variables; this is a project-specific opt-in and is never set by the standard templates.
- Constraints: Maximum three workflow files (except Docker-less projects which may have two). Lint, test, docker-smoke run sequentially. Publish requires CI to pass on main (when triggered by `workflow_run`).
- Known Limitations: Codecov upload requires a `CODECOV_TOKEN` secret. Multi-arch Docker builds increase CI time by ~2-3 minutes. AFDS validation downloads the validator script from `https://raw.githubusercontent.com/paulomac1000/ai-skills/main/skills/afds-doc-writer/docs_validate.py` at runtime via curl. Projects without `pyproject.toml` cannot use `auto-tag.yml`.

## EDGE CASES

- CASE: Project does not use `pyproject.toml` (uses `setup.py` or `requirements.txt`) → EXPECTED: `auto-tag.yml` is inapplicable. Replace `pip install -e ".[dev]"` with `pip install -r requirements.txt`.
- CASE: Project has no documentation beyond README → EXPECTED: AFDS validation step is a no-op (gated by `hashFiles` check).
- CASE: Project is private → EXPECTED: Codecov upload is optional. Set `use_codecov: false` in configuration contract.
- CASE: Tag `v*` already exists → EXPECTED: `auto-tag.yml` skips tagging via `git rev-parse` guard and exits 0. The version in `pyproject.toml` must be bumped before the next merge to create a new tag. The workflow MUST NOT fail on duplicate tags — use `if git rev-parse "v$VERSION" >/dev/null 2>&1; then echo "Tag already exists — skipping"; exit 0; fi`.
- CASE: `workflow_run` trigger receives a failed CI → EXPECTED: The publish job's `if` condition skips execution (`github.event.workflow_run.conclusion == 'success'`).
- CASE: Project uses Docker but has no health endpoint → EXPECTED: `docker-smoke` verifies only that the container starts and stays running for a minimum time.
- CASE: Project requires multiple Docker services for smoke test → EXPECTED: Declare all services in configuration contract. Use `--network host` for the smoke container.
- CASE: Project has a non-standard Dockerfile path or target → EXPECTED: Use `dockerfile_target` parameter in configuration contract. Use `file:` parameter on `docker/build-push-action`.
- CASE: Project is not an MCP server but has a REST API → EXPECTED: Set `is_mcp: false`. Use `health_port` for the health endpoint. Smoke test verifies health only.
- CASE: Configuration contract is missing → EXPECTED: The project is treated as non-compliant. See SKILL.md migration workflow for how to add the config contract retroactively.
- CASE: Semgrep `# nosemgrep` suppression in Dockerfiles → EXPECTED: In Dockerfiles, `# nosemgrep:` comments MUST be placed on a SEPARATE line BEFORE the directive they suppress. Inline `#` characters on Dockerfile directive lines (e.g., `USER root  # nosemgrep: ...`) are parsed as part of the directive argument, not as comments. This causes Docker build failures (`unable to find user`). Correct form: `# nosemgrep: rule-id` on a separate preceding line.
- CASE: Direct push to main without a pull request → EXPECTED: The auto-tag workflow fires only on PR merge (`pull_request.closed + merged == true`). Direct pushes to main do NOT create a version tag. To publish after a direct push: (1) verify `pyproject.toml` version is correct, then (2) manually create and push the tag via `git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z`. The publish workflow will then create the release and Docker image from the tag push.

## EXAMPLES

### Example Configuration Contract (`.github/ci-cd-config.yaml`)

```yaml
# CI/CD Configuration Contract for my-project
# This file is the SSOT for all CI/CD parameters.
# Workflow files are generated from this config. See ci-cd-architect SKILL.md.

src_dir: "src/my_package/"
package: "my_package"
project: "my-project"
python_version: "3.14"
image_name: "my-project:test"
health_port: 8080
smoke_name: "my-project-smoke"
use_docker: true
is_mcp: false
use_codecov: true
dockerfile_target: "prod"

services:
  mosquitto:
    image: eclipse-mosquitto:latest
    ports:
      - "1883:1883"
```

### Example Configuration Contract (MCP project)

```yaml
src_dir: "tools/"
package: "tools"
project: "example-mcp"
python_version: "3.14"
image_name: "example-mcp:test"
health_port: 9091
smoke_name: "example-mcp-smoke"
rest_port: 9099
use_docker: true
is_mcp: true
expected_tools: 42
use_codecov: true
```

### Complete `ci.yml` Template (MCP variant)

See `templates/ci.yml.j2` for the Jinja2 template. The template substitutes `<PLACEHOLDERS>` from the configuration contract.

### Complete `publish.yml` Template

See `templates/publish.yml.j2` for the Jinja2 template.

### Complete `auto-tag.yml` Template

See `templates/auto-tag.yml.j2` for the Jinja2 template.

## NON_GOALS

- This standard does not cover deployment orchestration, Kubernetes, or Nomad.
- It does not specify monitoring, alerting, or observability beyond CI exit codes.
- It does not define branching strategies, code review processes, or merge policies.
- It does not cover secrets injection beyond `.env` and GitHub Secrets.
- It does not prescribe a specific tool for generating workflow files from templates (Jinja2 is a suggestion; any template engine works).

## CHANGELOG

### 2.1.0 (2026-06-07) — Semgrep action fix, attest-build-provenance, Python 3.14 standard, --break-system-packages

- 🔴 **Fixed:** Replaced nonexistent Semgrep action reference with correct `returntocorp/semgrep-action@713efdd...` (commit-SHA pinned). The `semgrep/semgrep` repository does not exist — the actual action is `returntocorp/semgrep-action`.
- 🔴 **Fixed:** Replaced stale `actions/attest` (v4) references with `attest-build-provenance@v2` in version matrix and changelog. The `actions/attest` action was renamed to `actions/attest-build-provenance` by GitHub.
- 🟡 **Updated:** CI-CDW-4a — Python 3.14 is now the standard target for all projects. Legacy projects SHOULD upgrade to 3.14.
- 🟡 **Added:** CI-CDW-82 — All `pip install` commands in CI workflows targeting Python >=3.14 MUST include `--break-system-packages` (PEP 668 compliance on GitHub Actions runners). Virtual environment users are exempt.
- 🟡 **Documented:** `/api/health` endpoint path assumption in STATE section (defaults to `/api/health`, configurable via `health_port` in configuration contract).
- 🟠 **Documented:** `MCP_UNSAFE_PUBLIC_ACCESS_CONFIRMED=1` as a project-specific opt-in flag for MCP servers allowing public tool access without authentication.

### v2.0.1 (2026-06-05) — Checkout security, workflow_run guard, cache validation

- Added Rule 24 / CI-CDW-79: `actions/checkout` MUST include `persist-credentials: false`
- Added Rule 25 / CI-CDW-80: `workflow_run` trigger guard with explicit branches, event type, and conclusion check
- Added Rule 26 / CI-CDW-81: `cache: pip` dependency validation — requires `requirements.txt` or `pyproject.toml`

### v2.0.0 (2026-05-23) — Security hardening + version bumps + deployment patches

- **NOTE:** `semgrep/semgrep-action@v1` remains the canonical action. The upstream repo is archived (Apr 2024) but still resolves tags and executes correctly. The `semgrep/semgrep` repository does NOT exist as a GitHub Action — migration was attempted and reverted based on hybrid-therapist deployment.
- **BREAKING:** All action references now use full commit SHA format (`owner/repo@<sha>  # vX`)
- Bumped `actions/upload-artifact` from v4 → v7
- Bumped `actions/download-artifact` from v4 → v8
- Updated .NET SDK to 10.0.x (latest)
- Added rules CI-CDW-73, CI-CDW-74, CI-CDW-75 (commit SHA pinning)
- Added rules CI-CDW-76,76a,76b,76c,76d: auto-tag→publish chain with gh workflow run (filename-based via publish.yml, workflow_dispatch standalone trigger, SKIP_TAG env var pattern)
- Added rule CI-CDW-77: `--strict` flag on docs-validation MUST be configurable, SHOULD default to off (warnings are advisory, should not fail CI)
- Added rule CI-CDW-78: `CHANGELOG.md` MUST be in `afds_config.yaml exempt_files` — changelogs are non-AFDS files per AFDS §2.2
- Added rule requiring `docker` in `package_ecosystems` when `use_docker: true`
- Added rule requiring `[tool.mypy].python_version` consistency with CI python_version
- Fixed `SEMGREP_BASELINE_REF` and `publishToken` in deployed semgrep workflows
- Fixed `hashFiles` guard on SARIF upload in semgrep-scheduled workflows
- Added YAML frontmatter to SKILL.md with name, description, standard_version

### 1.0.1 (2026-05-21)
- Fixed: Rule ID collision — Dependabot rules CI-CDW-52/53 overlapped with Semgrep rules CI-CDW-52/53. Renumbered Dependabot (52→54, 53→55, 54→56, 55→57), Docs (56→58, 57→59, 58→60), Concurrency (59→61, 60→62), .NET (61→63, 62→64, 63→65, 64→66, 65→67), PR Feedback (66→68, 67→69).
- Added: `[CI-CDW-52]` (L1+) — `SEMGREP_BASELINE_REF` env var for diff-aware Semgrep scanning, upgraded from L3+ to L1+.
- Added: `[CI-CDW-53]` (L2+) — `hashFiles('semgrep.sarif')` guard on SARIF upload to prevent spurious failures.
- Added: `[CI-CDW-53a]` (SHOULD) — `.semgrep.yml` triage file for accepted unfixable findings.
- Added: `[CI-CDW-70]`, `[CI-CDW-71]`, `[CI-CDW-72]` (Rule 22) — pyproject.toml classifier consistency, mypy configuration completeness, and cross-source Python version agreement.
- Added: Edge cases for `# nosemgrep` in Dockerfiles (must be on separate line) and direct push to main without PR.
- Updated: Semgrep templates — added `SEMGREP_BASELINE_REF` env, `hashFiles` guard, and fixed `SEMGREP_EXIT_CODE` → `SEMGREP_OUTCOME` variable naming.
- Updated: Code Review Checklist in SKILL.md — all rule references updated to new numbering.

### 1.0.0 (2026-05-20)
- Initial standard: Unicode CI pipeline (lint, test, docker-smoke), Docker publish, auto-tag, unified action versions, Semgrep security scanning, Dependabot dependency management, documentation validation (CAFDS), Codecov integration, .NET CI variant, PR feedback patterns, concurrency best practices.
- Scope: Python + Docker (primary), .NET + NuGet (variant), polyglot projects.
- Rules: `[CI-CDW-1]` through `[CI-CDW-69]` covering workflow files, action versions, Python version, CI structure (3 jobs), lint quality gates, test coverage, Docker smoke, publish (multi-arch + attestation), auto-tag, documentation validation, project config contract, customizations, source layout variants, Docker-less projects, service integration, standard versioning, non-MCP smoke, Semgrep scanning, Dependabot, docs validation, concurrency, .NET variant, PR feedback.
- Action versions pinned: checkout@v6, setup-python@v6, buildx@v4, login@v4, metadata@v6, build-push@v7, attest-build-provenance@v2, gh-release@v3, codecov@v6, upload-artifact@v4, semgrep-action@v1, upload-sarif@v4, cache@v5, setup-dotnet@v5, github-script@v9, changed-files@v47, test-reporter@v3.

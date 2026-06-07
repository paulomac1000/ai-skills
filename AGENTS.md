## Pre-commit Hooks

This project uses pre-commit to enforce code quality before commits.

**Setup**: `pre-commit install`
**Run manually**: `pre-commit run --all-files`
**Hooks mirror CI**: The same checks run in `.github/workflows/ci.yml` lint job.
**Config**: `.pre-commit-config.yaml` follows `ref.precommit-standard` v1.0.0.

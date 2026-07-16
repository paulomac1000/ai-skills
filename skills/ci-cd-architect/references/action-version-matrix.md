# Deprecated action version matrix

This file remains as a compatibility pointer. It is not a version authority.

GitHub Action refs are declared in workflow manifests and updated by Dependabot. Generate the current repository view with:

```bash
python3 scripts/dependency_catalog.py
```

Review the generated `docs/generated/dependency-catalog.md` and the Dependabot pull request. Do not copy refs from this file into workflows.

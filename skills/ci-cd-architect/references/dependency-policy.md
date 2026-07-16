# Dependency policy

Dependabot owns update proposals for supported ecosystems. Manifests and lock files remain the source of truth.

`dependency_catalog.py` scans GitHub Actions, Python, NuGet, npm, and container manifests and generates `docs/generated/dependency-catalog.md` plus JSON. It does not guess latest versions. Optional registry checks may annotate availability, but an update is accepted only through normal tests and review.

Use grouped updates for related toolchains, separate security updates from broad migrations, and keep preview dependencies opt-in. For GitHub Actions, preserve immutable SHA pins and the human-readable release tag comment when policy requires it.

# Hook catalog policy

This repository no longer maintains a hand-written current-version catalog.

Select hooks from the project's accepted framework and declare them in its manifest. Dependabot or the ecosystem update tool maintains refs. `scripts/dependency_catalog.py` reports the versions actually declared in the repository.

Evaluate a hook by ownership, release activity, permissions, runtime, language environment, file-scope behavior, and whether CI enforces the same purpose.

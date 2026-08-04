"""Contract tests for governed local pre-commit and pre-push guidance."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "skills/ci-cd-architect/references/local-quality-gates.md"


def test_husky_lint_staged_profile_preserves_ci_authority() -> None:
    text = REFERENCE.read_text(encoding="utf-8")
    required = (
        "## Package-manager selection",
        "Do not silently default to npm",
        "## Husky and lint-staged profile",
        "partially staged files",
        "must not trigger a network install",
        "hosted CI remains authoritative",
        "do not create commits automatically",
    )
    for token in required:
        assert token in text


def test_local_hook_profile_rejects_unsafe_convenience_defaults() -> None:
    text = REFERENCE.read_text(encoding="utf-8")
    prohibited = (
        "automatic staging or committing",
        "downloading an unpinned tool through `npx`",
        "network calls",
        "full environment orchestration on every commit",
    )
    for token in prohibited:
        assert token in text


def test_local_hook_verification_covers_real_index_and_offline_behavior() -> None:
    text = REFERENCE.read_text(encoding="utf-8")
    required = (
        "package-manager lifecycle or `prepare` integration",
        "partially staged file with additional unstaged edits",
        "filename containing spaces or non-ASCII characters",
        "operation without network access",
        "local bypass followed by rejection from the authoritative hosted gate",
    )
    for token in required:
        assert token in text

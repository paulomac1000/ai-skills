"""Dependency lock completeness and platform selection contract."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.select_lock import selected_lock

ROOT = Path(__file__).resolve().parents[1]
HASH = re.compile(r"--hash=sha256:[0-9a-f]{64}")
PLATFORMS = {"linux": "linux", "darwin": "macos", "win32": "windows"}


def logical_requirements(text: str) -> list[str]:
    lines: list[str] = []
    current = ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        current += (" " if current else "") + stripped.rstrip("\\").strip()
        if not stripped.endswith("\\"):
            lines.append(current)
            current = ""
    assert not current
    return lines


def test_every_committed_lock_is_fully_pinned_and_hashed() -> None:
    locks = sorted(ROOT.glob("requirements-dev-*.lock")) + sorted(
        (ROOT / "skills/mcp-server-architect/locks").glob("*.lock")
    )
    assert len(locks) == 9
    for path in locks:
        requirements = logical_requirements(path.read_text(encoding="utf-8"))
        assert requirements, path
        for requirement in requirements:
            assert "==" in requirement, (path, requirement)
            assert HASH.search(requirement), (path, requirement)
            assert " --hash=sha256:" in requirement, (path, requirement)


def test_platform_selector_is_explicit_and_rejects_unknown_platforms() -> None:
    for platform, suffix in PLATFORMS.items():
        assert selected_lock(platform).name == f"requirements-dev-{suffix}.lock"
    with pytest.raises(RuntimeError):
        selected_lock("plan9")

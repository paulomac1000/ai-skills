"""Global test-process isolation for Git-backed repository fixtures."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def isolate_git_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent developer/global Git policy from changing repository test behavior."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_OPTIONAL_LOCKS", "0")
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    values = (
        ("commit.gpgsign", "false"),
        ("core.fsmonitor", "false"),
        ("core.hooksPath", os.devnull),
        ("core.pager", "cat"),
    )
    monkeypatch.setenv("GIT_CONFIG_COUNT", str(len(values)))
    for index, (key, value) in enumerate(values):
        monkeypatch.setenv(f"GIT_CONFIG_KEY_{index}", key)
        monkeypatch.setenv(f"GIT_CONFIG_VALUE_{index}", value)

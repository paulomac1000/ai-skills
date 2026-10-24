"""Integration base resolution regressions for the push-path audit.

A push to main proposes the range between the branch state the provider
recorded before the push and the pushed head. A base that is missing,
malformed, or the zero SHA cannot be audited, so the gate must fail closed
instead of silently auditing nothing.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/resolve_integration_base.py"


def _invoke(base: str | None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT)]
    if base is not None:
        command += ["--base", base]
    return subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)


def test_a_full_provider_recorded_base_is_accepted() -> None:
    completed = _invoke("a" * 40)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "a" * 40


def test_the_zero_sha_of_a_branch_creation_cannot_be_audited() -> None:
    completed = _invoke("0" * 40)
    assert completed.returncode == 1
    assert "INTEGRATION_BASE_ZERO" in completed.stdout


def test_a_malformed_base_fails_closed() -> None:
    for base in ("", "abc123", "A" * 40, "g" * 40, "a" * 39, "a" * 41):
        completed = _invoke(base)
        assert completed.returncode == 1, base
        assert "INTEGRATION_BASE_INVALID" in completed.stdout


def test_a_missing_base_argument_fails_closed() -> None:
    completed = _invoke(None)
    assert completed.returncode != 0

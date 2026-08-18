"""Provider-backed trust uses fixed Git identity and immutable object bytes."""

from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "contracts/validate_trusted_executable_sources.py"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("external_identity_object_binding", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _checkout(root: Path) -> str:
    root.mkdir()
    (root / "policy.yaml").write_text("value: trusted\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True, timeout=30)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True, timeout=30)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True, timeout=30)
    subprocess.run(
        ["git", "-C", str(root), "remote", "add", "origin", "https://github.com/trusted/authority.git"],
        check=True,
        timeout=30,
    )
    subprocess.run(["git", "-C", str(root), "add", "policy.yaml"], check=True, timeout=30)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "policy"], check=True, timeout=30)
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()


def test_trusted_git_identity_does_not_resolve_from_candidate_path(tmp_path: Path, monkeypatch) -> None:
    trusted = _module()
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_git = fake_bin / ("git.exe" if os.name == "nt" else "git")
    fake_git.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    if os.name != "nt":
        fake_git.chmod(fake_git.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", str(fake_bin))

    selected = Path(trusted._trusted_git_executable())

    assert selected.is_absolute()
    assert selected != fake_git


def test_authority_text_reads_locked_blob_not_mutated_worktree(tmp_path: Path) -> None:
    trusted = _module()
    authority = tmp_path / "authority"
    revision = _checkout(authority)
    (authority / "policy.yaml").write_text("value: candidate-controlled\n", encoding="utf-8")

    observed = trusted._authority_text(authority, revision, "policy.yaml")

    assert observed == "value: trusted\n"

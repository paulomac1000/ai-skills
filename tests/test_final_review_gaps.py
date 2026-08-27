"""Final fail-closed regressions for evidence, trusted checkout identity, and stable releases."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from contracts.run_evidence_command import main as run_evidence_command
from contracts.validate_trusted_executable_sources import validate_lock
from scripts import check_release_version


def test_evidence_command_kills_timeout_and_records_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "slow.py"
    script.write_text("import time\ntime.sleep(10)\n", encoding="utf-8")
    output = tmp_path / "evidence.json"
    assert (
        run_evidence_command(
            [
                "--execution-id",
                "slow-gate",
                "--timeout-seconds",
                "1",
                "--output",
                str(output),
                "--",
                sys.executable,
                str(script),
            ]
        )
        == 124
    )
    record = json.loads(output.read_text(encoding="utf-8"))
    assert "exceeded timeout" in record["validation_error"]


def test_evidence_command_bounds_stdout_during_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "noisy.py"
    script.write_text("import sys\nsys.stdout.write('x' * 200000)\nsys.stdout.flush()\n", encoding="utf-8")
    output = tmp_path / "evidence.json"
    assert (
        run_evidence_command(
            [
                "--execution-id",
                "noisy-gate",
                "--max-output-bytes",
                "1024",
                "--output",
                str(output),
                "--",
                sys.executable,
                str(script),
            ]
        )
        == 125
    )
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["command_result"]["stdout"]["bytes"] <= 1024
    assert "output exceeded" in record["validation_error"]


def _git(path: Path, *args: str) -> str:
    completed = subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True, timeout=30)
    return completed.stdout.strip()


def _authority(path: Path, repository: str = "owner/trusted") -> str:
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True, timeout=30)
    _git(path, "config", "user.name", "Test")
    _git(path, "config", "user.email", "test@example.invalid")
    _git(path, "remote", "add", "origin", f"https://github.com/{repository}.git")
    (path / "tool.py").write_text("print('trusted')\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "fixture")
    return _git(path, "rev-parse", "HEAD")


def test_trusted_authority_checkout_binds_remote_and_head(tmp_path: Path) -> None:
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    authority = tmp_path / "authority"
    revision = _authority(authority)
    import hashlib

    payload = (authority / "tool.py").read_bytes()
    lock = {
        "schema_version": 1,
        "sources": [
            {
                "id": "collector",
                "role": "evidence-collector",
                "repository": "owner/trusted",
                "revision": revision,
                "credential_access": "read-only-provider",
                "files": [{"authority_path": "tool.py", "sha256": "sha256:" + hashlib.sha256(payload).hexdigest()}],
            }
        ],
    }
    lock_path = consumer / "trusted-executable-sources.lock.yaml"
    lock_path.write_text(yaml.safe_dump(lock), encoding="utf-8")
    assert validate_lock(lock_path, repository_root=consumer, authority_roots={"collector": authority}) == []
    _git(authority, "remote", "set-url", "origin", "https://github.com/other/repo.git")
    assert any(
        "repository" in finding
        for finding in validate_lock(lock_path, repository_root=consumer, authority_roots={"collector": authority})
    )


def _init_release_repo(root: Path) -> str:
    (root / "skills/demo").mkdir(parents=True)
    (root / "skills/demo/manifest.yaml").write_text("name: demo\nversion: 1.0.0\nmaturity: stable\n", encoding="utf-8")
    (root / "skills/demo/STANDARD.md").write_text("# Demo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True, timeout=30)
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return _git(root, "rev-parse", "HEAD")


def test_stable_release_cannot_be_removed_or_downgraded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = _init_release_repo(tmp_path)
    monkeypatch.setattr(check_release_version, "ROOT", tmp_path)
    (tmp_path / "skills/demo/manifest.yaml").unlink()
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "remove")
    assert any("was removed" in finding for finding in check_release_version.validate_version_bumps(base))
    _git(tmp_path, "reset", "--hard", base)
    (tmp_path / "skills/demo/manifest.yaml").write_text(
        "name: demo\nversion: 1.1.0\nmaturity: candidate\n", encoding="utf-8"
    )
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "downgrade-maturity")
    assert any("cannot be downgraded" in finding for finding in check_release_version.validate_version_bumps(base))


def test_stable_release_version_must_increase_for_semantic_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = _init_release_repo(tmp_path)
    monkeypatch.setattr(check_release_version, "ROOT", tmp_path)
    (tmp_path / "skills/demo/manifest.yaml").write_text(
        "name: demo\nversion: 0.9.0\nmaturity: stable\n", encoding="utf-8"
    )
    (tmp_path / "skills/demo/STANDARD.md").write_text("# Demo\n\nchanged\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "bad-version")
    assert any("must not decrease" in finding for finding in check_release_version.validate_version_bumps(base))

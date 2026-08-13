#!/usr/bin/env python3
"""Apply the last reviewed trust/evidence/release fixes; deleted before commit."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, got {count}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# Bounded command execution: no unlimited temp-file output and no unbounded runtime.
replace_once(
    "contracts/run_evidence_command.py",
    '''import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, BinaryIO
''',
    '''import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO
''',
)
replace_once(
    "contracts/run_evidence_command.py",
    '''EXECUTION_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
READ_CHUNK_BYTES = 1024 * 1024
''',
    '''EXECUTION_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
READ_CHUNK_BYTES = 1024 * 1024
PIPE_READ_BYTES = 64 * 1024
MAX_CAPTURE_BYTES = 8 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 900
MAX_TIMEOUT_SECONDS = 3600
''',
)
replace_once(
    "contracts/run_evidence_command.py",
    '''def _stream_observation(source: BinaryIO) -> dict[str, Any]:
    source.flush()
    source.seek(0)
    digest = hashlib.sha256()
    size = 0
    while chunk := source.read(READ_CHUNK_BYTES):
        digest.update(chunk)
        size += len(chunk)
    source.seek(0)
    return {"digest": f"sha256:{digest.hexdigest()}", "bytes": size}


def _replay(source: BinaryIO, destination: BinaryIO) -> None:
    source.seek(0)
    while chunk := source.read(READ_CHUNK_BYTES):
        destination.write(chunk)
    destination.flush()
''',
    '''@dataclass(slots=True)
class _CapturedStream:
    data: bytearray = field(default_factory=bytearray)
    bytes_seen: int = 0
    overflow: bool = False

    def observation(self) -> dict[str, Any]:
        payload = bytes(self.data)
        return {"digest": f"sha256:{hashlib.sha256(payload).hexdigest()}", "bytes": len(payload)}


def _drain_stream(
    source: BinaryIO,
    capture: _CapturedStream,
    *,
    limit: int,
    overflow_event: threading.Event,
) -> None:
    try:
        while chunk := source.read(PIPE_READ_BYTES):
            capture.bytes_seen += len(chunk)
            remaining = max(0, limit - len(capture.data))
            if remaining:
                capture.data.extend(chunk[:remaining])
            if capture.bytes_seen > limit:
                capture.overflow = True
                overflow_event.set()
    finally:
        source.close()


def _execute_bounded(
    argv: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    max_output_bytes: int,
) -> tuple[int, _CapturedStream, _CapturedStream, str | None, int | None]:
    process = subprocess.Popen(  # noqa: S603
        argv,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None and process.stderr is not None
    overflow_event = threading.Event()
    stdout_capture = _CapturedStream()
    stderr_capture = _CapturedStream()
    threads = [
        threading.Thread(
            target=_drain_stream,
            args=(process.stdout, stdout_capture),
            kwargs={"limit": max_output_bytes, "overflow_event": overflow_event},
            daemon=True,
        ),
        threading.Thread(
            target=_drain_stream,
            args=(process.stderr, stderr_capture),
            kwargs={"limit": max_output_bytes, "overflow_event": overflow_event},
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + timeout_seconds
    execution_error: str | None = None
    failure_status: int | None = None
    while process.poll() is None:
        if overflow_event.wait(timeout=0.02):
            execution_error = f"command output exceeded {max_output_bytes} bytes per stream"
            failure_status = 125
            process.kill()
            break
        if time.monotonic() >= deadline:
            execution_error = f"command exceeded timeout of {timeout_seconds} seconds"
            failure_status = 124
            process.kill()
            break
    returncode = process.wait()
    for thread in threads:
        thread.join(timeout=5)
    if any(thread.is_alive() for thread in threads):
        raise RuntimeError("command output drain did not terminate")
    if execution_error is None and (stdout_capture.overflow or stderr_capture.overflow):
        execution_error = f"command output exceeded {max_output_bytes} bytes per stream"
        failure_status = 125
    return returncode, stdout_capture, stderr_capture, execution_error, failure_status


def _replay(capture: _CapturedStream, destination: BinaryIO) -> None:
    destination.write(capture.data)
    destination.flush()
''',
)
replace_once(
    "contracts/run_evidence_command.py",
    '''    parser.add_argument("--artifact-file", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path, required=True)
''',
    '''    parser.add_argument("--artifact-file", action="append", type=Path, default=[])
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-output-bytes", type=int, default=MAX_CAPTURE_BYTES)
    parser.add_argument("--output", type=Path, required=True)
''',
)
replace_once(
    "contracts/run_evidence_command.py",
    '''    repository_root = Path.cwd().resolve(strict=True)
    working_directory, working_directory_text = _safe_working_directory(args.working_directory, repository_root)

    with tempfile.TemporaryFile() as stdout_capture, tempfile.TemporaryFile() as stderr_capture:
        completed = subprocess.run(  # noqa: S603
            argv,
            cwd=working_directory,
            check=False,
            stdout=stdout_capture,
            stderr=stderr_capture,
        )
        stdout_observation = _stream_observation(stdout_capture)
        stderr_observation = _stream_observation(stderr_capture)
        _replay(stdout_capture, sys.stdout.buffer)
        _replay(stderr_capture, sys.stderr.buffer)

    results: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    validation_error: str | None = None
''',
    '''    repository_root = Path.cwd().resolve(strict=True)
    working_directory, working_directory_text = _safe_working_directory(args.working_directory, repository_root)
    if not 0 < args.timeout_seconds <= MAX_TIMEOUT_SECONDS:
        raise ValueError(f"timeout_seconds must be between 1 and {MAX_TIMEOUT_SECONDS}")
    if not 0 < args.max_output_bytes <= MAX_CAPTURE_BYTES:
        raise ValueError(f"max_output_bytes must be between 1 and {MAX_CAPTURE_BYTES}")

    returncode, stdout_capture, stderr_capture, execution_error, failure_status = _execute_bounded(
        argv,
        cwd=working_directory,
        timeout_seconds=args.timeout_seconds,
        max_output_bytes=args.max_output_bytes,
    )
    stdout_observation = stdout_capture.observation()
    stderr_observation = stderr_capture.observation()
    _replay(stdout_capture, sys.stdout.buffer)
    _replay(stderr_capture, sys.stderr.buffer)

    results: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    validation_errors = [execution_error] if execution_error is not None else []
''',
)
replace_once(
    "contracts/run_evidence_command.py",
    '''    except (OSError, ValueError) as exc:
        validation_error = str(exc)

    record: dict[str, Any] = {
''',
    '''    except (OSError, ValueError) as exc:
        validation_errors.append(str(exc))
    validation_error = "; ".join(validation_errors) if validation_errors else None

    record: dict[str, Any] = {
''',
)
replace_once(
    "contracts/run_evidence_command.py",
    '        "exit_status": completed.returncode,\n',
    '        "exit_status": returncode,\n',
)
replace_once(
    "contracts/run_evidence_command.py",
    '''    if completed.returncode != 0:
        return completed.returncode
    if validation_error is not None:
        raise ValueError(validation_error)
''',
    '''    if failure_status is not None:
        return failure_status
    if returncode != 0:
        return returncode
    if validation_error is not None:
        raise ValueError(validation_error)
''',
)

# Authority bytes only count when the checkout identity itself matches repository + exact revision.
replace_once(
    "contracts/validate_trusted_executable_sources.py",
    '''import os
import stat
''',
    '''import os
import re
import stat
import subprocess
''',
)
replace_once(
    "contracts/validate_trusted_executable_sources.py",
    '''MAX_SOURCE_BYTES = 8 * 1024 * 1024
''',
    '''MAX_SOURCE_BYTES = 8 * 1024 * 1024
GITHUB_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
''',
)
replace_once(
    "contracts/validate_trusted_executable_sources.py",
    '''def _authority_roots(values: Sequence[str]) -> dict[str, Path]:
''',
    '''def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed git executable and argument vector.
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise ValueError(detail)
    return completed.stdout.strip()


def _repository_from_remote(value: str) -> str:
    remote = value.strip()
    prefixes = ("https://github.com/", "http://github.com/", "ssh://git@github.com/")
    for prefix in prefixes:
        if remote.startswith(prefix):
            remote = remote[len(prefix) :]
            break
    else:
        if remote.startswith("git@github.com:"):
            remote = remote[len("git@github.com:") :]
        else:
            raise ValueError("authority origin must be a GitHub owner/name remote")
    remote = remote.rstrip("/")
    if remote.endswith(".git"):
        remote = remote[:-4]
    if GITHUB_REPOSITORY.fullmatch(remote) is None:
        raise ValueError("authority origin must resolve to GitHub owner/name")
    return remote


def _verify_authority_identity(root: Path, repository: str, revision: str) -> None:
    try:
        top_level = Path(_git(root, "rev-parse", "--show-toplevel")).resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise ValueError(f"authority checkout is not a verifiable git checkout: {exc}") from exc
    if top_level != root.resolve(strict=True):
        raise ValueError("authority root must be the git checkout top level")
    head = _git(root, "rev-parse", "HEAD")
    if head != revision:
        raise ValueError(f"authority checkout HEAD {head!r} does not match locked revision {revision!r}")
    actual_repository = _repository_from_remote(_git(root, "remote", "get-url", "origin"))
    if actual_repository.casefold() != repository.casefold():
        raise ValueError(
            f"authority checkout repository {actual_repository!r} does not match locked repository {repository!r}"
        )


def _authority_roots(values: Sequence[str]) -> dict[str, Path]:
''',
)
replace_once(
    "contracts/validate_trusted_executable_sources.py",
    '''        candidate = Path(path).resolve(strict=True)
        if not candidate.is_dir():
''',
    '''        lexical = Path(path)
        if lexical.is_symlink():
            raise ValueError(f"authority root must not be a symlink: {path}")
        candidate = lexical.resolve(strict=True)
        if not candidate.is_dir():
''',
)
replace_once(
    "contracts/validate_trusted_executable_sources.py",
    '''        if raw_source.get("credential_access") != "none" and authority_root is None:
            findings.append(
                f"sources.{index}: credential-bearing trusted source {source_id} requires an authority checkout"
            )
        files = raw_source["files"]
''',
    '''        if raw_source.get("credential_access") != "none" and authority_root is None:
            findings.append(
                f"sources.{index}: credential-bearing trusted source {source_id} requires an authority checkout"
            )
        authority_identity_valid = authority_root is not None
        if authority_root is not None:
            try:
                _verify_authority_identity(
                    authority_root,
                    str(raw_source["repository"]),
                    str(raw_source["revision"]),
                )
            except ValueError as exc:
                authority_identity_valid = False
                findings.append(f"sources.{index}: {exc}")
        files = raw_source["files"]
''',
)
replace_once(
    "contracts/validate_trusted_executable_sources.py",
    '''            if authority_root is not None:
                try:
''',
    '''            if authority_root is not None and authority_identity_valid:
                try:
''',
)

# Stable releases cannot be silently removed, downgraded to candidate, or version-decremented.
replace_once(
    "scripts/check_release_version.py",
    '''import yaml

ROOT = Path(__file__).resolve().parents[1]
''',
    '''import yaml

from contracts.semver import parse_semver

ROOT = Path(__file__).resolve().parents[1]
''',
)
replace_once(
    "scripts/check_release_version.py",
    '''def validate_version_bumps(base: str) -> list[str]:
    changed = _changed_paths(base)
    shared_contract_change = any(path.startswith("contracts/") for path in changed)
    findings: list[str] = []
    for manifest_path in sorted((ROOT / "skills").glob("*/manifest.yaml")):
        relative = manifest_path.relative_to(ROOT).as_posix()
        current = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(current, dict) or current.get("maturity") != "stable":
            continue
        old_text = _git_show(base, relative)
        if old_text is None:
            continue
        previous = yaml.safe_load(old_text)
        if not isinstance(previous, dict):
            continue
        skill_prefix = f"skills/{manifest_path.parent.name}/"
        semantic_change = shared_contract_change or any(path.startswith(skill_prefix) for path in changed)
        if semantic_change and current.get("version") == previous.get("version"):
            findings.append(f"{manifest_path.parent.name}: stable shipped content changed without a skill version bump")
    return findings
''',
    '''def _base_manifest_paths(base: str) -> set[str]:
    completed = subprocess.run(  # noqa: S603
        ["git", "ls-tree", "-r", "--name-only", base, "--", "skills"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return {
        line.strip()
        for line in completed.stdout.splitlines()
        if line.strip().startswith("skills/") and line.strip().endswith("/manifest.yaml")
    }


def _stable_triplet(value: object, skill_name: str) -> tuple[int, int, int]:
    parsed = parse_semver(value)
    if parsed.prerelease:
        raise ValueError(f"{skill_name}: stable skill version must not be a prerelease")
    return parsed.major, parsed.minor, parsed.patch


def validate_version_bumps(base: str) -> list[str]:
    changed = _changed_paths(base)
    shared_contract_change = any(path.startswith("contracts/") for path in changed)
    findings: list[str] = []
    for relative in sorted(_base_manifest_paths(base)):
        old_text = _git_show(base, relative)
        if old_text is None:
            continue
        previous = yaml.safe_load(old_text)
        if not isinstance(previous, dict) or previous.get("maturity") != "stable":
            continue
        skill_name = Path(relative).parent.name
        current_path = ROOT / relative
        if not current_path.is_file():
            findings.append(f"{skill_name}: previously stable skill manifest was removed")
            continue
        current = yaml.safe_load(current_path.read_text(encoding="utf-8"))
        if not isinstance(current, dict) or current.get("maturity") != "stable":
            findings.append(f"{skill_name}: previously stable skill cannot be downgraded from stable maturity")
            continue
        try:
            previous_version = _stable_triplet(previous.get("version"), skill_name)
            current_version = _stable_triplet(current.get("version"), skill_name)
        except ValueError as exc:
            findings.append(str(exc))
            continue
        if current_version < previous_version:
            findings.append(f"{skill_name}: stable skill version must not decrease")
            continue
        skill_prefix = f"skills/{skill_name}/"
        semantic_change = shared_contract_change or any(path.startswith(skill_prefix) for path in changed)
        if semantic_change and current_version <= previous_version:
            findings.append(f"{skill_name}: stable shipped content changed without increasing the skill version")
    return findings
''',
)

# Existing authority fixture now models an actual immutable checkout.
replace_once(
    "tests/test_real_usage_hardening.py",
    '''import json
import sys
''',
    '''import json
import subprocess
import sys
''',
)
replace_once(
    "tests/test_real_usage_hardening.py",
    '''ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
''',
    '''ROOT = Path(__file__).resolve().parents[1]


def _init_authority_checkout(path: Path, repository: str = "owner/trusted") -> str:
    subprocess.run(["git", "init", "-q", str(path)], check=True, timeout=30)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True, timeout=30)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.invalid"], check=True, timeout=30)
    subprocess.run(
        ["git", "-C", str(path), "remote", "add", "origin", f"https://github.com/{repository}.git"],
        check=True,
        timeout=30,
    )
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True, timeout=30)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "fixture"], check=True, timeout=30)
    completed = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.stdout.strip()


def _load(name: str, path: Path):
''',
)
replace_once(
    "tests/test_real_usage_hardening.py",
    '''    (authority / "tools/collector.py").write_bytes(content)
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
''',
    '''    (authority / "tools/collector.py").write_bytes(content)
    authority_revision = _init_authority_checkout(authority)
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
''',
)
replace_once(
    "tests/test_real_usage_hardening.py",
    '''                "repository": "owner/trusted",
                "revision": "a" * 40,
                "credential_access": "read-only-provider",
''',
    '''                "repository": "owner/trusted",
                "revision": authority_revision,
                "credential_access": "read-only-provider",
''',
)
replace_once(
    "tests/test_real_usage_hardening.py",
    '''    (authority / "authority.py").write_bytes(b"different\\n")
    digest = "sha256:" + hashlib.sha256(b"trusted\\n").hexdigest()
''',
    '''    (authority / "authority.py").write_bytes(b"different\\n")
    authority_revision = _init_authority_checkout(authority)
    digest = "sha256:" + hashlib.sha256(b"trusted\\n").hexdigest()
''',
)
replace_once(
    "tests/test_real_usage_hardening.py",
    '''                "repository": "owner/trusted",
                "revision": "b" * 40,
                "credential_access": "none",
''',
    '''                "repository": "owner/trusted",
                "revision": authority_revision,
                "credential_access": "none",
''',
)

(ROOT / "tests/test_final_review_gaps.py").write_text(
    r'''"""Final fail-closed regressions for evidence, trusted checkout identity, and stable releases."""
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
    assert run_evidence_command([
        "--execution-id", "slow-gate", "--timeout-seconds", "1", "--output", str(output), "--",
        sys.executable, str(script),
    ]) == 124
    record = json.loads(output.read_text(encoding="utf-8"))
    assert "exceeded timeout" in record["validation_error"]


def test_evidence_command_bounds_stdout_during_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "noisy.py"
    script.write_text("import sys\nsys.stdout.write('x' * 200000)\nsys.stdout.flush()\n", encoding="utf-8")
    output = tmp_path / "evidence.json"
    assert run_evidence_command([
        "--execution-id", "noisy-gate", "--max-output-bytes", "1024", "--output", str(output), "--",
        sys.executable, str(script),
    ]) == 125
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
        "sources": [{
            "id": "collector", "role": "evidence-collector", "repository": "owner/trusted",
            "revision": revision, "credential_access": "read-only-provider",
            "files": [{"authority_path": "tool.py", "sha256": "sha256:" + hashlib.sha256(payload).hexdigest()}],
        }],
    }
    lock_path = consumer / "trusted-executable-sources.lock.yaml"
    lock_path.write_text(yaml.safe_dump(lock), encoding="utf-8")
    assert validate_lock(lock_path, repository_root=consumer, authority_roots={"collector": authority}) == []
    _git(authority, "remote", "set-url", "origin", "https://github.com/other/repo.git")
    assert any("repository" in finding for finding in validate_lock(
        lock_path, repository_root=consumer, authority_roots={"collector": authority}
    ))


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
    (tmp_path / "skills/demo/manifest.yaml").write_text("name: demo\nversion: 1.1.0\nmaturity: candidate\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "downgrade-maturity")
    assert any("cannot be downgraded" in finding for finding in check_release_version.validate_version_bumps(base))


def test_stable_release_version_must_increase_for_semantic_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = _init_release_repo(tmp_path)
    monkeypatch.setattr(check_release_version, "ROOT", tmp_path)
    (tmp_path / "skills/demo/manifest.yaml").write_text("name: demo\nversion: 0.9.0\nmaturity: stable\n", encoding="utf-8")
    (tmp_path / "skills/demo/STANDARD.md").write_text("# Demo\n\nchanged\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "bad-version")
    assert any("must not decrease" in finding for finding in check_release_version.validate_version_bumps(base))
''',
    encoding="utf-8",
)

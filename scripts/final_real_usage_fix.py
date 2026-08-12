#!/usr/bin/env python3
"""Apply final exact-head fixes derived from hosted CI; deleted before commit."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


replace_once(
    "tests/test_mcp_generator.py",
    '    assert copied_schema.read_bytes() == (ROOT / "contracts/capability-manifest.schema.json").read_bytes()\n',
    '''    assert json.loads(copied_schema.read_text(encoding="utf-8")) == json.loads(\n        (ROOT / "contracts/capability-manifest.schema.json").read_text(encoding="utf-8")\n    )\n''',
)

replace_once(
    "contracts/validate_trusted_executable_sources.py",
    '''def _safe_file(root: Path, raw: str, name: str) -> Path:\n    if not raw or "\\\\" in raw:\n        raise ValueError(f"{name} must use a non-empty POSIX relative path")\n    relative = Path(raw)\n    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):\n        raise ValueError(f"{name} must stay inside its checkout root")\n    candidate = root.joinpath(*relative.parts)\n    try:\n        metadata = candidate.lstat()\n    except FileNotFoundError as exc:\n        raise ValueError(f"{name} does not exist: {raw}") from exc\n    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):\n        raise ValueError(f"{name} must be a regular non-symlink file: {raw}")\n    if metadata.st_size > MAX_SOURCE_BYTES:\n        raise ValueError(f"{name} exceeds {MAX_SOURCE_BYTES} bytes: {raw}")\n    return candidate\n''',
    '''def _safe_file(root: Path, raw: str, name: str) -> Path:\n    if not raw or "\\\\" in raw:\n        raise ValueError(f"{name} must use a non-empty POSIX relative path")\n    relative = Path(raw)\n    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):\n        raise ValueError(f"{name} must stay inside its checkout root")\n    root = root.resolve(strict=True)\n    current = root\n    for part in relative.parts:\n        current /= part\n        if os.path.lexists(current) and current.is_symlink():\n            raise ValueError(f"{name} must not contain symlink components: {raw}")\n    try:\n        candidate = root.joinpath(*relative.parts).resolve(strict=True)\n    except FileNotFoundError as exc:\n        raise ValueError(f"{name} does not exist: {raw}") from exc\n    try:\n        candidate.relative_to(root)\n    except ValueError as exc:\n        raise ValueError(f"{name} must stay inside its checkout root") from exc\n    metadata = candidate.stat()\n    if not stat.S_ISREG(metadata.st_mode):\n        raise ValueError(f"{name} must be a regular non-symlink file: {raw}")\n    if metadata.st_size > MAX_SOURCE_BYTES:\n        raise ValueError(f"{name} exceeds {MAX_SOURCE_BYTES} bytes: {raw}")\n    return candidate\n''',
)

path = ROOT / "tests/test_real_usage_hardening.py"
text = path.read_text(encoding="utf-8")
text += r'''


def test_trusted_source_validator_rejects_duplicate_unknown_and_missing_authority(tmp_path: Path) -> None:
    repository = tmp_path / "consumer"
    authority = tmp_path / "authority"
    repository.mkdir()
    authority.mkdir()
    content = b"trusted\n"
    vendored = repository / "vendor.py"
    authority_file = authority / "authority.py"
    vendored.write_bytes(content)
    authority_file.write_bytes(content)
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    lock = {
        "schema_version": 1,
        "sources": [
            {
                "id": "collector",
                "role": "evidence-collector",
                "repository": "owner/trusted",
                "revision": "a" * 40,
                "credential_access": "read-only-provider",
                "files": [
                    {
                        "authority_path": "authority.py",
                        "local_path": "vendor.py",
                        "sha256": digest,
                    }
                ],
            },
            {
                "id": "collector",
                "role": "vendored-validator",
                "repository": "owner/trusted",
                "revision": "a" * 40,
                "credential_access": "none",
                "files": [{"authority_path": "authority.py", "sha256": digest}],
            },
        ],
    }
    lock_path = repository / "trusted-executable-sources.lock.yaml"
    lock_path.write_text(yaml.safe_dump(lock), encoding="utf-8")
    findings = validate_lock(
        lock_path,
        repository_root=repository,
        authority_roots={"unexpected": authority},
        require_authority=True,
    )
    assert any("duplicate source id" in item for item in findings)
    assert any("authority checkout is required" in item for item in findings)
    assert any("credential-bearing trusted source" in item for item in findings)
    assert any("no lock entry" in item for item in findings)


def test_trusted_source_validator_rejects_authority_digest_and_unsafe_paths(tmp_path: Path) -> None:
    repository = tmp_path / "consumer"
    authority = tmp_path / "authority"
    repository.mkdir()
    authority.mkdir()
    local = repository / "vendor.py"
    local.write_bytes(b"trusted\n")
    (authority / "authority.py").write_bytes(b"different\n")
    digest = "sha256:" + hashlib.sha256(b"trusted\n").hexdigest()
    lock = {
        "schema_version": 1,
        "sources": [
            {
                "id": "validator",
                "role": "vendored-validator",
                "repository": "owner/trusted",
                "revision": "b" * 40,
                "credential_access": "none",
                "files": [
                    {
                        "authority_path": "authority.py",
                        "local_path": "vendor.py",
                        "sha256": digest,
                    }
                ],
            }
        ],
    }
    lock_path = repository / "trusted-executable-sources.lock.yaml"
    lock_path.write_text(yaml.safe_dump(lock), encoding="utf-8")
    assert any(
        "authority digest" in item
        for item in validate_lock(
            lock_path,
            repository_root=repository,
            authority_roots={"validator": authority},
        )
    )

    validator = _load(
        "trusted_source_validator_edges",
        ROOT / "contracts/validate_trusted_executable_sources.py",
    )
    for raw in ("", "../escape.py", "/absolute.py", "dir\\file.py"):
        with pytest.raises(ValueError):
            validator._safe_file(repository, raw, "local_path")
    with pytest.raises(ValueError, match="does not exist"):
        validator._safe_file(repository, "missing.py", "local_path")
    directory = repository / "directory"
    directory.mkdir()
    with pytest.raises(ValueError, match="regular"):
        validator._safe_file(repository, "directory", "local_path")

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("secret\n", encoding="utf-8")
    link = repository / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        return
    with pytest.raises(ValueError, match="symlink components"):
        validator._safe_file(repository, "linked/secret.py", "local_path")


def test_trusted_source_validator_schema_and_cli_edges(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    validator = _load(
        "trusted_source_validator_cli",
        ROOT / "contracts/validate_trusted_executable_sources.py",
    )
    repository = tmp_path / "consumer"
    repository.mkdir()
    invalid = repository / "trusted-executable-sources.lock.yaml"
    invalid.write_text("{}\n", encoding="utf-8")
    assert validate_lock(invalid, repository_root=repository)
    assert validator.main([str(invalid), "--repository-root", str(repository)]) == 1
    assert "trusted executable source findings" in capsys.readouterr().out

    with pytest.raises(ValueError, match="unique"):
        validator._authority_roots(["collector=/tmp", "collector=/tmp"])
    with pytest.raises(ValueError, match="SOURCE_ID=PATH"):
        validator._authority_roots(["malformed"])


def test_trusted_source_lock_rejects_symlinked_vendored_parent(tmp_path: Path) -> None:
    repository = tmp_path / "consumer"
    repository.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    content = b"trusted\n"
    (outside / "validator.py").write_bytes(content)
    link = repository / "vendor"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable on this platform")
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    lock = {
        "schema_version": 1,
        "sources": [
            {
                "id": "validator",
                "role": "vendored-validator",
                "repository": "owner/trusted",
                "revision": "c" * 40,
                "credential_access": "none",
                "files": [
                    {
                        "authority_path": "validator.py",
                        "local_path": "vendor/validator.py",
                        "sha256": digest,
                    }
                ],
            }
        ],
    }
    lock_path = repository / "trusted-executable-sources.lock.yaml"
    lock_path.write_text(yaml.safe_dump(lock), encoding="utf-8")
    assert any("symlink components" in item for item in validate_lock(lock_path, repository_root=repository))
'''
path.write_text(text, encoding="utf-8", newline="\n")

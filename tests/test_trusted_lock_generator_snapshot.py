"""Regression coverage for immutable authority bytes used by trust-lock generation."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "skills/ci-cd-architect/tools/generate_trusted_executable_sources.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("trusted_lock_generator_snapshot", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_generator_hashes_immutable_git_blob_instead_of_authority_worktree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = _load_generator()
    authority = tmp_path / "authority"
    authority.mkdir()
    revision = "a" * 40
    payload = b"immutable authority bytes\n"

    monkeypatch.setattr(generator.trusted_sources, "_verify_authority_identity", lambda *_args: None)

    def git_blob(root: Path, locked_revision: str, raw_path: str) -> bytes:
        assert root == authority.resolve()
        assert locked_revision == revision
        assert raw_path == "contracts/verifier.py"
        return payload

    def forbidden_worktree_read(*_args):
        raise AssertionError("lock generation must not derive authority bytes from the mutable worktree")

    monkeypatch.setattr(generator.trusted_sources, "_git_blob", git_blob)
    monkeypatch.setattr(generator.trusted_sources, "_authority_file", forbidden_worktree_read)
    monkeypatch.setattr(generator.trusted_sources, "_digest", forbidden_worktree_read)

    document = generator.generate_lock(
        authority,
        source_id="validator",
        role="vendored-validator",
        repository="owner/trusted",
        revision=revision,
        credential_access="none",
        authority_paths=["contracts/verifier.py"],
    )

    source = document["sources"][0]
    assert source["files"] == [
        {
            "authority_path": "contracts/verifier.py",
            "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
        }
    ]


@pytest.mark.parametrize(
    ("repository", "revision", "paths", "message"),
    [
        ("not-a-github-repository", "a" * 40, ["validator.py"], "repository must use GitHub owner/name syntax"),
        ("owner/repo", "main", ["validator.py"], "revision must be a full lowercase 40-character commit SHA"),
        ("owner/repo", "a" * 40, [], "at least one --authority-path is required"),
    ],
)
def test_generator_rejects_unbound_source_coordinates_before_git_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    repository: str,
    revision: str,
    paths: list[str],
    message: str,
) -> None:
    generator = _load_generator()
    authority = tmp_path / "authority"
    authority.mkdir()

    def forbidden_identity(*_args):
        raise AssertionError("invalid source coordinates must fail before git identity verification")

    monkeypatch.setattr(generator.trusted_sources, "_verify_authority_identity", forbidden_identity)

    with pytest.raises(ValueError, match=message):
        generator.generate_lock(
            authority,
            source_id="validator",
            role="vendored-validator",
            repository=repository,
            revision=revision,
            credential_access="none",
            authority_paths=paths,
        )


def test_generator_rejects_non_directory_authority_root(tmp_path: Path) -> None:
    generator = _load_generator()
    authority = tmp_path / "authority.txt"
    authority.write_text("not a checkout", encoding="utf-8")

    with pytest.raises(ValueError, match="authority root must be a directory"):
        generator.generate_lock(
            authority,
            source_id="validator",
            role="vendored-validator",
            repository="owner/repo",
            revision="a" * 40,
            credential_access="none",
            authority_paths=["validator.py"],
        )


def test_generator_rejects_duplicate_authority_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = _load_generator()
    authority = tmp_path / "authority"
    authority.mkdir()
    revision = "a" * 40

    monkeypatch.setattr(generator.trusted_sources, "_verify_authority_identity", lambda *_args: None)
    monkeypatch.setattr(generator.trusted_sources, "_git_blob", lambda *_args: b"trusted")

    with pytest.raises(ValueError, match="duplicate authority path: validator.py"):
        generator.generate_lock(
            authority,
            source_id="validator",
            role="vendored-validator",
            repository="owner/repo",
            revision=revision,
            credential_access="none",
            authority_paths=["validator.py", "validator.py"],
        )


def _generated_document() -> dict[str, object]:
    return {
        "schema_version": 1,
        "sources": [
            {
                "id": "validator",
                "role": "vendored-validator",
                "repository": "owner/repo",
                "revision": "a" * 40,
                "credential_access": "none",
                "files": [
                    {
                        "authority_path": "validator.py",
                        "sha256": "sha256:" + "0" * 64,
                    }
                ],
            }
        ],
    }


def test_generator_cli_renders_lock_to_stdout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    generator = _load_generator()
    authority = tmp_path / "authority"
    authority.mkdir()
    document = _generated_document()
    monkeypatch.setattr(generator, "generate_lock", lambda *_args, **_kwargs: document)

    result = generator.main(
        [
            "--authority-root",
            str(authority),
            "--repository",
            "owner/repo",
            "--revision",
            "a" * 40,
            "--authority-path",
            "validator.py",
        ]
    )

    assert result == 0
    assert yaml.safe_load(capsys.readouterr().out) == document


def test_generator_cli_writes_requested_lock_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    generator = _load_generator()
    authority = tmp_path / "authority"
    authority.mkdir()
    output = tmp_path / "trusted-sources.lock.yaml"
    document = _generated_document()
    monkeypatch.setattr(generator, "generate_lock", lambda *_args, **_kwargs: document)

    result = generator.main(
        [
            "--authority-root",
            str(authority),
            "--repository",
            "owner/repo",
            "--revision",
            "a" * 40,
            "--authority-path",
            "validator.py",
            "--output",
            str(output),
        ]
    )

    assert result == 0
    assert capsys.readouterr().out == ""
    assert yaml.safe_load(output.read_text(encoding="utf-8")) == document

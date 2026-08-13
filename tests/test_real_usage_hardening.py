"""Regression coverage derived directly from real downstream ai-skills usage."""

from __future__ import annotations

import errno
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

from contracts.run_evidence_command import main as run_evidence_command
from contracts.validate_trusted_executable_sources import validate_lock

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_command_evidence_does_not_require_fake_junit_and_records_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "gate.py"
    script.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "print('quality-ok')\n"
        "print('diagnostic', file=sys.stderr)\n"
        "Path('artifact.bin').write_bytes(b'exact-artifact')\n",
        encoding="utf-8",
    )
    output = tmp_path / "execution.json"
    assert (
        run_evidence_command(
            [
                "--execution-id",
                "quality-gate",
                "--artifact-file",
                "artifact.bin",
                "--output",
                str(output),
                "--",
                sys.executable,
                str(script),
            ]
        )
        == 0
    )
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["results"] == []
    assert record["command_result"]["kind"] == "command-result"
    assert record["command_result"]["stdout"]["bytes"] > 0
    assert record["command_result"]["stderr"]["bytes"] > 0
    artifact = record["artifacts"][0]
    assert artifact["kind"] == "artifact-observation"
    assert artifact["digest"] == "sha256:" + hashlib.sha256(b"exact-artifact").hexdigest()


def test_junit_result_remains_first_class_test_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "gate.py"
    script.write_text(
        "from pathlib import Path\n"
        "Path('result.xml').write_text('<testsuite><testcase classname=\"tests.x\" name=\"test_y\" /></testsuite>', encoding='utf-8')\n",
        encoding="utf-8",
    )
    output = tmp_path / "execution.json"
    assert (
        run_evidence_command(
            [
                "--execution-id",
                "test-gate",
                "--result-file",
                "result.xml",
                "--output",
                str(output),
                "--",
                sys.executable,
                str(script),
            ]
        )
        == 0
    )
    assert json.loads(output.read_text(encoding="utf-8"))["results"][0]["kind"] == "test-result"


def test_consumer_hygiene_detects_divergent_afds_semgrep_noop_and_unmanaged_pin(tmp_path: Path) -> None:
    checker = _load(
        "consumer_trust_hygiene_test",
        ROOT / "skills/ci-cd-architect/tools/check_consumer_trust_hygiene.py",
    )
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / "Makefile").write_text(
        "docs-check:\n\tpython scripts/vendor/afds_validate_abcdef.py README.md CHANGELOG.md\n",
        encoding="utf-8",
    )
    (tmp_path / ".github/workflows/ci.yml").write_text(
        "env:\n  EVIDENCE_COLLECTOR_REVISION: 0123456789abcdef0123456789abcdef01234567\n"
        "jobs:\n  docs:\n    steps:\n      - run: python .ai-skills/skills/afds-doc-writer/validate.py docs\n",
        encoding="utf-8",
    )
    (tmp_path / ".pre-commit-config.yaml").write_text(
        "repos:\n- repo: local\n  hooks:\n  - id: semgrep\n    name: semgrep\n"
        "    entry: bash -c 'if command -v semgrep; then semgrep --config auto; else echo remains a required CI gate; fi'\n",
        encoding="utf-8",
    )
    findings = checker.check_repository(tmp_path)
    assert any("AFDS is invoked directly from multiple" in item for item in findings)
    assert any("may succeed locally" in item for item in findings)
    assert any("without trusted-executable-sources.lock.yaml" in item for item in findings)
    assert any("hardcoded trusted" in item for item in findings)


def test_trusted_source_lock_binds_authority_and_vendored_bytes(tmp_path: Path) -> None:
    repository = tmp_path / "consumer"
    authority = tmp_path / "authority"
    (repository / "scripts/vendor").mkdir(parents=True)
    (authority / "tools").mkdir(parents=True)
    content = b"print('trusted')\n"
    (repository / "scripts/vendor/collector.py").write_bytes(content)
    (authority / "tools/collector.py").write_bytes(content)
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
                        "authority_path": "tools/collector.py",
                        "local_path": "scripts/vendor/collector.py",
                        "sha256": digest,
                    }
                ],
            }
        ],
    }
    path = repository / "trusted-executable-sources.lock.yaml"
    path.write_text(yaml.safe_dump(lock), encoding="utf-8")
    assert (
        validate_lock(
            path,
            repository_root=repository,
            authority_roots={"collector": authority},
            require_authority=True,
        )
        == []
    )
    assert any("requires an authority checkout" in item for item in validate_lock(path, repository_root=repository))
    (repository / "scripts/vendor/collector.py").write_text("changed\n", encoding="utf-8")
    assert any(
        "local vendored digest" in item
        for item in validate_lock(
            path,
            repository_root=repository,
            authority_roots={"collector": authority},
        )
    )


def test_generator_platform_error_paths_contribute_to_hosted_core_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generator = _load(
        "dotnet_generator_real_usage_test",
        ROOT / "skills/mcp-server-architect/tools/generate_dotnet_server.py",
    )
    with pytest.raises(FileExistsError):
        generator._raise_rename_error(errno.EEXIST, tmp_path / "target")
    with pytest.raises(OSError):
        generator._raise_rename_error(errno.EACCES, tmp_path / "target")
    with pytest.raises(ValueError, match="namespace"):
        generator._validate("System.Bad", "Valid server")
    monkeypatch.setattr(generator.platform, "system", lambda: "FreeBSD")
    with pytest.raises(RuntimeError, match="no configured atomic"):
        generator._rename_noreplace(tmp_path / "source", tmp_path / "target")


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

    authority = tmp_path / "authority-root"
    authority.mkdir()
    authority_value = str(authority)
    with pytest.raises(ValueError, match="unique"):
        validator._authority_roots([f"collector={authority_value}", f"collector={authority_value}"])
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
